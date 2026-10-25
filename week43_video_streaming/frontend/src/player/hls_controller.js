/**
 * PulseStream HLS Stream Controller.
 * Wraps Hls.js library with adaptive bitrate switching, level querying,
 * and graceful fallback to native HLS or progressive range streaming.
 */

export class HLSController {
    constructor(videoElement) {
        this.video = videoElement;
        this.hls = null;
        this.isHlsSupported = typeof window !== "undefined" && Boolean(window.Hls && window.Hls.isSupported());
        this.levels = [];
        this.currentLevelIndex = -1; // -1 represents Auto (ABR)
        this.levelsCallback = null;
        this.levelSwitchCallback = null;
        this.errorCallback = null;
    }

    /**
     * Register callback fired when ABR quality levels are parsed from master playlist.
     */
    onLevelsLoaded(callback) {
        this.levelsCallback = callback;
    }

    /**
     * Register callback fired when Hls.js switches active rendition level.
     */
    onLevelSwitched(callback) {
        this.levelSwitchCallback = callback;
    }

    /**
     * Register callback fired on fatal or recoverable errors.
     */
    onError(callback) {
        this.errorCallback = callback;
    }

    /**
     * Load a streaming source URL. Selects Hls.js, native Safari HLS,
     * or progressive MP4 byte-range playback based on URL and browser capabilities.
     */
    loadSource(streamUrl) {
        this.destroy();

        const isHlsUrl = streamUrl.includes(".m3u8") || streamUrl.includes("/hls/");

        if (isHlsUrl && this.isHlsSupported) {
            this.hls = new window.Hls({
                enableWorker: true,
                lowLatencyMode: true,
                backBufferLength: 60,
                maxBufferLength: 30,
                maxMaxBufferLength: 60
            });

            this.hls.attachMedia(this.video);

            this.hls.on(window.Hls.Events.MEDIA_ATTACHED, () => {
                this.hls.loadSource(streamUrl);
            });

            this.hls.on(window.Hls.Events.MANIFEST_PARSED, (event, data) => {
                this.levels = (data.levels || []).map((lvl, idx) => ({
                    index: idx,
                    width: lvl.width || 0,
                    height: lvl.height || 0,
                    bitrate: lvl.bitrate || 0,
                    name: lvl.name || `${lvl.height || "ABR"}p`
                }));

                if (this.levelsCallback) {
                    this.levelsCallback(this.levels);
                }
            });

            this.hls.on(window.Hls.Events.LEVEL_SWITCHED, (event, data) => {
                this.currentLevelIndex = data.level;
                if (this.levelSwitchCallback) {
                    this.levelSwitchCallback(data.level, this.levels[data.level]);
                }
            });

            this.hls.on(window.Hls.Events.ERROR, (event, data) => {
                if (this.errorCallback) {
                    this.errorCallback(data);
                }

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
        } else if (isHlsUrl && this.video.canPlayType("application/vnd.apple.mpegurl")) {
            // Native Safari HLS
            this.video.src = streamUrl;
        } else {
            // Progressive MP4 / RFC 7233 range stream fallback
            this.video.src = streamUrl;
        }
    }

    /**
     * Select rendition quality level. Pass -1 for Auto (ABR).
     */
    setQuality(levelIndex) {
        if (!this.hls) return;
        this.hls.currentLevel = levelIndex;
        this.currentLevelIndex = levelIndex;
    }

    /**
     * Retrieve currently cached levels.
     */
    getLevels() {
        return this.levels;
    }

    /**
     * Teardown and release Hls.js instance.
     */
    destroy() {
        if (this.hls) {
            this.hls.destroy();
            this.hls = null;
        }
        this.levels = [];
        this.currentLevelIndex = -1;
    }
}
