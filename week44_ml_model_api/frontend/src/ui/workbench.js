/**
 * PulseInfer Model Workbench & Testing Playground Controller.
 */

export class WorkbenchController {
    constructor() {
        this.models = [];
        this.activeModel = null;

        this.modelsList = document.getElementById("modelsList");
        this.activeModelName = document.getElementById("activeModelName");
        this.activeModelDomain = document.getElementById("activeModelDomain");
        this.activeModelVersion = document.getElementById("activeModelVersion");
        this.activeModelDesc = document.getElementById("activeModelDesc");
        this.consoleInputs = document.getElementById("consoleInputs");
        this.runInferenceBtn = document.getElementById("runInferenceBtn");
        this.clearInputsBtn = document.getElementById("clearInputsBtn");
        this.resultCard = document.getElementById("predictionResultCard");
        this.resultContent = document.getElementById("resultContent");
        this.resLatencyBadge = document.getElementById("resLatencyBadge");
        this.resCachedBadge = document.getElementById("resCachedBadge");

        this.bindEvents();
    }

    bindEvents() {
        if (this.runInferenceBtn) {
            this.runInferenceBtn.addEventListener("click", () => this.handleRunInference());
        }
        if (this.clearInputsBtn) {
            this.clearInputsBtn.addEventListener("click", () => this.clearInputs());
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

    selectModel(model) {
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

        this.renderDynamicInputs(model);
        if (this.resultCard) this.resultCard.classList.add("hidden");
    }

    renderDynamicInputs(model) {
        if (!this.consoleInputs) return;
        this.consoleInputs.innerHTML = "";

        if (model.domain === "nlp") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            grp.innerHTML = `
                <label for="nlpTextInput">Input Text Sentence or Review</label>
                <textarea id="nlpTextInput" class="form-control" placeholder="e.g. Excellent service and lightning fast delivery!">The product quality is excellent and the customer support is great!</textarea>
            `;
            this.consoleInputs.appendChild(grp);
        } else if (model.domain === "vision") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            grp.innerHTML = `
                <label for="visionImageInput">Image Input (Synthetic Vector or Base64)</label>
                <input type="text" id="visionImageInput" class="form-control" value="data:image/png;base64,sample_raw_pixel_data" placeholder="Base64 encoded image string">
                <span style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Supports normalized RGB raw arrays and base64 payloads.</span>
            `;
            this.consoleInputs.appendChild(grp);
        } else if (model.domain === "tabular") {
            const grp = document.createElement("div");
            grp.className = "form-group";
            grp.innerHTML = `
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem;">
                    <div>
                        <label>Amount ($)</label>
                        <input type="number" id="tabAmount" class="form-control" value="150.00" step="10">
                    </div>
                    <div>
                        <label>User Age</label>
                        <input type="number" id="tabAge" class="form-control" value="35" min="18" max="100">
                    </div>
                    <div>
                        <label>1h Velocity</label>
                        <input type="number" id="tabVelocity" class="form-control" value="2" min="0" max="50">
                    </div>
                    <div>
                        <label>Foreign Tx (0/1)</label>
                        <input type="number" id="tabForeign" class="form-control" value="0" min="0" max="1">
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
            return { text: txt ? txt.value : "" };
        }
        if (this.activeModel.domain === "vision") {
            const img = document.getElementById("visionImageInput");
            return { image_base64: img ? img.value : "" };
        }
        if (this.activeModel.domain === "tabular") {
            const amount = parseFloat(document.getElementById("tabAmount")?.value || "0");
            const age = parseInt(document.getElementById("tabAge")?.value || "0", 10);
            const vel = parseInt(document.getElementById("tabVelocity")?.value || "0", 10);
            const foreign = parseInt(document.getElementById("tabForeign")?.value || "0", 10);
            return {
                transaction_amount: amount,
                user_age: age,
                velocity_1h: vel,
                is_foreign: foreign
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

        try {
            const res = await fetch(`/api/v1/models/${this.activeModel.id}/predict`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            this.renderPredictionResult(data);
        } catch {
            this.renderPredictionResult({
                status: "error",
                error: "Inference endpoint offline or unreachable in baseline state."
            });
        } finally {
            if (this.runInferenceBtn) {
                this.runInferenceBtn.disabled = false;
                this.runInferenceBtn.textContent = "Run Inference";
            }
        }
    }

    renderPredictionResult(result) {
        if (!this.resultCard || !this.resultContent) return;
        this.resultCard.classList.remove("hidden");

        if (this.resLatencyBadge) {
            this.resLatencyBadge.textContent = `${result.latency_ms ? result.latency_ms.toFixed(2) : "0.00"} ms`;
        }
        if (this.resCachedBadge) {
            this.resCachedBadge.textContent = result.cached ? "Cache Hit" : "Cache Miss";
            this.resCachedBadge.className = `badge ${result.cached ? "cached" : ""}`;
        }

        this.resultContent.innerHTML = `<pre style="font-size: 0.85rem; color: #a5f3fc; overflow-x: auto; background: #0c121e; padding: 1rem; border-radius: 6px;">${JSON.stringify(result, null, 2)}</pre>`;
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
