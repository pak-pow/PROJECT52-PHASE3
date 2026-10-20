/**
 * Upload modal and ingestion UI controller for PulseStream.
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
        this.progressContainer = modalElement.querySelector("#uploadProgressContainer");
        this.progressBarFill = modalElement.querySelector("#progressBarFill");
        this.progressPercent = modalElement.querySelector("#progressPercent");
        this.progressStage = modalElement.querySelector("#progressStage");
        this.selectedFile = null;
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
    }

    handleFileSelected(file) {
        this.selectedFile = file;
        if (this.fileInfo) {
            this.fileInfo.textContent = `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
            this.fileInfo.classList.remove("hidden");
        }
        const titleInput = this.modal.querySelector("#videoTitle");
        if (titleInput && !titleInput.value) {
            titleInput.value = file.name.replace(/\.[^/.]+$/, "");
        }
    }

    show() {
        if (this.modal) {
            this.modal.classList.remove("hidden");
        }
    }

    hide() {
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
        if (this.submitBtn) this.submitBtn.disabled = false;
    }
}
