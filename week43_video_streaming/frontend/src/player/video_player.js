/**
 * PulseStream Video Player UI wrapper.
 * Provides custom scrub bar, buffer display, ABR quality selector,
 * playback speed adjustments, fullscreen, PiP, and keyboard shortcuts.
 */

import { HLSController } from "./hls_controller.js";

export class PulsePlayer {
    constructor(wrapperElement) {
        this.wrapper = wrapperElement;
        this.video = wrapperElement.querySelector("video");
        this.controls = wrapperElement.querySelector("#customControls");
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

        this.activeVideo = null;
        this.controlsTimeout = null;
        this.isUserScrubbing = false;

        this.hlsController = new HLSController(this.video);
        this.setupHlsCallbacks();
        this.bindEvents();
    }

    setupHlsCallbacks() {
        this.hlsController.onLevelsLoaded((levels) => {
            this.populateQualityMenu(levels);
        });

        this.hlsController.onLevelSwitched((levelIndex, levelData) => {
            if (this.qualitySelect && this.hlsController.currentLevelIndex === -1 && levelData) {
                const autoOption = this.qualitySelect.querySelector("option[value='auto']");
                if (autoOption) {
                    autoOption.textContent = `Auto (${levelData.height}p)`;
                }
            }
        });

        this.hlsController.onError((err) => {
            if (err.fatal && this.activeVideo && this.activeVideo.stream_url) {
                // Fallback to direct byte-range progressive stream
                this.video.src = this.activeVideo.stream_url;
            }
        });
    }

    bindEvents() {
        if (!this.video) return;

        // Playback toggle
        if (this.playPauseBtn) {
            this.playPauseBtn.addEventListener("click", () => this.togglePlay());
        }
        this.video.addEventListener("click", () => this.togglePlay());
        this.video.addEventListener("play", () => this.updatePlayState(true));
        this.video.addEventListener("pause", () => this.updatePlayState(false));

        // Time updates and buffering
        this.video.addEventListener("timeupdate", () => this.handleTimeUpdate());
        this.video.addEventListener("progress", () => this.handleBufferProgress());

        // Scrubbing
        if (this.progressBar) {
            this.progressBar.addEventListener("input", (e) => this.handleSeekInput(e));
            this.progressBar.addEventListener("change", (e) => this.handleSeekCommit(e));
        }

        // Volume and Mute
        if (this.volumeBar) {
            this.volumeBar.addEventListener("input", (e) => this.handleVolumeChange(e));
        }
        if (this.muteBtn) {
            this.muteBtn.addEventListener("click", () => this.toggleMute());
        }

        // Speed selector
        if (this.speedSelect) {
            this.speedSelect.addEventListener("change", (e) => {
                this.video.playbackRate = parseFloat(e.target.value);
            });
        }

        // Quality selector
        if (this.qualitySelect) {
            this.qualitySelect.addEventListener("change", (e) => {
                const val = e.target.value;
                if (val === "auto") {
                    this.hlsController.setQuality(-1);
                } else {
                    this.hlsController.setQuality(parseInt(val, 10));
                }
            });
        }

        // Fullscreen and PiP
        if (this.fullscreenBtn) {
            this.fullscreenBtn.addEventListener("click", () => this.toggleFullscreen());
        }
        this.wrapper.addEventListener("dblclick", (e) => {
            if (e.target.closest("#customControls")) return;
            this.toggleFullscreen();
        });

        if (this.pipBtn) {
            if (document.pictureInPictureEnabled) {
                this.pipBtn.addEventListener("click", () => this.togglePiP());
            } else {
                this.pipBtn.style.display = "none";
            }
        }

        // Mouse hover controls visibility
        this.wrapper.addEventListener("mousemove", () => this.handleUserActivity());
        this.wrapper.addEventListener("mouseleave", () => {
            if (!this.video.paused) {
                this.hideControls();
            }
        });

        // Global keyboard shortcuts
        document.addEventListener("keydown", (e) => this.handleKeyboardShortcut(e));
    }

    populateQualityMenu(levels) {
        if (!this.qualitySelect) return;
        this.qualitySelect.innerHTML = "";

        const autoOption = document.createElement("option");
        autoOption.value = "auto";
        autoOption.textContent = "Auto (ABR)";
        this.qualitySelect.appendChild(autoOption);

        levels.forEach((lvl) => {
            const opt = document.createElement("option");
            opt.value = lvl.index;
            const mbps = lvl.bitrate ? ` (${(lvl.bitrate / 1000000).toFixed(1)} Mbps)` : "";
            opt.textContent = `${lvl.height}p${mbps}`;
            this.qualitySelect.appendChild(opt);
        });
    }

