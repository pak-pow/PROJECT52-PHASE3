/**
 * Main dashboard coordinator organizing health monitoring, benchmarks, and task CRUD.
 * 
 * The controller handles continuous background polling and mounts sub-components.
 */

import { opsApi } from '../api/opsApi.js';
import { ServiceGrid } from '../components/serviceGrid.js';
import { BenchmarkCard } from '../components/benchmarkCard.js';
import { TaskManager } from '../components/taskManager.js';

export class DashboardPage {
  constructor(appContainer) {
    this.appContainer = appContainer;
    this.pollInterval = null;
  }

  init() {
    this.renderLayout();

    const serviceGridContainer = this.appContainer.querySelector('#service-grid-slot');
    const benchmarkContainer = this.appContainer.querySelector('#benchmark-slot');
    const taskManagerContainer = this.appContainer.querySelector('#task-manager-slot');

    this.serviceGrid = new ServiceGrid(serviceGridContainer);
    this.serviceGrid.render();

    this.benchmarkCard = new BenchmarkCard(benchmarkContainer);
    this.benchmarkCard.render();

    this.taskManager = new TaskManager(taskManagerContainer);
    this.taskManager.render();

    // Start background telemetry polling (every 5 seconds)
    this.pollTelemetry();
    this.pollInterval = setInterval(() => this.pollTelemetry(), 5000);
  }

  renderLayout() {
    this.appContainer.innerHTML = `
      <div class="container">
        <header>
          <div class="badge-pill">
            <span class="status-dot"></span> Multi-Container Topology Active
          </div>
          <h1>Docker Pulse Operations Hub</h1>
          <p class="subtitle">Real-time telemetry monitor and task orchestrator across Nginx, Flask API, PostgreSQL 16, and Redis 7 Cache.</p>
        </header>

        <!-- Service Topology Grid -->
        <div id="service-grid-slot"></div>

        <!-- Comparative Benchmark Component -->
        <div id="benchmark-slot"></div>

        <!-- Task Manager Component -->
        <div id="task-manager-slot"></div>

        <footer>
          Project 52 — Phase 3 (Production) &nbsp;|&nbsp; Week 38: Containerized App with Docker
        </footer>
      </div>
    `;
  }

  async pollTelemetry() {
    try {
      const [nginxOk, liveness, readiness] = await Promise.all([
        opsApi.checkNginxHealth(),
        opsApi.getLiveness().catch(() => null),
        opsApi.getReadiness().catch(() => null),
      ]);

      if (this.serviceGrid) {
        this.serviceGrid.updateTelemetry(readiness, liveness, nginxOk);
      }
    } catch (err) {
      console.warn('[Docker Pulse] Telemetry poll encountered error:', err);
    }
  }

  destroy() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  }
}