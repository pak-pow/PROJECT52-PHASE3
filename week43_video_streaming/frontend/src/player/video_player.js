/**
 * PulseStream Video Player UI wrapper.
 */

import { HLSController } from "./hls_controller.js";

export class PulsePlayer {
    constructor(wrapperElement) {
        this.wrapper = wrapperElement;
        this.video = wrapperElement.querySelector("video");
        this.progressBar = wrapperElement.querySelector("#progressBar");
        this.bufferedBar = wrapperElement.querySelector("#bufferedBar");
        this.playPauseBtn = wrapperElement.querySelector("#playPauseBtn");
        this.muteBtn = wrapperElement.querySelector("#muteBtn");
        this.volumeBar = wrapperElement.querySelector("#volumeBar");
        this.timeDisplay = wrapperElement.querySelector("#timeDisplay");
        this.speedSelect = wrapperElement.querySelector("#speedSelect");
        this.qualitySelect = wrapperElement.querySelector("#qualitySelect");
        this.fullscreenBtn = wrapperElement.querySelector("#fullscreenBtn");
        this.pipBtn = wrapperElement.querySelector("#pipBtn");

        this.hlsController = new HLSController(this.video);
        this.bindEvents();
    }

    bindEvents() {
        if (!this.video) return;

        // Play / Pause toggle
        if (this.playPauseBtn) {
            this.playPauseBtn.addEventListener("click", () => this.togglePlay());
        }
        this.video.addEventListener("click", () => this.togglePlay());
        this.video.addEventListener("play", () => this.updatePlayState(true));
        this.video.addEventListener("pause", () => this.updatePlayState(false));

        // Time updates
        this.video.addEventListener("timeupdate", () => this.handleTimeUpdate());
        this.video.addEventListener("progress", () => this.handleBufferProgress());

        // Scrubbing
        if (this.progressBar) {
            this.progressBar.addEventListener("input", (e) => this.handleSeek(e));
        }

        // Volume / Mute
        if (this.volumeBar) {
            this.volumeBar.addEventListener("input", (e) => this.handleVolumeChange(e));
        }
        if (this.muteBtn) {
            this.muteBtn.addEventListener("click", () => this.toggleMute());
        }

        // Playback speed
        if (this.speedSelect) {
            this.speedSelect.addEventListener("change", (e) => {
                this.video.playbackRate = parseFloat(e.target.value);
            });
        }

        // Fullscreen & PiP
        if (this.fullscreenBtn) {
            this.fullscreenBtn.addEventListener("click", () => this.toggleFullscreen());
        }
        if (this.pipBtn && document.pictureInPictureEnabled) {
            this.pipBtn.addEventListener("click", () => this.togglePiP());
        }
    }

    togglePlay() {
        if (this.video.paused) {
            this.video.play();
        } else {
            this.video.pause();
        }
    }

    updatePlayState(isPlaying) {
        if (this.playPauseBtn) {
            this.playPauseBtn.textContent = isPlaying ? "Pause" : "Play";
        }
    }

    handleTimeUpdate() {
        if (!this.video.duration) return;
        const current = this.video.currentTime;
        const duration = this.video.duration;

        if (this.progressBar) {
            this.progressBar.value = (current / duration) * 100;
        }

        if (this.timeDisplay) {
            this.timeDisplay.textContent = `${this.formatTime(current)} / ${this.formatTime(duration)}`;
        }
    }

    handleBufferProgress() {
        if (!this.video.duration || this.video.buffered.length === 0) return;
        const bufferedEnd = this.video.buffered.end(this.video.buffered.length - 1);
        const duration = this.video.duration;
        if (this.bufferedBar) {
            this.bufferedBar.style.width = `${(bufferedEnd / duration) * 100}%`;
        }
    }

    handleSeek(event) {
        if (!this.video.duration) return;
        const seekRatio = parseFloat(event.target.value) / 100;
        this.video.currentTime = seekRatio * this.video.duration;
    }

    handleVolumeChange(event) {
        const val = parseFloat(event.target.value);
        this.video.volume = val;
        this.video.muted = val === 0;
        if (this.muteBtn) {
            this.muteBtn.textContent = this.video.muted ? "Unmute" : "Mute";
        }
    }

    toggleMute() {
        this.video.muted = !this.video.muted;
        if (this.muteBtn) {
            this.muteBtn.textContent = this.video.muted ? "Unmute" : "Mute";
        }
        if (this.volumeBar) {
            this.volumeBar.value = this.video.muted ? 0 : this.video.volume;
        }
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            this.wrapper.requestFullscreen().catch(() => {});
        } else {
            document.exitFullscreen().catch(() => {});
        }
    }

    async togglePiP() {
        try {
            if (document.pictureInPictureElement) {
                await document.exitPictureInPicture();
            } else {
                await this.video.requestPictureInPicture();
            }
        } catch (err) {
            // Ignore PiP errors
        }
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return "0:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
    }

    loadVideo(streamUrl) {
        this.hlsController.loadSource(streamUrl);
    }
}