    handleUserActivity() {
        this.showControls();
        clearTimeout(this.controlsTimeout);
        if (!this.video.paused) {
            this.controlsTimeout = setTimeout(() => this.hideControls(), 2500);
        }
    }

    showControls() {
        if (this.controls) {
            this.controls.style.opacity = "1";
            this.controls.style.pointerEvents = "auto";
        }
    }

    hideControls() {
        if (this.controls && !this.video.paused) {
            this.controls.style.opacity = "0";
            this.controls.style.pointerEvents = "none";
        }
    }

    togglePlay() {
        if (this.video.paused) {
            this.video.play().catch(() => {});
        } else {
            this.video.pause();
        }
    }

    updatePlayState(isPlaying) {
        if (this.playPauseBtn) {
            this.playPauseBtn.textContent = isPlaying ? "Pause" : "Play";
        }
        if (!isPlaying) {
            this.showControls();
        }
    }

    handleTimeUpdate() {
        if (!this.video.duration || this.isUserScrubbing) return;
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
            this.bufferedBar.style.width = `${Math.min(100, (bufferedEnd / duration) * 100)}%`;
        }
    }

    handleSeekInput(event) {
        this.isUserScrubbing = true;
        if (!this.video.duration) return;
        const seekRatio = parseFloat(event.target.value) / 100;
        const targetTime = seekRatio * this.video.duration;
        if (this.timeDisplay) {
            this.timeDisplay.textContent = `${this.formatTime(targetTime)} / ${this.formatTime(this.video.duration)}`;
        }
    }

    handleSeekCommit(event) {
        this.isUserScrubbing = false;
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
            } else if (this.video !== document.pictureInPictureElement) {
                await this.video.requestPictureInPicture();
            }
        } catch {
            // Ignore PiP errors
        }
    }

    handleKeyboardShortcut(event) {
        const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
        if (["input", "textarea", "select"].includes(activeTag)) return;

        switch (event.code) {
            case "Space":
            case "KeyK":
                event.preventDefault();
                this.togglePlay();
                break;
            case "KeyF":
                event.preventDefault();
                this.toggleFullscreen();
                break;
            case "KeyM":
                event.preventDefault();
                this.toggleMute();
                break;
            case "ArrowLeft":
                event.preventDefault();
                this.seekRelative(-5);
                break;
            case "ArrowRight":
                event.preventDefault();
                this.seekRelative(5);
                break;
            case "ArrowUp":
                event.preventDefault();
                this.adjustVolume(0.1);
                break;
            case "ArrowDown":
                event.preventDefault();
                this.adjustVolume(-0.1);
                break;
            case "Digit0":
            case "Digit1":
            case "Digit2":
            case "Digit3":
            case "Digit4":
            case "Digit5":
            case "Digit6":
            case "Digit7":
            case "Digit8":
            case "Digit9": {
                const digit = parseInt(event.code.replace("Digit", ""), 10);
                if (this.video.duration) {
                    this.video.currentTime = (digit / 10) * this.video.duration;
                }
                break;
            }
            default:
                break;
        }
    }

    seekRelative(seconds) {
        if (!this.video.duration) return;
        this.video.currentTime = Math.max(0, Math.min(this.video.duration, this.video.currentTime + seconds));
    }

    adjustVolume(delta) {
        const next = Math.max(0, Math.min(1, this.video.volume + delta));
        this.video.volume = next;
        this.video.muted = next === 0;
        if (this.volumeBar) this.volumeBar.value = next;
        if (this.muteBtn) this.muteBtn.textContent = this.video.muted ? "Unmute" : "Mute";
    }

    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "0:00";
        const total = Math.floor(seconds);
        const hrs = Math.floor(total / 3600);
        const mins = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        const padSecs = secs < 10 ? `0${secs}` : `${secs}`;

        if (hrs > 0) {
            const padMins = mins < 10 ? `0${mins}` : `${mins}`;
            return `${hrs}:${padMins}:${padSecs}`;
        }
        return `${mins}:${padSecs}`;
    }

    /**
     * Load video resource and initiate playback.
     */
    loadVideo(video) {
        this.activeVideo = video;

        // Reset control state
        if (this.progressBar) this.progressBar.value = 0;
        if (this.bufferedBar) this.bufferedBar.style.width = "0%";
        if (this.timeDisplay) this.timeDisplay.textContent = "0:00 / 0:00";
        if (this.qualitySelect) {
            this.qualitySelect.innerHTML = '<option value="auto">Auto (ABR)</option>';
        }

        const sourceUrl = video.hls_url || video.stream_url;
        if (sourceUrl) {
            this.hlsController.loadSource(sourceUrl);
        }

        if (video.poster_url) {
            this.video.poster = video.poster_url;
        } else {
            this.video.removeAttribute("poster");
        }
    }
}
