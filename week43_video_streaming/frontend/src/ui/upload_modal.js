/**
 * Upload modal and ingestion UI controller for PulseStream.
 * Handles drag-and-drop file ingestion, multipart form uploads,
 * real-time transcoding job polling, and stage telemetry tracking.
 */

export class UploadModal {
    constructor(modalElement) {
        this.modal = modalElement;
        this.form = modalElement.querySelector("#uploadForm");
        this.dropZone = modalElement.querySelector("#dropZone");
        this.fileInput = modalElement.querySelector("#videoFileInput");
        this.fileInfo = modalElement.querySelector("#fileSelectionInfo");
        this.closeBtn = modalElement.querySelector("#closeModalBtn");
        this.cancelBtn = modalElement.querySelector("#cancelUploadBtn");
        this.submitBtn = modalElement.querySelector("#submitUploadBtn");
        this.categorySelect = modalElement.querySelector("#videoCategory");
        this.titleInput = modalElement.querySelector("#videoTitle");
        this.descInput = modalElement.querySelector("#videoDescription");
        this.progressContainer = modalElement.querySelector("#uploadProgressContainer");
        this.progressBarFill = modalElement.querySelector("#progressBarFill");
        this.progressPercent = modalElement.querySelector("#progressPercent");
        this.progressStage = modalElement.querySelector("#progressStage");

        this.selectedFile = null;
        this.pollingTimer = null;
        this.onUploadCompleteCallback = null;

        this.bindEvents();
    }

    bindEvents() {
        if (this.closeBtn) {
            this.closeBtn.addEventListener("click", () => this.hide());
        }
        if (this.cancelBtn) {
            this.cancelBtn.addEventListener("click", () => this.hide());
        }
        if (this.dropZone) {
            this.dropZone.addEventListener("click", () => this.fileInput && this.fileInput.click());
            this.dropZone.addEventListener("dragover", (e) => {
                e.preventDefault();
                this.dropZone.classList.add("dragover");
            });
            this.dropZone.addEventListener("dragleave", () => {
                this.dropZone.classList.remove("dragover");
            });
            this.dropZone.addEventListener("drop", (e) => {
                e.preventDefault();
                this.dropZone.classList.remove("dragover");
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    this.handleFileSelected(e.dataTransfer.files[0]);
                }
            });
        }
        if (this.fileInput) {
            this.fileInput.addEventListener("change", (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    this.handleFileSelected(e.target.files[0]);
                }
            });
        }
        if (this.form) {
            this.form.addEventListener("submit", (e) => this.handleSubmit(e));
        }
    }

    populateCategories(categories) {
        if (!this.categorySelect) return;
        this.categorySelect.innerHTML = '<option value="">Select Category (Optional)</option>';
        categories.forEach((cat) => {
            const opt = document.createElement("option");
            opt.value = cat.id;
            opt.textContent = cat.name;
            this.categorySelect.appendChild(opt);
        });
    }

    handleFileSelected(file) {
        this.selectedFile = file;
        if (this.fileInfo) {
            const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
            this.fileInfo.textContent = `Selected: ${file.name} (${sizeMb} MB)`;
            this.fileInfo.classList.remove("hidden");
        }
        if (this.titleInput && !this.titleInput.value) {
            this.titleInput.value = file.name.replace(/\.[^/.]+$/, "");
        }
    }

    async handleSubmit(event) {
        event.preventDefault();

        if (!this.selectedFile) {
            alert("Please select a video file to upload.");
            return;
        }

        const formData = new FormData();
        formData.append("video", this.selectedFile);
        formData.append("title", (this.titleInput ? this.titleInput.value : "").trim());
        if (this.categorySelect && this.categorySelect.value) {
            formData.append("category_id", this.categorySelect.value);
        }
        if (this.descInput && this.descInput.value) {
            formData.append("description", this.descInput.value.trim());
        }

        this.setUploadingState(true);
        this.updateProgress(10, "Uploading video file to server...");

        try {
            const response = await fetch("/api/videos/upload", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `Upload failed with HTTP ${response.status}`);
            }

            const data = await response.json();
            const { video, job } = data;

            this.updateProgress(20, "Video uploaded. Enqueueing transcoding...");
            if (job && job.id) {
                this.pollJobProgress(job.id, video);
            } else {
                this.finishUpload(video);
            }
        } catch (err) {
            this.setUploadingState(false);
            alert(`Error uploading video: ${err.message}`);
        }
    }

    pollJobProgress(jobId, video) {
        this.stopPolling();

        const stageDescriptions = {
            queued: "Queued for transcoding...",
            inspecting: "Inspecting container and extracting metadata (15%)...",
            thumbnailing: "Generating poster thumbnail (30%)...",
            packaging_hls: "Packaging multi-bitrate HLS streams (50%)...",
            saving_renditions: "Saving ABR stream renditions (85%)...",
            completed: "Transcoding complete! Ready to stream (100%)."
        };

        this.pollingTimer = setInterval(async () => {
            try {
                const res = await fetch(`/api/jobs/${jobId}`);
                if (!res.ok) return;

                const job = await res.json();
                const progress = job.progress || 0;
                const stageText = stageDescriptions[job.stage] || stageDescriptions[job.status] || `Processing (${progress}%)...`;

                this.updateProgress(progress, stageText);

                if (job.status === "completed") {
                    this.stopPolling();
                    setTimeout(() => {
                        this.finishUpload(video);
                    }, 600);
                } else if (job.status === "failed") {
                    this.stopPolling();
                    this.setUploadingState(false);
                    alert(`Transcoding failed: ${job.error_message || "Unknown error"}`);
                }
            } catch {
                // Transient polling errors are retried on next tick
            }
        }, 600);
    }

    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    }

    updateProgress(percent, stageText) {
        if (this.progressBarFill) {
            this.progressBarFill.style.width = `${Math.min(100, percent)}%`;
        }
        if (this.progressPercent) {
            this.progressPercent.textContent = `${Math.min(100, Math.round(percent))}%`;
        }
        if (this.progressStage && stageText) {
            this.progressStage.textContent = stageText;
        }
    }

    setUploadingState(isUploading) {
        if (this.progressContainer) {
            this.progressContainer.classList.toggle("hidden", !isUploading);
        }
        if (this.submitBtn) {
            this.submitBtn.disabled = isUploading;
        }
        if (this.cancelBtn) {
            this.cancelBtn.disabled = isUploading;
        }
    }

    finishUpload(video) {
        this.hide();
        if (this.onUploadCompleteCallback) {
            this.onUploadCompleteCallback(video);
        }
    }

    show() {
        if (this.modal) {
            this.modal.classList.remove("hidden");
        }
    }

    hide() {
        this.stopPolling();
        if (this.modal) {
            this.modal.classList.add("hidden");
            this.reset();
        }
    }

    reset() {
        if (this.form) this.form.reset();
        this.selectedFile = null;
        if (this.fileInfo) this.fileInfo.classList.add("hidden");
        if (this.progressContainer) this.progressContainer.classList.add("hidden");
        if (this.progressBarFill) this.progressBarFill.style.width = "0%";
        if (this.progressPercent) this.progressPercent.textContent = "0%";
        if (this.submitBtn) this.submitBtn.disabled = false;
        if (this.cancelBtn) this.cancelBtn.disabled = false;
    }
}
