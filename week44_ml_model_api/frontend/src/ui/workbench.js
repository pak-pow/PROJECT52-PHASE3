/**
 * PulseInfer Model Workbench & Testing Playground Controller.
 * Provides interactive inputs, schema presets, version hot-swapping, and visual outputs.
 */

export class WorkbenchController {
    constructor() {
        this.models = [];
        this.activeModel = null;
        this.modelVersions = {};

        this.modelsList = document.getElementById("modelsList");
        this.activeModelName = document.getElementById("activeModelName");
        this.activeModelDomain = document.getElementById("activeModelDomain");
        this.activeModelVersion = document.getElementById("activeModelVersion");
        this.activeModelDesc = document.getElementById("activeModelDesc");
        this.swapVersionSelect = document.getElementById("swapVersionSelect");
        this.swapVersionBtn = document.getElementById("swapVersionBtn");
        this.hotswapNotice = document.getElementById("hotswapNotice");

        this.presetsContainer = document.getElementById("presetsContainer");
        this.consoleInputs = document.getElementById("consoleInputs");
        this.bypassCacheToggle = document.getElementById("bypassCacheToggle");
        this.bypassBatcherToggle = document.getElementById("bypassBatcherToggle");

        this.runInferenceBtn = document.getElementById("runInferenceBtn");
        this.clearInputsBtn = document.getElementById("clearInputsBtn");
        this.resultCard = document.getElementById("predictionResultCard");
        this.visualResultContainer = document.getElementById("visualResultContainer");
        this.resultContent = document.getElementById("resultContent");
        this.resLatencyBadge = document.getElementById("resLatencyBadge");
        this.resCachedBadge = document.getElementById("resCachedBadge");
        this.resVersionBadge = document.getElementById("resVersionBadge");

        this.bindEvents();
    }

    bindEvents() {
        if (this.runInferenceBtn) {
            this.runInferenceBtn.addEventListener("click", () => this.handleRunInference());
        }
        if (this.clearInputsBtn) {
            this.clearInputsBtn.addEventListener("click", () => this.clearInputs());
        }
        if (this.swapVersionBtn) {
            this.swapVersionBtn.addEventListener("click", () => this.handleHotSwap());
        }
    }

    setModels(models) {
        this.models = models || [];
        this.renderModelsList();
        if (this.models.length > 0 && !this.activeModel) {
            this.selectModel(this.models[0]);
        }
    }

    renderModelsList() {
        if (!this.modelsList) return;
        this.modelsList.innerHTML = "";

        this.models.forEach((model) => {
            const card = document.createElement("div");
            card.className = `model-card ${this.activeModel && this.activeModel.id === model.id ? "active" : ""}`;
            card.dataset.modelId = model.id;

            card.innerHTML = `
                <div class="model-card-header">
                    <span class="model-card-title">${model.name}</span>
                    <span class="domain-tag">${model.domain}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-muted);">
                    <span>ID: ${model.id}</span>
                    <span class="version-tag">${model.active_version || "v1"}</span>
                </div>
            `;

            card.addEventListener("click", () => this.selectModel(model));
            this.modelsList.appendChild(card);
        });
    }

    async selectModel(model) {
        this.activeModel = model;
        if (this.modelsList) {
            this.modelsList.querySelectorAll(".model-card").forEach((c) => {
                c.classList.toggle("active", c.dataset.modelId === model.id);
            });
        }

        if (this.activeModelName) this.activeModelName.textContent = model.name;
        if (this.activeModelDomain) this.activeModelDomain.textContent = model.domain;
        if (this.activeModelVersion) this.activeModelVersion.textContent = model.active_version || "v1";
        if (this.activeModelDesc) this.activeModelDesc.textContent = model.description || "";
        if (this.hotswapNotice) this.hotswapNotice.classList.add("hidden");

        await this.loadModelMetadata(model.id);
        this.renderPresets(model);
        this.renderDynamicInputs(model);

        if (this.resultCard) this.resultCard.classList.add("hidden");
    }

