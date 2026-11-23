/**
 * PulsePress Application Shell Controller
 * Manages theme toggling, article catalog rendering, and search inputs.
 */

class AppShell {
  constructor() {
    this.currentTheme = localStorage.getItem("pulsepress_theme") || "dark";
    this.initTheme();
    this.bindEvents();
    this.loadDemoArticles();
  }

  initTheme() {
    document.body.className = `theme-${this.currentTheme}`;
  }

  toggleTheme() {
    this.currentTheme = this.currentTheme === "dark" ? "light" : "dark";
    localStorage.setItem("pulsepress_theme", this.currentTheme);
    this.initTheme();
  }

  bindEvents() {
    const themeBtn = document.getElementById("themeToggleBtn");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => this.toggleTheme());
    }

    const searchInput = document.getElementById("globalSearchInput");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.handleSearch(e.target.value.trim());
      });
    }
  }

  handleSearch(query) {
    const dropdown = document.getElementById("autocompleteDropdown");
    if (!dropdown) return;

    if (!query) {
      dropdown.classList.add("hidden");
      dropdown.innerHTML = "";
      return;
    }

    // Baseline autocomplete demonstration
    const suggestions = [
      "python",
      "bm25",
      "search",
      "architecture",
      "seo",
      "flask",
    ].filter((term) => term.toLowerCase().includes(query.toLowerCase()));

    if (suggestions.length === 0) {
      dropdown.classList.add("hidden");
      return;
    }

    dropdown.innerHTML = suggestions
      .map((term) => `<div class="autocomplete-item">${term}</div>`)
      .join("");
    dropdown.classList.remove("hidden");
  }

  loadDemoArticles() {
    const container = document.getElementById("postsListContainer");
    if (!container) return;

    const demoPosts = [
      {
        title: "Building a Production-Grade Blog Engine with Advanced SEO",
        slug: "building-production-blog-engine-with-advanced-seo",
        excerpt:
          "Explore how to design an enterprise blog platform from the ground up, incorporating Open Graph, JSON-LD schemas, and dynamic XML sitemaps.",
        readingTime: 3,
        date: "2026-11-20",
        author: "Sarah Chen",
        tags: ["Python", "Web Development", "SEO"],
      },
      {
        title: "Demystifying BM25 Search Ranking with Python",
        slug: "demystifying-bm25-search-ranking-with-python",
        excerpt:
          "A deep dive into the mathematical mechanics of BM25 probabilistic relevance ranking and how to build an inverted index inside SQLite.",
        readingTime: 4,
        date: "2026-11-21",
        author: "Sarah Chen",
        tags: ["Python", "Machine Learning", "Architecture"],
      },
      {
        title: "Clean Architecture in Flask: From Monolith to Microservices",
        slug: "clean-architecture-in-flask-monolith-to-microservices",
        excerpt:
          "Learn how decoupling domain entities, repository DAOs, and service layers allows monolithic web applications to scale gracefully.",
        readingTime: 3,
        date: "2026-11-22",
        author: "System Administrator",
        tags: ["Python", "Architecture", "DevOps"],
      },
    ];

    container.innerHTML = demoPosts
      .map(
        (post) => `
      <article class="post-card">
        <h3 class="post-card-title">
          <a href="/posts/${post.slug}">${post.title}</a>
        </h3>
        <p class="post-card-excerpt">${post.excerpt}</p>
        <div class="post-card-meta">
          <span>By ${post.author}</span>
          <span>${post.date}</span>
          <span>${post.readingTime} min read</span>
          <div class="post-tags-list">
            ${post.tags
              .map((t) => `<span class="tag-badge">${t}</span>`)
              .join("")}
          </div>
        </div>
      </article>
    `
      )
      .join("");

    const tagContainer = document.getElementById("tagCloudContainer");
    if (tagContainer) {
      const allTags = [
        "Python (3)",
        "Web Development (2)",
        "SEO (1)",
        "Machine Learning (1)",
        "Architecture (2)",
        "DevOps (1)",
      ];
      tagContainer.innerHTML = allTags
        .map((t) => `<a href="#tag" class="tag-badge">${t}</a>`)
        .join("");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.pulsePressApp = new AppShell();
});
