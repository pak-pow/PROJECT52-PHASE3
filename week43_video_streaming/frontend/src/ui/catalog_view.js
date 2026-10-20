/**
 * Catalog grid and category tab controller for PulseStream.
 */

export class CatalogView {
    constructor(gridElement, tabsElement) {
        this.grid = gridElement;
        this.tabs = tabsElement;
        this.videos = [];
        this.categories = [];
        this.activeCategory = "all";
        this.onVideoSelectCallback = null;
    }

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

        categories.forEach(cat => {
            const btn = document.createElement("button");
            btn.className = `tab-btn ${this.activeCategory === cat.slug ? "active" : ""}`;
            btn.textContent = cat.name;
            btn.dataset.category = cat.slug;
            btn.addEventListener("click", () => this.selectCategory(cat.slug));
            this.tabs.appendChild(btn);
        });
    }

    selectCategory(slug) {
        this.activeCategory = slug;
        if (this.tabs) {
            this.tabs.querySelectorAll(".tab-btn").forEach(btn => {
                btn.classList.toggle("active", btn.dataset.category === slug);
            });
        }
        this.filterAndRender();
    }

    setVideos(videos) {
        this.videos = videos;
        this.filterAndRender();
    }

    filterAndRender() {
        if (!this.grid) return;
        const filtered = this.activeCategory === "all"
            ? this.videos
            : this.videos.filter(v => v.category_slug === this.activeCategory);

        this.grid.innerHTML = "";
        if (filtered.length === 0) {
            this.grid.innerHTML = '<p class="empty-msg" style="color: var(--text-muted); padding: 2rem;">No videos found in this category.</p>';
            return;
        }

        filtered.forEach(video => {
            const card = document.createElement("div");
            card.className = "video-card";
            card.innerHTML = `
                <div class="card-thumbnail-wrap">
                    <img class="card-thumbnail" src="${video.poster_path ? '/api/thumbnails/' + video.poster_path : ''}" alt="${video.title}" onerror="this.style.display='none'">
                    <span class="card-duration">${this.formatDuration(video.duration)}</span>
                </div>
                <div class="card-info">
                    <span class="card-category">${video.category_name || 'General'}</span>
                    <h3 class="card-title">${video.title}</h3>
                    <div class="card-meta">
                        <span>${video.views_count || 0} views</span>
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
        if (!seconds) return "0:00";
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
    }
}