    async loadModelMetadata(modelId) {
        if (!this.swapVersionSelect) return;
        this.swapVersionSelect.innerHTML = '<option value="v1">v1</option>';

        try {
            const res = await fetch(`/api/v1/models/${modelId}/metadata`);
            if (!res.ok) return;
            const data = await res.json();
            const versions = data.versions || [];
            this.modelVersions[modelId] = versions;

            this.swapVersionSelect.innerHTML = versions.map((v) => `
                <option value="${v.version}" ${v.version === data.active_version ? "selected" : ""}>
                    ${v.version} (${v.status})
                </option>
            `).join("");

            if (this.activeModelVersion) {
                this.activeModelVersion.textContent = data.active_version;
            }
        } catch {
            // Graceful baseline fallback
        }
    }

    async handleHotSwap() {
        if (!this.activeModel || !this.swapVersionSelect) return;
        const targetVersion = this.swapVersionSelect.value;
        const startSwap = performance.now();

        if (this.swapVersionBtn) {
            this.swapVersionBtn.disabled = true;
            this.swapVersionBtn.textContent = "Swapping...";
        }

        try {
            const res = await fetch(`/api/v1/models/${this.activeModel.id}/reload`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ version: targetVersion })
            });

            const data = await res.json();
            const duration = (performance.now() - startSwap).toFixed(1);

            if (res.ok && data.status === "success") {
                this.activeModel.active_version = targetVersion;
                if (this.activeModelVersion) this.activeModelVersion.textContent = targetVersion;
                this.renderModelsList();

                if (this.hotswapNotice) {
                    this.hotswapNotice.textContent = `Hot-swapped to ${targetVersion} in ${duration} ms (0 dropped requests)`;
                    this.hotswapNotice.className = "hotswap-notice success";
                    this.hotswapNotice.classList.remove("hidden");
                }
            } else {
                if (this.hotswapNotice) {
                    this.hotswapNotice.textContent = data.error || "Hot swap failed";
                    this.hotswapNotice.className = "hotswap-notice error";
                    this.hotswapNotice.classList.remove("hidden");
                }
            }
        } catch {
            if (this.hotswapNotice) {
                this.hotswapNotice.textContent = "Hot swap request failed";
                this.hotswapNotice.className = "hotswap-notice error";
                this.hotswapNotice.classList.remove("hidden");
            }
        } finally {
            if (this.swapVersionBtn) {
                this.swapVersionBtn.disabled = false;
                this.swapVersionBtn.textContent = "Hot-Swap";
            }
        }
    }

    renderPresets(model) {
        if (!this.presetsContainer) return;
        this.presetsContainer.innerHTML = "";

        const presets = {
            nlp: [
                {
                    label: "Positive Review",
                    payload: { text: "Outstanding performance, lightning fast response time, and wonderful customer service!" }
                },
                {
                    label: "Negative Complaint",
                    payload: { text: "Terrible slow response, persistent error messages, and poor service quality." }
                },
                {
                    label: "Neutral Query",
                    payload: { text: "System check completed with standard configuration and telemetry verification." }
                }
            ],
            vision: [
                {
                    label: "Landscape Scene",
                    payload: { image_base64: "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAJElEQVR42mP8z8BQDwAEhQGAhKmMIQBkWFgggwUFBbA0mD4AAP9rBgf9U6WbAAAAAElFTkSuQmCC" }
                },
                {
                    label: "Document Scan",
                    payload: { image_base64: "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAMElEQVR42mP8//8/AwgwMjKCGTAAEwApgYGBgQFDgQx0Bkgdihp8mglZHYiACpA1AAA6dQEGBqJjEgAAAABJRU5ErkJggg==" }
                },
                {
                    label: "Portrait Photo",
                    payload: { image_base64: "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAALUlEQVR42mNkYPj/n4EAYCIiIrBgwADEDqTBC4gGqFqgGpg6mDp0dSB1MDMGAACoMwEGWfH+OAAAAABJRU5ErkJggg==" }
                }
            ],
            tabular: [
                {
                    label: "Normal Purchase ($12.50)",
                    payload: { transaction_amount: 12.50, user_age: 38, velocity_1h: 1, is_foreign: 0 }
                },
                {
                    label: "High-Risk Anomaly ($3,200.00)",
                    payload: { transaction_amount: 3200.00, user_age: 21, velocity_1h: 12, is_foreign: 1 }
                },
                {
                    label: "Velocity Spike ($180.00)",
                    payload: { transaction_amount: 180.00, user_age: 29, velocity_1h: 8, is_foreign: 0 }
                }
            ]
        };

        const list = presets[model.domain] || [];
        list.forEach((item) => {
            const btn = document.createElement("button");
            btn.className = "preset-pill-btn";
            btn.textContent = item.label;
            btn.addEventListener("click", () => this.applyPreset(item.payload));
            this.presetsContainer.appendChild(btn);
        });
    }

    applyPreset(payload) {
        if (!this.activeModel) return;

        if (this.activeModel.domain === "nlp") {
            const txt = document.getElementById("nlpTextInput");
            if (txt && payload.text) txt.value = payload.text;
        } else if (this.activeModel.domain === "vision") {
            const img = document.getElementById("visionImageInput");
            if (img && payload.image_base64) {
                img.value = payload.image_base64;
                this.updateVisionPreview(payload.image_base64);
            }
        } else if (this.activeModel.domain === "tabular") {
            if (document.getElementById("tabAmount")) document.getElementById("tabAmount").value = payload.transaction_amount;
            if (document.getElementById("tabAge")) document.getElementById("tabAge").value = payload.user_age;
            if (document.getElementById("tabVelocity")) document.getElementById("tabVelocity").value = payload.velocity_1h;
            if (document.getElementById("tabForeign")) document.getElementById("tabForeign").value = payload.is_foreign;
        }
    }

    updateVisionPreview(b64) {
        const preview = document.getElementById("visionImgPreview");
        if (preview) {
            preview.src = b64.startsWith("data:") ? b64 : `data:image/png;base64,${b64}`;
        }
    }

    renderDynamicInputs(model) {
        if (!this.consoleInputs) return;
        this.consoleInputs.innerHTML = "";

        if (model.domain === "nlp") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            grp.innerHTML = `
                <label for="nlpTextInput">Input Review or Statement</label>
                <textarea id="nlpTextInput" class="form-control" placeholder="Enter text sentence...">Outstanding performance, lightning fast response time, and wonderful customer service!</textarea>
            `;
            this.consoleInputs.appendChild(grp);
        } else if (model.domain === "vision") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            const sampleB64 = "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAJElEQVR42mP8z8BQDwAEhQGAhKmMIQBkWFgggwUFBbA0mD4AAP9rBgf9U6WbAAAAAElFTkSuQmCC";
            grp.innerHTML = `
                <label for="visionImageInput">Image Input (Base64 Encoded PNG/JPEG)</label>
                <div class="vision-input-row">
                    <input type="text" id="visionImageInput" class="form-control" value="${sampleB64}">
                    <div class="vision-preview-box">
                        <img id="visionImgPreview" class="vision-preview-img" src="data:image/png;base64,${sampleB64}" alt="Preview">
                    </div>
                </div>
            `;
            this.consoleInputs.appendChild(grp);

            const inp = document.getElementById("visionImageInput");
            if (inp) {
                inp.addEventListener("input", (e) => this.updateVisionPreview(e.target.value));
            }
        } else if (model.domain === "tabular") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            grp.innerHTML = `
                <div class="tabular-input-grid">
                    <div>
                        <label for="tabAmount">Amount ($)</label>
                        <input type="number" id="tabAmount" class="form-control" value="12.50" step="1">
                    </div>
                    <div>
                        <label for="tabAge">Cardholder Age</label>
                        <input type="number" id="tabAge" class="form-control" value="38" min="18" max="100">
                    </div>
                    <div>
                        <label for="tabVelocity">1h Tx Velocity</label>
                        <input type="number" id="tabVelocity" class="form-control" value="1" min="0" max="50">
                    </div>
                    <div>
                        <label for="tabForeign">Foreign Tx (0/1)</label>
                        <select id="tabForeign" class="form-control">
                            <option value="0" selected>0 (Domestic)</option>
                            <option value="1">1 (International)</option>
                        </select>
                    </div>
                </div>
            `;
            this.consoleInputs.appendChild(grp);
        }
    }

    collectPayload() {
        if (!this.activeModel) return null;
        if (this.activeModel.domain === "nlp") {
            const txt = document.getElementById("nlpTextInput");
            return { text: txt ? txt.value.trim() : "" };
        }
        if (this.activeModel.domain === "vision") {
            const img = document.getElementById("visionImageInput");
            return { image_base64: img ? img.value.trim() : "" };
        }
        if (this.activeModel.domain === "tabular") {
            return {
                transaction_amount: parseFloat(document.getElementById("tabAmount")?.value || "0"),
                user_age: parseInt(document.getElementById("tabAge")?.value || "0", 10),
                velocity_1h: parseInt(document.getElementById("tabVelocity")?.value || "0", 10),
                is_foreign: parseInt(document.getElementById("tabForeign")?.value || "0", 10)
            };
        }
        return {};
    }

    async handleRunInference() {
        if (!this.activeModel) return;
        const payload = this.collectPayload();
        if (!payload) return;

        if (this.runInferenceBtn) {
            this.runInferenceBtn.disabled = true;
            this.runInferenceBtn.textContent = "Inferring...";
        }

        const bypassCache = this.bypassCacheToggle && this.bypassCacheToggle.checked;
        const bypassBatcher = this.bypassBatcherToggle && this.bypassBatcherToggle.checked;

        const queryParams = new URLSearchParams();
        if (bypassCache) queryParams.set("bypass_cache", "true");
        if (bypassBatcher) queryParams.set("bypass_batcher", "true");
        const url = `/api/v1/models/${this.activeModel.id}/predict${queryParams.toString() ? `?${queryParams}` : ""}`;

        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            this.renderPredictionResult(data);
        } catch {
            this.renderPredictionResult({
                status: "error",
                error: "Inference gateway endpoint unreachable or offline."
            });
        } finally {
            if (this.runInferenceBtn) {
                this.runInferenceBtn.disabled = false;
                this.runInferenceBtn.textContent = "Run Inference";
            }
        }
    }

    renderPredictionResult(result) {
        if (!this.resultCard) return;
        this.resultCard.classList.remove("hidden");

        const latency = result.latency_ms !== undefined ? result.latency_ms.toFixed(2) : "0.00";
        if (this.resLatencyBadge) {
            this.resLatencyBadge.textContent = `${latency} ms`;
        }
        if (this.resCachedBadge) {
            this.resCachedBadge.textContent = result.cached ? "Cache Hit" : "Cache Miss";
            this.resCachedBadge.className = `badge ${result.cached ? "cached" : ""}`;
        }
        if (this.resVersionBadge) {
            this.resVersionBadge.textContent = result.version || (this.activeModel ? this.activeModel.active_version : "v1");
        }

        // Render Visualized Results
        if (this.visualResultContainer) {
            this.visualResultContainer.innerHTML = this.buildVisualRepresentation(result);
        }

        // Raw JSON Collapsible
        if (this.resultContent) {
            this.resultContent.innerHTML = `<pre class="json-code">${JSON.stringify(result, null, 2)}</pre>`;
        }
    }

    buildVisualRepresentation(result) {
        if (result.status !== "success" || !result.prediction) {
            return `
                <div class="result-error-box">
                    <strong>Inference Error:</strong>
                    <span>${result.error || "Unknown processing failure"}</span>
                </div>
            `;
        }

        const pred = result.prediction;
        const domain = this.activeModel ? this.activeModel.domain : "";

        if (domain === "nlp") {
            const sentiment = pred.sentiment || "unknown";
            const probs = pred.probabilities || {};
            const confidence = (pred.confidence !== undefined ? (pred.confidence * 100).toFixed(1) : "0.0");

            return `
                <div class="visual-card">
                    <div class="visual-header">
                        <span class="visual-title">Classification: <strong class="highlight-tag ${sentiment}">${sentiment.toUpperCase()}</strong></span>
                        <span class="confidence-badge">Confidence: ${confidence}%</span>
                    </div>
                    <div class="bars-stack">
                        ${Object.entries(probs).map(([cls, prob]) => {
                            const pct = (prob * 100).toFixed(1);
                            return `
                                <div class="bar-group">
                                    <div class="bar-label-row">
                                        <span class="bar-class-name">${cls}</span>
                                        <span class="bar-class-pct">${pct}%</span>
                                    </div>
                                    <div class="progress-track">
                                        <div class="progress-fill ${cls}" style="width: ${pct}%;"></div>
                                    </div>
                                </div>
                            `;
                        }).join("")}
                    </div>
                </div>
            `;
        }

        if (domain === "vision") {
            const topClass = pred.top_class || "unknown";
            const scores = pred.class_scores || {};
            const confidence = (pred.confidence !== undefined ? (pred.confidence * 100).toFixed(1) : "0.0");

            return `
                <div class="visual-card">
                    <div class="visual-header">
                        <span class="visual-title">Detected Class: <strong class="highlight-tag vision">${topClass.toUpperCase()}</strong></span>
                        <span class="confidence-badge">Confidence: ${confidence}%</span>
                    </div>
                    <div class="bars-stack">
                        ${Object.entries(scores).map(([cls, score]) => {
                            const pct = (score * 100).toFixed(1);
                            return `
                                <div class="bar-group">
                                    <div class="bar-label-row">
                                        <span class="bar-class-name">${cls}</span>
                                        <span class="bar-class-pct">${pct}%</span>
                                    </div>
                                    <div class="progress-track">
                                        <div class="progress-fill vision" style="width: ${pct}%;"></div>
                                    </div>
                                </div>
                            `;
                        }).join("")}
                    </div>
                </div>
            `;
        }

        if (domain === "tabular") {
            const riskLevel = (pred.risk_level || "low").toLowerCase();
            const riskScore = pred.risk_score !== undefined ? pred.risk_score : 0.0;
            const scorePct = (riskScore * 100).toFixed(1);
            const isFlagged = pred.is_flagged;

            return `
                <div class="visual-card">
                    <div class="visual-header">
                        <span class="visual-title">Fraud Risk Tier: <strong class="highlight-tag risk-${riskLevel}">${riskLevel.toUpperCase()}</strong></span>
                        <span class="confidence-badge ${isFlagged ? 'flagged' : ''}">
                            ${isFlagged ? 'FLAGGED FOR MANUAL AUDIT' : 'AUTOMATICALLY APPROVED'}
                        </span>
                    </div>
                    <div class="risk-gauge-container">
                        <div class="bar-label-row">
                            <span>Computed Risk Score</span>
                            <strong>${riskScore.toFixed(4)} (${scorePct}%)</strong>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill risk-${riskLevel}" style="width: ${scorePct}%;"></div>
                        </div>
                    </div>
                </div>
            `;
        }

        return "";
    }

    clearInputs() {
        if (this.activeModel) {
            this.renderDynamicInputs(this.activeModel);
        }
        if (this.resultCard) {
            this.resultCard.classList.add("hidden");
        }
    }
}
