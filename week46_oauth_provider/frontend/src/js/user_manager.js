/**
 * PulseAuth User Account & Authentication Management Portal
 * Strict Zero-Emoji Compliant
 */

import { showToast } from "./app.js";

export function initUserManager() {
    setupUserRegistration();
    setupUserLoginTest();
    setupDemoUserPresets();
    loadUsersList();

    const refreshBtn = document.getElementById("users-refresh-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadUsersList();
            showToast("[OK] User directory refreshed.", "info");
        });
    }
}

function setupUserRegistration() {
    const form = document.getElementById("users-reg-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = document.getElementById("users-reg-submit-btn");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "[REGISTERING...]";
        }

        const email = document.getElementById("usr-reg-email").value.trim();
        const name = document.getElementById("usr-reg-name").value.trim();
        const password = document.getElementById("usr-reg-password").value;

        try {
            const res = await fetch("/api/v1/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, name, password })
            });

            const data = await res.json();
            if (res.ok) {
                showToast(`[OK] User '${email}' registered successfully!`, "success");
                form.reset();
                loadUsersList();
            } else {
                showToast(`Registration failed: ${data.error_description || data.error}`, "error");
            }
        } catch (err) {
            showToast(`Registration error: ${err.message}`, "error");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "[CREATE USER ACCOUNT]";
            }
        }
    });
}

function setupUserLoginTest() {
    const form = document.getElementById("users-login-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = document.getElementById("users-login-submit-btn");
        const statusBox = document.getElementById("users-login-result-box");
        const jsonBox = document.getElementById("users-login-result-json");

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "[AUTHENTICATING...]";
        }

        const email = document.getElementById("usr-login-email").value.trim();
        const password = document.getElementById("usr-login-password").value;

        try {
            const startTime = performance.now();
            const res = await fetch("/api/v1/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });

            const duration = Math.round(performance.now() - startTime);
            const data = await res.json();

            if (statusBox) statusBox.style.display = "block";
            if (jsonBox) jsonBox.textContent = JSON.stringify(data, null, 2);

            if (res.ok) {
                showToast(`[OK] Authenticated as '${email}' (${duration}ms)`, "success");
            } else {
                showToast(`Authentication failed: ${data.error_description || data.error}`, "error");
            }
        } catch (err) {
            showToast(`Login request error: ${err.message}`, "error");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "[TEST CREDENTIAL LOGIN]";
            }
        }
    });
}

function setupDemoUserPresets() {
    const presets = [
        { btnId: "preset-dev-btn", email: "developer@pulseauth.dev", pass: "DevPass2026!" },
        { btnId: "preset-admin-btn", email: "admin@pulseauth.dev", pass: "AdminPass2026!" },
        { btnId: "preset-user-btn", email: "user@pulseauth.dev", pass: "UserPass2026!" }
    ];

    presets.forEach(p => {
        const btn = document.getElementById(p.btnId);
        if (btn) {
            btn.addEventListener("click", () => {
                const emailInput = document.getElementById("usr-login-email");
                const passInput = document.getElementById("usr-login-password");
                if (emailInput) emailInput.value = p.email;
                if (passInput) passInput.value = p.pass;
                showToast(`Loaded credentials for ${p.email}`, "info");
            });
        }
    });
}

export async function loadUsersList() {
    const tableBody = document.getElementById("users-table-body");
    if (!tableBody) return;

    try {
        const res = await fetch("/api/v1/auth/users");
        if (!res.ok) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-muted" style="text-align: center;">Failed to load user directory.</td></tr>`;
            return;
        }

        const data = await res.json();
        const users = data.users || [];

        if (users.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-muted" style="text-align: center;">No registered users found.</td></tr>`;
            return;
        }

        tableBody.innerHTML = "";
        users.forEach(u => {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td><code style="font-size: 0.75rem;">${u.id}</code></td>
                <td><strong>${escapeHtml(u.email)}</strong></td>
                <td>${escapeHtml(u.name || "-")}</td>
                <td>
                    <span class="badge ${u.email_verified ? "badge-success" : "badge-warning"}">
                        ${u.email_verified ? "[VERIFIED]" : "[UNVERIFIED]"}
                    </span>
                </td>
                <td><small>${u.created_at ? u.created_at.substring(0, 10) : "-"}</small></td>
            `;

            tableBody.appendChild(tr);
        });
    } catch (err) {
        tableBody.innerHTML = `<tr><td colspan="5" class="text-danger" style="text-align: center;">Network error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
