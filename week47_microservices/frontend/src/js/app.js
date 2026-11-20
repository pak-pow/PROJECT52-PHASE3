/**
 * PULSEMESH // MICROSERVICES ARCHITECTURE & CHAOS CONSOLE
 * Interactive State Engine, Topology Renderer & Chaos Controller
 * Zero-Emoji Compliance Enforced.
 */

class PulseMeshApp {
  constructor() {
    this.activeTab = 'tab-topology';
    this.servicesMap = {};
    this.circuitBreakers = {};
    this.lbStats = {};
    this.trafficCounters = {};
    this.selectedNode = null;
    this.pollInterval = null;
  }

  init() {
    this.setupEventListeners();
    this.refreshAll();
    this.startPolling();
  }

  setupEventListeners() {
    // Navigation tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        this.switchTab(tab.dataset.tab);
      });
    });
  }

  switchTab(tabId) {
    this.activeTab = tabId;
    document.querySelectorAll('.nav-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tabId);
    });
    document.querySelectorAll('.tab-pane').forEach(p => {
      p.classList.toggle('active', p.id === tabId);
    });

    if (tabId === 'tab-topology') {
      this.renderTopology();
    } else if (tabId === 'tab-broker') {
      this.loadBrokerData();
    }
  }

  startPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollInterval = setInterval(() => {
      this.pollState();
    }, 3000);
  }

  async pollState() {
    try {
      const [healthRes, statsRes] = await Promise.all([
        fetch('/health'),
        fetch('/api/v1/gateway/stats')
      ]);

      if (healthRes.ok) {
        const healthData = await healthRes.json();
        this.updateClusterStatus(healthData);
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        this.updateGatewayStats(statsData);
      }

      if (this.activeTab === 'tab-topology') {
        this.renderTopology();
      } else if (this.activeTab === 'tab-chaos') {
        this.renderCircuitBreakers();
      }
    } catch (err) {
      console.warn('[PulseMesh] Polling error:', err);
    }
  }

  async refreshAll() {
    await Promise.all([
      this.pollState(),
      this.loadRegistryData(),
      this.loadBrokerData()
    ]);
  }

  updateClusterStatus(data) {
    const badge = document.getElementById('cluster-status-badge');
    const status = data.status || 'UNKNOWN';
    badge.innerText = status;
    badge.className = 'badge';

    if (status === 'HEALTHY') badge.classList.add('badge-healthy');
    else if (status === 'DEGRADED') badge.classList.add('badge-degraded');
    else badge.classList.add('badge-down');

    // Count replicas
    let totalInstances = 0;
    if (data.services) {
      Object.values(data.services).forEach(s => {
        totalInstances += (s.total_instances || 0);
      });
    }
    document.getElementById('cluster-instance-count').innerText = totalInstances;
  }

  updateGatewayStats(data) {
    if (data.rate_limiter) {
      document.getElementById('gateway-rate-metric').innerText =
        `${data.rate_limiter.rate_per_second || 100} req/s`;
    }

    if (data.circuit_breakers) {
      this.circuitBreakers = data.circuit_breakers;
      this.renderCircuitBreakers();
    }

    if (data.routing && data.routing.services) {
      this.lbStats = data.routing.services;
    }
  }

  /* ------------------------------------------------------------------------
     1. MESH TOPOLOGY RENDERER
     ------------------------------------------------------------------------ */
  renderTopology() {
    const svg = document.getElementById('mesh-topology-svg');
    if (!svg) return;

    // Define canonical nodes
    const nodes = [
      { id: 'gateway', name: 'API GATEWAY', role: 'Edge Router', x: 70, y: 220, w: 140, h: 70, type: 'gateway' },
      { id: 'registry', name: 'REGISTRY', role: 'Discovery', x: 380, y: 35, w: 140, h: 60, type: 'registry' },
      { id: 'user-01', name: 'USER-PRIMARY', svc: 'user-service', port: 8002, x: 320, y: 150, w: 120, h: 60, type: 'service' },
      { id: 'user-02', name: 'USER-REPLICA', svc: 'user-service', port: 8012, x: 470, y: 150, w: 120, h: 60, type: 'service' },
      { id: 'catalog-01', name: 'CATALOG-PRI', svc: 'catalog-service', port: 8003, x: 320, y: 245, w: 120, h: 60, type: 'service' },
      { id: 'catalog-02', name: 'CATALOG-REP', svc: 'catalog-service', port: 8013, x: 470, y: 245, w: 120, h: 60, type: 'service' },
      { id: 'order-01', name: 'ORDER-PRI', svc: 'order-service', port: 8004, x: 320, y: 340, w: 120, h: 60, type: 'service' },
      { id: 'order-02', name: 'ORDER-REP', svc: 'order-service', port: 8014, x: 470, y: 340, w: 120, h: 60, type: 'service' },
      { id: 'broker', name: 'EVENT BROKER', role: 'Pub/Sub & DLQ', x: 720, y: 245, w: 150, h: 70, type: 'broker' },
      { id: 'notif-01', name: 'NOTIF-SERVICE', svc: 'notification-service', port: 8005, x: 720, y: 375, w: 150, h: 60, type: 'service' }
    ];

    // Links between nodes
    const links = [
      { from: 'gateway', to: 'user-01' },
      { from: 'gateway', to: 'user-02' },
      { from: 'gateway', to: 'catalog-01' },
      { from: 'gateway', to: 'catalog-02' },
      { from: 'gateway', to: 'order-01' },
      { from: 'gateway', to: 'order-02' },
      { from: 'registry', to: 'gateway' },
      { from: 'order-01', to: 'broker' },
      { from: 'order-02', to: 'broker' },
      { from: 'broker', to: 'notif-01' }
    ];

    let html = '';

    // Draw links
    links.forEach(l => {
      const f = nodes.find(n => n.id === l.from);
      const t = nodes.find(n => n.id === l.to);
      if (f && t) {
        const x1 = f.x + f.w / 2;
        const y1 = f.y + f.h / 2;
        const x2 = t.x + t.w / 2;
        const y2 = t.y + t.h / 2;
        html += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="topo-link" />`;
      }
    });

    // Draw nodes
    nodes.forEach(n => {
      let strokeColor = '#30363d';
      let statusText = 'HEALTHY';

      if (n.svc && this.circuitBreakers[n.svc]) {
        const cb = this.circuitBreakers[n.svc];
        if (cb.state === 'OPEN') {
          strokeColor = '#bc8cff'; // Circuit breaker open
          statusText = 'CIRCUIT OPEN';
        }
      }

      html += `
        <g class="topo-node" onclick="app.inspectNode('${n.id}')">
          <rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="6"
                fill="#161b22" stroke="${strokeColor}" />
          <text x="${n.x + 12}" y="${n.y + 24}" fill="#e6edf3" font-size="11" font-weight="700">${n.name}</text>
          <text x="${n.x + 12}" y="${n.y + 42}" fill="#8b949e" font-size="10">${n.port ? `Port: ${n.port}` : (n.role || '')}</text>
          <circle cx="${n.x + n.w - 14}" cy="${n.y + 16}" r="4" fill="#3fb950" />
        </g>
      `;
    });

    svg.innerHTML = html;
  }

  inspectNode(nodeId) {
    this.selectedNode = nodeId;
    const content = document.getElementById('inspector-content');
    const placeholder = document.getElementById('inspector-placeholder');

    placeholder.style.display = 'none';
    content.style.display = 'block';

    document.getElementById('insp-name').innerText = nodeId.toUpperCase();
    document.getElementById('insp-id').innerText = nodeId;
    document.getElementById('insp-addr').innerText = '127.0.0.1';
    document.getElementById('insp-status').innerText = 'HEALTHY';

    let svcName = 'user-service';
    if (nodeId.includes('catalog')) svcName = 'catalog-service';
    else if (nodeId.includes('order')) svcName = 'order-service';
    else if (nodeId.includes('notif')) svcName = 'notification-service';

    const cb = this.circuitBreakers[svcName];
    document.getElementById('insp-cb').innerText = cb ? cb.state : 'CLOSED';
    document.getElementById('insp-latency').innerText =
      this.lbStats[svcName] ? `${this.lbStats[svcName].avg_latency_ms} ms` : '1.2 ms';
  }

  chaosTripSelected() {
    if (!this.selectedNode) return;
    let svc = 'user-service';
    if (this.selectedNode.includes('catalog')) svc = 'catalog-service';
    else if (this.selectedNode.includes('order')) svc = 'order-service';
    this.chaosTrip(svc);
  }

  chaosResetSelected() {
    if (!this.selectedNode) return;
    let svc = 'user-service';
    if (this.selectedNode.includes('catalog')) svc = 'catalog-service';
    else if (this.selectedNode.includes('order')) svc = 'order-service';
    this.chaosReset(svc);
  }

  /* ------------------------------------------------------------------------
     2. SERVICE REGISTRY & SCALE MANAGER
     ------------------------------------------------------------------------ */
  async loadRegistryData() {
    const tbody = document.getElementById('registry-table-body');
    try {
      const res = await fetch('/api/v1/registry/services');
      if (!res.ok) throw new Error('Registry API unavailable');
      const data = await res.json();
      const services = data.services || {};

      let rows = '';
      Object.entries(services).forEach(([svcName, svcData]) => {
        const instances = svcData.instances || [];
        instances.forEach(inst => {
          rows += `
            <tr>
              <td><strong>${inst.service_name}</strong></td>
              <td><code>${inst.instance_id}</code></td>
              <td>${inst.host}:${inst.port}</td>
              <td><span class="badge ${inst.health_status === 'HEALTHY' ? 'badge-healthy' : 'badge-down'}">${inst.health_status}</span></td>
              <td>${inst.weight || 1}</td>
              <td>${inst.last_heartbeat ? inst.last_heartbeat.split('T')[1].slice(0, 8) : '--'}</td>
              <td>
                <button class="btn btn-sm btn-danger" onclick="app.toggleNodeHealth('${inst.instance_id}', 'DOWN')">SET DOWN</button>
                <button class="btn btn-sm btn-success" onclick="app.toggleNodeHealth('${inst.instance_id}', 'HEALTHY')">SET HEALTHY</button>
              </td>
            </tr>
          `;
        });
      });

      tbody.innerHTML = rows || '<tr><td colspan="7" class="text-center text-muted">No instances registered.</td></tr>';
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Registry query failed: ${err.message}</td></tr>`;
    }
  }

  async toggleNodeHealth(instanceId, newStatus) {
    try {
      const res = await fetch('/api/v1/chaos/instance/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_id: instanceId, health_status: newStatus })
      });
      if (res.ok) {
        await this.loadRegistryData();
        await this.pollState();
      }
    } catch (err) {
      alert(`Status update failed: ${err.message}`);
    }
  }

  showScaleModal() {
    document.getElementById('scale-modal').style.display = 'flex';
  }

  hideScaleModal() {
    document.getElementById('scale-modal').style.display = 'none';
  }

  async submitScaleReplica() {
    const svcName = document.getElementById('scale-svc-name').value;
    const port = parseInt(document.getElementById('scale-inst-port').value, 10);

    try {
      const res = await fetch('/api/v1/registry/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_name: svcName,
          instance_id: `${svcName}-${port}`,
          host: '127.0.0.1',
          port: port
        })
      });

      if (res.ok) {
        this.hideScaleModal();
        await this.loadRegistryData();
        await this.pollState();
      } else {
        alert('Replica registration rejected by registry');
      }
    } catch (err) {
      alert(`Registration error: ${err.message}`);
    }
  }

  /* ------------------------------------------------------------------------
     3. LOAD BALANCER SANDBOX
     ------------------------------------------------------------------------ */
  async changeLbStrategy(strategyName) {
    try {
      const res = await fetch('/api/v1/gateway/load-balancer/strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: strategyName })
      });
      if (res.ok) {
        console.log(`[PulseMesh] Load balancer algorithm updated to: ${strategyName}`);
      }
    } catch (err) {
      console.error('Failed to change LB strategy:', err);
    }
  }

  async sendTrafficBurst() {
    const targetPath = document.getElementById('lb-target-path').value;
    const count = parseInt(document.getElementById('lb-burst-count').value, 10);
    const trafficLog = document.getElementById('traffic-log-body');

    for (let i = 0; i < count; i++) {
      const start = performance.now();
      try {
        const res = await fetch(targetPath);
        const elapsed = (performance.now() - start).toFixed(1);
        const upstream = res.headers.get('X-Upstream-Instance') || 'primary-01';
        const corrId = res.headers.get('X-Correlation-ID') || '--';

        // Increment counter
        this.trafficCounters[upstream] = (this.trafficCounters[upstream] || 0) + 1;

        // Add log row
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${new Date().toISOString().split('T')[1].slice(0, 8)}</td>
          <td><code>GET ${targetPath}</code></td>
          <td><span class="badge ${res.ok ? 'badge-healthy' : 'badge-down'}">${res.status}</span></td>
          <td>${elapsed} ms</td>
          <td><code>${upstream}</code></td>
          <td><small>${corrId.slice(0, 14)}...</small></td>
        `;
        if (trafficLog.children[0] && trafficLog.children[0].innerText.includes('No proxied')) {
          trafficLog.innerHTML = '';
        }
        trafficLog.prepend(row);
      } catch (err) {
        console.warn('Traffic error:', err);
      }
    }

    this.renderDistributionBars();
  }

  renderDistributionBars() {
    const container = document.getElementById('lb-distribution-bars');
    const total = Object.values(this.trafficCounters).reduce((a, b) => a + b, 0);

    if (total === 0) {
      container.innerHTML = '<p class="text-muted text-center" style="margin-top: 40px;">Send a traffic burst to observe replica node distributions.</p>';
      return;
    }

    let html = '';
    Object.entries(this.trafficCounters).forEach(([instId, hits]) => {
      const pct = Math.round((hits / total) * 100);
      html += `
        <div class="dist-bar-item">
          <div class="dist-label-row">
            <span><strong>${instId}</strong></span>
            <span>${hits} reqs (${pct}%)</span>
          </div>
          <div class="dist-bar-bg">
            <div class="dist-bar-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  clearTrafficCounters() {
    this.trafficCounters = {};
    this.renderDistributionBars();
    document.getElementById('traffic-log-body').innerHTML =
      '<tr><td colspan="6" class="text-center text-muted">No proxied traffic recorded yet.</td></tr>';
  }

  /* ------------------------------------------------------------------------
     4. CHAOS & CIRCUIT BREAKER
     ------------------------------------------------------------------------ */
  renderCircuitBreakers() {
    const services = ['user-service', 'catalog-service', 'order-service'];
    services.forEach(svc => {
      const cb = this.circuitBreakers[svc];
      const pill = document.getElementById(`cb-state-${svc}`);
      const failCount = document.getElementById(`cb-fail-${svc}`);
      const cooldown = document.getElementById(`cb-cooldown-${svc}`);
      const success = document.getElementById(`cb-success-${svc}`);

      if (cb && pill) {
        pill.innerText = cb.state;
        pill.className = `badge cb-state-pill ${cb.state === 'OPEN' ? 'badge-open' : 'badge-healthy'}`;
        failCount.innerText = `${cb.failure_count} / ${cb.failure_threshold}`;
        cooldown.innerText = `${cb.cooldown_remaining_seconds}s`;
        success.innerText = cb.consecutive_successes;
      }
    });
  }

  async chaosTrip(serviceName) {
    try {
      const res = await fetch('/api/v1/chaos/circuit/trip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service_name: serviceName })
      });
      if (res.ok) {
        await this.pollState();
      }
    } catch (err) {
      alert(`Failed to trip breaker: ${err.message}`);
    }
  }

  async chaosReset(serviceName) {
    try {
      const res = await fetch('/api/v1/chaos/circuit/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service_name: serviceName })
      });
      if (res.ok) {
        await this.pollState();
      }
    } catch (err) {
      alert(`Failed to reset breaker: ${err.message}`);
    }
  }

  /* ------------------------------------------------------------------------
     5. DISTRIBUTED SAGA WATERFALL
     ------------------------------------------------------------------------ */
  async executeSaga() {
    const userId = document.getElementById('saga-user-id').value;
    const sku = document.getElementById('saga-sku').value;
    const qty = parseInt(document.getElementById('saga-quantity').value, 10);
    const price = parseInt(document.getElementById('saga-price').value, 10);
    const simFail = document.getElementById('saga-sim-failure').checked;
    const container = document.getElementById('saga-waterfall-container');

    container.innerHTML = '<p class="text-muted text-center" style="margin-top: 40px;">Executing distributed checkout saga across microservices...</p>';

    try {
      const res = await fetch('/api/v1/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          items: [{ product_id: sku, quantity: qty, price_cents: price }],
          total_cents: qty * price,
          simulate_payment_failure: simFail
        })
      });

      const data = await res.json();
      const trace = data.trace || [];
      const isSuccess = data.success === true;

      let html = `
        <div style="margin-bottom: 12px; font-size: 12px;">
          <strong>ORDER RESULT:</strong>
          <span class="badge ${isSuccess ? 'badge-healthy' : 'badge-down'}">${data.status || 'FAILED'}</span>
          <span style="color: var(--text-muted); margin-left: 8px;">ID: ${data.order_id || (data.order && data.order.id) || '--'}</span>
        </div>
      `;

      trace.forEach(step => {
        let stepClass = 'step-completed';
        if (step.status === 'FAILED') stepClass = 'step-failed';
        else if (step.status === 'COMPENSATED') stepClass = 'step-compensated';

        html += `
          <div class="waterfall-step ${stepClass}">
            <div class="step-info">
              <span class="step-name">${step.step_name}</span>
              <span class="step-desc">${JSON.stringify(step.details || {})}</span>
            </div>
            <div>
              <span class="badge ${step.status === 'COMPLETED' ? 'badge-healthy' : (step.status === 'COMPENSATED' ? 'badge-degraded' : 'badge-down')}">${step.status}</span>
            </div>
          </div>
        `;
      });

      container.innerHTML = html;
      await this.loadBrokerData();
    } catch (err) {
      container.innerHTML = `<p class="text-center" style="color: var(--accent-red); margin-top: 40px;">Saga dispatch error: ${err.message}</p>`;
    }
  }

  /* ------------------------------------------------------------------------
     6. MESSAGE BROKER & DLQ INSPECTOR
     ------------------------------------------------------------------------ */
  async loadBrokerData() {
    const eventsBody = document.getElementById('broker-events-body');
    const dlqBody = document.getElementById('dlq-table-body');

    try {
      // 1. Fetch Events
      const evRes = await fetch('/api/v1/broker/events?topic=orders.events&limit=20');
      if (evRes.ok) {
        const evData = await evRes.json();
        const events = evData.events || [];
        if (events.length === 0) {
          eventsBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No published domain events recorded.</td></tr>';
        } else {
          let rows = '';
          events.forEach(e => {
            rows += `
              <tr>
                <td><code>${e.id.slice(0, 14)}...</code></td>
                <td><span class="badge badge-healthy">${e.type}</span></td>
                <td>${e.source}</td>
                <td>${e.time ? e.time.split('T')[1].slice(0, 8) : '--'}</td>
                <td><small>${e.correlation_id ? e.correlation_id.slice(0, 12) + '...' : '--'}</small></td>
                <td><button class="btn btn-sm btn-secondary" onclick="alert('${JSON.stringify(e.data).replace(/'/g, "\\'")}')">VIEW JSON</button></td>
              </tr>
            `;
          });
          eventsBody.innerHTML = rows;
        }
      }

      // 2. Fetch DLQ
      const dlqRes = await fetch('/api/v1/broker/dlq');
      if (dlqRes.ok) {
        const dlqData = await dlqRes.json();
        const dlq = dlqData.dlq || [];
        if (dlq.length === 0) {
          dlqBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Dead-Letter Queue is empty. No poisoned messages.</td></tr>';
        } else {
          let rows = '';
          dlq.forEach(msg => {
            rows += `
              <tr>
                <td><code>${msg.id}</code></td>
                <td>${msg.topic}</td>
                <td>${msg.consumer_id}</td>
                <td><span class="badge badge-down">${msg.retry_count} retries</span></td>
                <td>${msg.failed_at ? msg.failed_at.split('T')[1].slice(0, 8) : '--'}</td>
                <td style="color: var(--accent-red);"><small>${msg.error_reason}</small></td>
                <td><button class="btn btn-sm btn-primary" onclick="app.replayDlqMessage('${msg.id}')">REPLAY</button></td>
              </tr>
            `;
          });
          dlqBody.innerHTML = rows;
        }
      }
    } catch (err) {
      console.warn('Failed to load broker data:', err);
    }
  }

  async replayDlqMessage(dlqId) {
    try {
      const res = await fetch(`/api/v1/broker/dlq/${dlqId}/replay`, { method: 'POST' });
      if (res.ok) {
        await this.loadBrokerData();
      } else {
        alert('Replay failed: consumer still rejected message');
      }
    } catch (err) {
      alert(`Replay error: ${err.message}`);
    }
  }

  async clearDlq() {
    try {
      const res = await fetch('/api/v1/broker/dlq', { method: 'DELETE' });
      if (res.ok) {
        await this.loadBrokerData();
      }
    } catch (err) {
      alert(`Clear DLQ error: ${err.message}`);
    }
  }
}

// Global App Instance
const app = new PulseMeshApp();
window.addEventListener('DOMContentLoaded', () => {
  app.init();
});
