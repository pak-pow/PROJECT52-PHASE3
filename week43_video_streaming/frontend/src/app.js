/**
 * PulseStream Main Application Orchestrator.
 * Wires the custom HTML5/HLS video player, catalog view, category filtering,
 * debounced search, and upload ingestion modal to the backend REST API.
 */

import { PulsePlayer } from "./player/video_player.js";
import { CatalogView } from "./ui/catalog_view.js";
import { UploadModal } from "./ui/upload_modal.js";

class PulseStreamApp {
    constructor() {
        this.player = null;
        this.catalog = null;
        this.uploadModal = null;
        this.searchDebounceTimer = null;
    }

    async init() {
        const videoWrapper = document.getElementById("videoWrapper");
        const videoGrid = document.getElementById("videoGrid");
        const categoryTabs = document.getElementById("categoryTabs");
        const uploadModalElem = document.getElementById("uploadModal");

        if (videoWrapper) {
            this.player = new PulsePlayer(videoWrapper);
        }

        if (videoGrid && categoryTabs) {
            this.catalog = new CatalogView(videoGrid, categoryTabs);
            this.catalog.onVideoSelectCallback = (video) => this.selectVideo(video, true);
        }

        if (uploadModalElem) {
            this.uploadModal = new UploadModal(uploadModalElem);
            this.uploadModal.onUploadCompleteCallback = async (newVideo) => {
                await this.refreshCatalog();
                if (newVideo) {
                    this.selectVideo(newVideo, true);
                }
            };
        }

        this.bindGlobalActions();
        await this.loadInitialData();
    }

    bindGlobalActions() {
        // Upload button
        const uploadBtn = document.getElementById("uploadBtn");
        if (uploadBtn && this.uploadModal) {
            uploadBtn.addEventListener("click", () => this.uploadModal.show());
        }

        // Search input with debounce
        const searchInput = document.getElementById("searchInput");
        if (searchInput && this.catalog) {
            searchInput.addEventListener("input", (e) => {
                clearTimeout(this.searchDebounceTimer);
                this.searchDebounceTimer = setTimeout(() => {
                    this.catalog.setSearchQuery(e.target.value);
                }, 200);
            });
        }

        // Brand click scrolls to top and resets category filter
        const brand = document.querySelector(".brand");
        if (brand && this.catalog) {
            brand.addEventListener("click", () => {
                this.catalog.selectCategory("all");
                window.scrollTo({ top: 0, behavior: "smooth" });
            });
        }
    }

    async loadInitialData() {
        await Promise.all([this.loadCategories(), this.loadVideos()]);
    }

    async loadCategories() {
        try {
            const res = await fetch("/api/categories");
            if (!res.ok) return;
            const categories = await res.json();
            if (this.catalog) {
                this.catalog.renderCategories(categories);
            }
            if (this.uploadModal) {
                this.uploadModal.populateCategories(categories);
            }
        } catch {
            // Graceful fallback if categories cannot be fetched
        }
    }

    async loadVideos() {
        try {
            const res = await fetch("/api/videos");
            if (!res.ok) return;
            const data = await res.json();
            const videos = data.videos || [];
            if (this.catalog) {
                this.catalog.setVideos(videos);
            }

            // Automatically queue up the first ready video if none is selected yet
            if (videos.length > 0 && this.player && !this.player.activeVideo) {
                const firstReady = videos.find((v) => v.status === "ready") || videos[0];
                this.selectVideo(firstReady, false);
            }
        } catch {
            // Graceful fallback if video catalog fetch fails
        }
    }

    async refreshCatalog() {
        await this.loadVideos();
        await this.loadCategories();
    }

    selectVideo(video, autoPlay = true) {
        if (!video || !this.player) return;

        const playerSection = document.getElementById("playerSection");
        if (playerSection) {
            playerSection.classList.remove("hidden");
            if (autoPlay) {
                playerSection.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }

        const titleElem = document.getElementById("activeVideoTitle");
        const viewsElem = document.getElementById("activeVideoViews");
        const catElem = document.getElementById("activeVideoCategory");
        const descElem = document.getElementById("activeVideoDesc");

        if (titleElem) titleElem.textContent = video.title;
        if (viewsElem) viewsElem.textContent = `${(video.views_count || 0) + (autoPlay ? 1 : 0)} views`;
        if (catElem) catElem.textContent = video.category_name || "General";
        if (descElem) descElem.textContent = video.description || "";

        this.player.loadVideo(video);

        if (autoPlay) {
            this.player.video.play().catch(() => {});
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const app = new PulseStreamApp();
    app.init();
});
