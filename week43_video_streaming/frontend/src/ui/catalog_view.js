/**
 * Catalog grid and category tab controller for PulseStream.
 * Manages category filtering, live keyword search, duration formatting,
 * and video card selection.
 */

export class CatalogView {
    constructor(gridElement, tabsElement) {
        this.grid = gridElement;
        this.tabs = tabsElement;
        this.videos = [];
        this.categories = [];
        this.activeCategory = "all";
        this.searchQuery = "";
        this.onVideoSelectCallback = null;
    }

    /**
     * Populate category tab pills.
     */
    renderCategories(categories) {
        this.categories = categories;
        if (!this.tabs) return;

        this.tabs.innerHTML = "";
        const allBtn = document.createElement("button");
        allBtn.className = `tab-btn ${this.activeCategory === "all" ? "active" : ""}`;
        allBtn.textContent = "All";
        allBtn.dataset.category = "all";
        allBtn.addEventListener("click", () => this.selectCategory("all"));
        this.tabs.appendChild(allBtn);

        categories.forEach((cat) => {
            const btn = document.createElement("button");
            btn.className = `tab-btn ${this.activeCategory === cat.slug ? "active" : ""}`;
            const countSuffix = typeof cat.video_count === "number" ? ` (${cat.video_count})` : "";
            btn.textContent = `${cat.name}${countSuffix}`;
            btn.dataset.category = cat.slug;
            btn.addEventListener("click", () => this.selectCategory(cat.slug));
            this.tabs.appendChild(btn);
        });
    }

    selectCategory(slug) {
        this.activeCategory = slug;
        if (this.tabs) {
            this.tabs.querySelectorAll(".tab-btn").forEach((btn) => {
                btn.classList.toggle("active", btn.dataset.category === slug);
            });
        }
        this.filterAndRender();
    }

    setVideos(videos) {
        this.videos = videos || [];
        this.filterAndRender();
    }

    setSearchQuery(query) {
        this.searchQuery = (query || "").trim().toLowerCase();
        this.filterAndRender();
    }

    filterAndRender() {
        if (!this.grid) return;

        let filtered = this.videos;

        // Category filter
        if (this.activeCategory !== "all") {
            filtered = filtered.filter((v) => v.category_slug === this.activeCategory);
        }

        // Search query filter
        if (this.searchQuery) {
            filtered = filtered.filter((v) => {
                const titleMatch = (v.title || "").toLowerCase().includes(this.searchQuery);
                const descMatch = (v.description || "").toLowerCase().includes(this.searchQuery);
                return titleMatch || descMatch;
            });
        }

        this.grid.innerHTML = "";

        if (filtered.length === 0) {
            const emptyNotice = document.createElement("div");
            emptyNotice.className = "empty-msg";
            emptyNotice.style.cssText = "color: var(--text-muted); padding: 3rem 1.5rem; text-align: center; grid-column: 1 / -1;";
            emptyNotice.textContent = this.searchQuery
                ? `No videos match the search "${this.searchQuery}".`
                : "No videos found in this category.";
            this.grid.appendChild(emptyNotice);
            return;
        }

        filtered.forEach((video) => {
            const card = document.createElement("div");
            card.className = "video-card";
            card.dataset.videoId = video.id;

            const posterSrc = video.poster_url || (video.poster_path ? `/api/thumbnails/${video.poster_path}` : "");
            const durationFormatted = this.formatDuration(video.duration);
            const viewsText = `${video.views_count || 0} views`;
            const categoryText = video.category_name || "General";

            const statusBadge = video.status && video.status !== "ready"
                ? `<span class="card-status-badge" style="position: absolute; top: 8px; left: 8px; background: rgba(2, 132, 199, 0.85); color: #fff; font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;">${video.status}</span>`
                : "";

            card.innerHTML = `
                <div class="card-thumbnail-wrap">
                    ${posterSrc ? `<img class="card-thumbnail" src="${posterSrc}" alt="${video.title}" loading="lazy" onerror="this.style.display='none'">` : ""}
                    ${statusBadge}
                    <span class="card-duration">${durationFormatted}</span>
                </div>
                <div class="card-info">
                    <span class="card-category">${categoryText}</span>
                    <h3 class="card-title">${video.title}</h3>
                    <div class="card-meta">
                        <span>${viewsText}</span>
                    </div>
                </div>
            `;

            card.addEventListener("click", () => {
                if (this.onVideoSelectCallback) {
                    this.onVideoSelectCallback(video);
                }
            });

            this.grid.appendChild(card);
        });
    }

    formatDuration(seconds) {
        if (!seconds || isNaN(seconds)) return "0:00";
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
}
