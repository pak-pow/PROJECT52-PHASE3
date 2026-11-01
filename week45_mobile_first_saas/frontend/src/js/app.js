/**
 * PulseSub Mobile-First Frontend Application Controller
 * Version: 1.0.0
 */

"use strict";

document.addEventListener("DOMContentLoaded", () => {
    initThemeManager();
    initNavigation();
    checkSystemHealth();
});

function initThemeManager() {
    const themeBtn = document.getElementById("theme-toggle-btn");
    const htmlEl = document.documentElement;
    const savedTheme = localStorage.getItem("pulse_theme") || "dark";

    htmlEl.setAttribute("data-theme", savedTheme);

    if (themeBtn) {
        themeBtn.addEventListener("click", () => {
            const currentTheme = htmlEl.getAttribute("data-theme") || "dark";
            const newTheme = currentTheme === "dark" ? "light" : "dark";
            htmlEl.setAttribute("data-theme", newTheme);
            localStorage.setItem("pulse_theme", newTheme);
        });
    }
}

function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((btn) => {
        btn.addEventListener("click", () => {
            navItems.forEach((item) => item.classList.remove("active"));
            btn.classList.add("active");
        });
    });
}

async function checkSystemHealth() {
    const statusMeta = document.getElementById("status-meta-text");
    const indicator = document.querySelector(".status-indicator");

    try {
        const response = await fetch("/api/health");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        if (statusMeta) {
            statusMeta.textContent = `DB: ${data.database} | Version: ${data.version} | ${data.service}`;
        }
        if (indicator) {
            indicator.classList.add("online");
        }
    } catch (err) {
        if (statusMeta) {
            statusMeta.textContent = `Backend error: ${err.message}`;
        }
        if (indicator) {
            indicator.classList.remove("online");
        }
    }
}
