/**
 * PulsePress Application Shell Controller
 * Coordinates client-side routing, theme toggling, and modular UI components:
 * PostList, TagCloud, BlogReader, SearchView, CommentWidget, and AuthorDashboard.
 */

import { AuthorDashboard } from "/src/ui/author_dashboard.js";
import { BlogReader } from "/src/ui/blog_reader.js";
import { CommentWidget } from "/src/ui/comment_widget.js";
import { PostList } from "/src/ui/post_list.js";
import { SearchView } from "/src/ui/search_view.js";
import { TagCloud } from "/src/ui/tag_cloud.js";

class AppShell {
  constructor() {
    this.currentTheme = localStorage.getItem("pulsepress_theme") || "dark";
    this.initTheme();

    this.views = {
      home: document.getElementById("homeView"),
      reader: document.getElementById("readerView"),
      search: document.getElementById("searchView"),
      dashboard: document.getElementById("dashboardView"),
    };

    this.tagCloud = new TagCloud({
      container: document.getElementById("tagCloudContainer"),
      onSelectTag: (slug, name) => this.navigateTag(slug, name),
    });

    this.postList = new PostList({
      container: document.getElementById("postsListContainer"),
      filterBanner: document.getElementById("activeTagFilter"),
      onSelectPost: (slug) => this.navigatePost(slug),
      onSelectTag: (slug, name) => this.navigateTag(slug, name),
    });

    this.blogReader = new BlogReader({
      container: this.views.reader,
      onNavigatePost: (slug) => this.navigatePost(slug),
      onSelectTag: (slug) => this.navigateTag(slug, slug),
      onBackHome: () => this.navigateHome(),
      onMountComments: (slug, mountEl) => {
        const widget = new CommentWidget({ container: mountEl, slug });
        widget.load();
      },
    });

    this.searchView = new SearchView({
      inputEl: document.getElementById("globalSearchInput"),
      dropdownEl: document.getElementById("autocompleteDropdown"),
      resultsContainer: this.views.search,
      onSelectPost: (slug) => this.navigatePost(slug),
      onSearchNavigate: (query) => this.navigateSearch(query),
      onBackHome: () => this.navigateHome(),
    });

    this.dashboard = new AuthorDashboard({
      container: this.views.dashboard,
      onViewPost: (slug) => this.navigatePost(slug),
      onBackHome: () => this.navigateHome(),
    });

    this.bindGlobalEvents();
    this.handleRoute();
  }

  initTheme() {
    document.body.className = `theme-${this.currentTheme}`;
  }

  toggleTheme() {
    this.currentTheme = this.currentTheme === "dark" ? "light" : "dark";
    localStorage.setItem("pulsepress_theme", this.currentTheme);
    this.initTheme();
  }

  bindGlobalEvents() {
    const themeBtn = document.getElementById("themeToggleBtn");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => this.toggleTheme());
    }

    document.querySelector(".brand-logo")?.addEventListener("click", (e) => {
      e.preventDefault();
      this.navigateHome();
    });

    document.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        const href = link.getAttribute("href") || "";
        if (href === "/" || href === "#home") {
          e.preventDefault();
          this.navigateHome();
        } else if (href === "#tags") {
          e.preventDefault();
          this.navigateHome();
          document
            .getElementById("tagCloudContainer")
            ?.scrollIntoView({ behavior: "smooth" });
        } else if (href === "#dashboard") {
          e.preventDefault();
          this.navigateDashboard();
        }
      });
    });

    window.addEventListener("hashchange", () => this.handleRoute());
  }

  /**
   * Show only the active view section and update nav active state.
   * @param {"home"|"reader"|"search"|"dashboard"} activeKey
   */
  showView(activeKey) {
    if (activeKey !== "reader") {
      this.blogReader.destroy();
    }
    Object.entries(this.views).forEach(([key, el]) => {
      if (!el) return;
      el.classList.toggle("hidden", key !== activeKey);
    });
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  navigateHome() {
    if (window.location.hash) {
      window.location.hash = "#home";
    } else {
      this.handleRoute();
    }
  }

  navigatePost(slug) {
    window.location.hash = `#post/${encodeURIComponent(slug)}`;
  }

  navigateTag(slug, name) {
    if (!slug) {
      this.navigateHome();
      return;
    }
    this._pendingTagName = name || slug;
    window.location.hash = `#tag/${encodeURIComponent(slug)}`;
  }

  navigateSearch(query) {
    window.location.hash = `#search/${encodeURIComponent(query)}`;
  }

  navigateDashboard() {
    window.location.hash = "#dashboard";
  }

  /**
   * Resolve URL hash to the appropriate view controller.
   */
  handleRoute() {
    const hash = window.location.hash || "#home";

    if (hash.startsWith("#post/")) {
      const slug = decodeURIComponent(hash.slice(6));
      this.showView("reader");
      this.blogReader.loadPost(slug);
      return;
    }

    if (hash.startsWith("#search/")) {
      const query = decodeURIComponent(hash.slice(8));
      this.showView("search");
      this.searchView.executeSearch(query, 1);
      return;
    }

    if (hash === "#dashboard") {
      this.showView("dashboard");
      this.dashboard.open();
      return;
    }

    if (hash.startsWith("#tag/")) {
      const slug = decodeURIComponent(hash.slice(5));
      const tagName = this._pendingTagName || slug;
      this.showView("home");
      this.tagCloud.load(slug);
      this.postList.loadPosts({ page: 1, tag: slug, tagName, append: false });
      return;
    }

    this.showView("home");
    this.tagCloud.load(null);
    this.postList.loadPosts({ page: 1, tag: null, tagName: null, append: false });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.pulsePressApp = new AppShell();
});
