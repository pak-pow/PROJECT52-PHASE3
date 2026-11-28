/**
 * PulsePress Search View Component
 * Provides debounced BM25 autocomplete with keyboard navigation
 * and full search results view with highlighted snippets and tag facet filters.
 */

export class SearchView {
  /**
   * @param {Object} options
   * @param {HTMLInputElement} options.inputEl - Global search input element
   * @param {HTMLElement} options.dropdownEl - Autocomplete dropdown element
   * @param {HTMLElement} options.resultsContainer - Container for full search view
   * @param {Function} [options.onSelectPost] - Callback(slug) when selecting a result
   * @param {Function} [options.onSearchNavigate] - Callback(query) when submitting search
   * @param {Function} [options.onBackHome] - Callback() to return to home feed
   */
  constructor(options = {}) {
    this.inputEl = options.inputEl;
    this.dropdownEl = options.dropdownEl;
    this.resultsContainer = options.resultsContainer;
    this.onSelectPost = options.onSelectPost || (() => {});
    this.onSearchNavigate = options.onSearchNavigate || (() => {});
    this.onBackHome = options.onBackHome || (() => {});

    this._debounceTimer = null;
    this._activeIndex = -1;
    this._suggestions = [];
    this.selectedTags = new Set();
    this.currentQuery = "";
    this.currentPage = 1;

    this.bindInputEvents();
  }

