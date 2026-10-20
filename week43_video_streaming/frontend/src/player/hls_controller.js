/**
 * HLS stream controller wrapping Hls.js library with native HLS fallback.
 */

export class HLSController {
    constructor(videoElement) {
        this.video = videoElement;
        this.hls = null;
        this.isSupported = window.Hls && window.Hls.isSupported();
        this.onLevelsLoadedCallback = null;
    }

    loadSource(streamUrl) {
        this.destroy();

        if (this.isSupported) {
            this.hls = new window.Hls({
                enableWorker: true,
                lowLatencyMode: true,
                backBufferLength: 90
            });

            this.hls.attachMedia(this.video);
            this.hls.on(window.Hls.Events.MEDIA_ATTACHED, () => {
                this.hls.loadSource(streamUrl);
            });

            this.hls.on(window.Hls.Events.MANIFEST_PARSED, (event, data) => {
                if (this.onLevelsLoadedCallback) {
                    this.onLevelsLoadedCallback(data.levels);
                }
            });

            this.hls.on(window.Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    switch (data.type) {
                        case window.Hls.ErrorTypes.NETWORK_ERROR:
                            this.hls.startLoad();
                            break;
                        case window.Hls.ErrorTypes.MEDIA_ERROR:
                            this.hls.recoverMediaError();
                            break;
                        default:
                            this.destroy();
                            break;
                    }
                }
            });
        } else if (this.video.canPlayType("application/vnd.apple.mpegurl")) {
            // Native Safari HLS
            this.video.src = streamUrl;
        } else {
            // Progressive MP4 fallback
            this.video.src = streamUrl;
        }
    }

    setQuality(levelIndex) {
        if (this.hls) {
            this.hls.currentLevel = levelIndex; // -1 for auto
        }
    }

    destroy() {
        if (this.hls) {
            this.hls.destroy();
            this.hls = null;
        }
    }
}