  /**
   * Escape HTML special characters.
   * @param {string} value
   * @returns {string}
   */
  static escapeHtml(value) {
    const str = String(value ?? "");
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Highlight matched query terms inside a snippet safely.
   * @param {string} text
   * @param {string[]} terms
   * @returns {string}
   */
  static highlightTerms(text, terms) {
    let escaped = SearchView.escapeHtml(text);
    if (!Array.isArray(terms) || terms.length === 0) return escaped;
    const cleanTerms = terms
      .map((t) => String(t).trim())
      .filter((t) => t.length >= 2)
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (cleanTerms.length === 0) return escaped;
    const regex = new RegExp(`(${cleanTerms.join("|")})`, "gi");
    return escaped.replace(regex, "<mark>$1</mark>");
  }

  /**
   * Attach debounced input and keyboard navigation listeners.
   */
  bindInputEvents() {
    if (!this.inputEl) return;

    this.inputEl.addEventListener("input", (e) => {
      const value = e.target.value.trim();
      clearTimeout(this._debounceTimer);
      if (!value) {
        this.hideDropdown();
        return;
      }
      this._debounceTimer = setTimeout(() => {
        this.fetchAutocomplete(value);
      }, 180);
    });

    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        if (this._suggestions.length === 0) return;
        e.preventDefault();
        this._activeIndex =
          (this._activeIndex + 1) % this._suggestions.length;
        this.renderDropdown();
      } else if (e.key === "ArrowUp") {
        if (this._suggestions.length === 0) return;
        e.preventDefault();
        this._activeIndex =
          (this._activeIndex - 1 + this._suggestions.length) %
          this._suggestions.length;
        this.renderDropdown();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (
          this._activeIndex >= 0 &&
          this._suggestions[this._activeIndex]
        ) {
          this.inputEl.value = this._suggestions[this._activeIndex];
        }
        const query = this.inputEl.value.trim();
        this.hideDropdown();
        if (query) {
          this.onSearchNavigate(query);
        }
      } else if (e.key === "Escape") {
        this.hideDropdown();
      }
    });

    document.addEventListener("click", (e) => {
      if (
        this.dropdownEl &&
        e.target !== this.inputEl &&
        !this.dropdownEl.contains(e.target)
      ) {
        this.hideDropdown();
      }
    });
  }

  /**
   * Fetch autocomplete term suggestions from BM25 index.
   * @param {string} prefix
   */
  async fetchAutocomplete(prefix) {
    try {
      const response = await fetch(
        `/api/search/autocomplete?q=${encodeURIComponent(prefix)}&limit=8`
      );
      const payload = await response.json();
      if (!response.ok || payload.status !== "success") {
        this.hideDropdown();
        return;
      }
      this._suggestions = Array.isArray(payload.data?.suggestions)
        ? payload.data.suggestions
        : [];
      this._activeIndex = -1;
      this.renderDropdown();
    } catch (err) {
      this.hideDropdown();
    }
  }

  /**
   * Render autocomplete dropdown items.
   */
  renderDropdown() {
    if (!this.dropdownEl) return;
    if (this._suggestions.length === 0) {
      this.hideDropdown();
      return;
    }

    const esc = SearchView.escapeHtml;
    this.dropdownEl.innerHTML = this._suggestions
      .map(
        (term, idx) => `
        <div class="autocomplete-item ${
          idx === this._activeIndex ? "active" : ""
        }" data-suggestion="${esc(term)}" role="option" aria-selected="${
          idx === this._activeIndex
        }">
          ${esc(term)}
        </div>`
      )
      .join("");
    this.dropdownEl.classList.remove("hidden");

    this.dropdownEl.querySelectorAll(".autocomplete-item").forEach((item) => {
      item.addEventListener("click", () => {
        const term = item.getAttribute("data-suggestion") || "";
        if (this.inputEl) this.inputEl.value = term;
        this.hideDropdown();
        this.onSearchNavigate(term);
      });
    });
  }

  /**
   * Hide and clear autocomplete dropdown.
   */
  hideDropdown() {
    if (!this.dropdownEl) return;
    this.dropdownEl.classList.add("hidden");
    this.dropdownEl.innerHTML = "";
    this._activeIndex = -1;
  }

  /**
   * Execute BM25 search and render full search view with tag facets.
   * @param {string} query
   * @param {number} [page=1]
   */
  async executeSearch(query, page = 1) {
    if (!this.resultsContainer) return;
    this.currentQuery = (query || "").trim();
    this.currentPage = page;
    if (this.inputEl && this.inputEl.value.trim() !== this.currentQuery) {
      this.inputEl.value = this.currentQuery;
    }

    this.resultsContainer.innerHTML =
      '<div class="loading-spinner">Searching inverted index...</div>';

    try {
      const tagParam = Array.from(this.selectedTags).join(",");
      const searchUrl = `/api/search?q=${encodeURIComponent(
        this.currentQuery
      )}&tags=${encodeURIComponent(tagParam)}&page=${page}&page_size=10`;

      const [searchRes, tagsRes] = await Promise.all([
        fetch(searchUrl),
        fetch("/api/tags"),
      ]);
      const searchPayload = await searchRes.json();
      const tagsPayload = await tagsRes.json();

      if (!searchRes.ok || searchPayload.status !== "success") {
        this.renderError(searchPayload.message || "Search failed.");
        return;
      }

      const data = searchPayload.data || {};
      const allTags = Array.isArray(tagsPayload?.data?.tags)
        ? tagsPayload.data.tags
        : [];
      this.renderResults(data, allTags);
    } catch (err) {
      this.renderError("Network error while searching articles.");
    }
  }

  /**
   * Render search error card.
   * @param {string} message
   */
  renderError(message) {
    this.resultsContainer.innerHTML = `
      <div class="empty-state-card">
        <p>${SearchView.escapeHtml(message)}</p>
        <button type="button" class="btn-secondary btn-sm" id="searchBackHomeBtn">Back to Articles</button>
      </div>
    `;
    const btn = document.getElementById("searchBackHomeBtn");
    if (btn) btn.addEventListener("click", () => this.onBackHome());
  }

  /**
   * Render search results and tag facet sidebar.
   * @param {Object} data
   * @param {Array} allTags
   */
  renderResults(data, allTags) {
    const esc = SearchView.escapeHtml;
    const results = Array.isArray(data.results) ? data.results : [];
    const terms = Array.isArray(data.terms) ? data.terms : [];
    const total = Number(data.total) || 0;
    const page = Number(data.page) || 1;
    const pageSize = Number(data.page_size) || 10;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    const facetsHtml =
      allTags.length > 0
        ? allTags
            .map((t) => {
              const checked = this.selectedTags.has(t.slug) ? "checked" : "";
              return `
                <label class="facet-checkbox">
                  <input type="checkbox" value="${esc(t.slug)}" ${checked} />
                  <span>${esc(t.name)}</span>
                  <span class="facet-count">${Number(t.post_count) || 0}</span>
                </label>`;
            })
            .join("")
        : '<p class="muted-text">No tag facets available.</p>';

    const resultsHtml =
      results.length > 0
        ? results
            .map((item) => {
              const titleHtml = SearchView.highlightTerms(item.title, terms);
              const snippetSource = item.snippet || item.excerpt || "";
              const snippetHtml = SearchView.highlightTerms(
                snippetSource,
                terms
              );
              const scoreVal =
                typeof item.score === "number" ? item.score.toFixed(2) : "0.00";
              return `
                <article class="search-result-card" data-result-slug="${esc(
                  item.slug
                )}">
                  <div class="search-result-header">
                    <h3>
                      <a href="#post/${esc(item.slug)}">${titleHtml}</a>
                    </h3>
                    <span class="bm25-score-badge">BM25 ${scoreVal}</span>
                  </div>
                  <p class="search-result-snippet">${snippetHtml}</p>
                  <div class="post-tags-list">
                    ${(item.tags || [])
                      .map(
                        (t) =>
                          `<span class="tag-badge">${esc(t.name)}</span>`
                      )
                      .join("")}
                  </div>
                </article>`;
            })
            .join("")
        : `<div class="empty-state-card">
             <h3>No matching articles</h3>
             <p>No results matched "${esc(this.currentQuery)}". Try broader keywords or fewer tag filters.</p>
           </div>`;

    this.resultsContainer.innerHTML = `
      <div class="search-view-header">
        <div>
          <h2>Search Results for "${esc(this.currentQuery)}"</h2>
          <p class="muted-text">${total} ranked result${total === 1 ? "" : "s"}</p>
        </div>
        <button type="button" class="btn-secondary btn-sm" id="searchViewBackBtn">
          &larr; Back to Feed
        </button>
      </div>

      <div class="search-layout">
        <aside class="search-facets-sidebar">
          <div class="sidebar-widget">
            <h3 class="widget-title">Filter by Tag</h3>
            <div class="facets-list" id="searchFacetsList">
              ${facetsHtml}
            </div>
            ${
              this.selectedTags.size > 0
                ? '<button type="button" class="btn-clear-filter" id="clearFacetBtn">Reset Filters</button>'
                : ""
            }
          </div>
        </aside>

        <section class="search-results-column">
          ${resultsHtml}
          ${
            totalPages > 1
              ? `<div class="pagination-controls">
                   <button type="button" class="btn-secondary btn-sm" id="searchPrevBtn" ${
                     page <= 1 ? "disabled" : ""
                   }>Previous</button>
                   <span class="pagination-info">Page ${page} of ${totalPages}</span>
                   <button type="button" class="btn-secondary btn-sm" id="searchNextBtn" ${
                     page >= totalPages ? "disabled" : ""
                   }>Next</button>
                 </div>`
              : ""
          }
        </section>
      </div>
    `;

    this.bindResultsEvents(page, totalPages);
  }

  /**
   * Bind click and facet filter listeners on rendered search view.
   * @param {number} page
   * @param {number} totalPages
   */
  bindResultsEvents(page, totalPages) {
    const backBtn = document.getElementById("searchViewBackBtn");
    if (backBtn) {
      backBtn.addEventListener("click", () => this.onBackHome());
    }

    this.resultsContainer
      .querySelectorAll("[data-result-slug] a")
      .forEach((link) => {
        link.addEventListener("click", (e) => {
          e.preventDefault();
          const card = link.closest("[data-result-slug]");
          if (card) {
            this.onSelectPost(card.getAttribute("data-result-slug"));
          }
        });
      });

    this.resultsContainer
      .querySelectorAll("#searchFacetsList input[type='checkbox']")
      .forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            this.selectedTags.add(checkbox.value);
          } else {
            this.selectedTags.delete(checkbox.value);
          }
          this.executeSearch(this.currentQuery, 1);
        });
      });

    const clearBtn = document.getElementById("clearFacetBtn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.selectedTags.clear();
        this.executeSearch(this.currentQuery, 1);
      });
    }

    const prevBtn = document.getElementById("searchPrevBtn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (page > 1) this.executeSearch(this.currentQuery, page - 1);
      });
    }

    const nextBtn = document.getElementById("searchNextBtn");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (page < totalPages) this.executeSearch(this.currentQuery, page + 1);
      });
    }
  }
}
