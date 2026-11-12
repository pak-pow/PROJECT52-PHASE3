/**
 * PulseAuth Developer Client Management Portal
 * Strict Zero-Emoji Compliant
 */

import { showToast, copyToClipboard } from "./app.js";
import { PRESET_CLIENTS } from "./sandbox_playground.js";

export function initClientPortal() {
    setupClientRegistrationForm();
    loadRegisteredClients();

    const refreshBtn = document.getElementById("portal-refresh-clients-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadRegisteredClients();
            showToast("[OK] Client registry refreshed.", "info");
        });
    }
}

function setupClientRegistrationForm() {
    const form = document.getElementById("portal-client-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = document.getElementById("portal-register-submit-btn");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "[REGISTERING...]";
        }

        const name = document.getElementById("reg-client-name").value.trim();
        const clientType = document.getElementById("reg-client-type").value;
        const redirectUrisRaw = document.getElementById("reg-redirect-uris").value.trim();
        const redirectUris = redirectUrisRaw.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);

        const grantTypeCheckboxes = document.querySelectorAll("input[name='reg-grant-type']:checked");
        const grantTypes = [];
        grantTypeCheckboxes.forEach(cb => grantTypes.push(cb.value));

        const scopeCheckboxes = document.querySelectorAll("input[name='reg-scope']:checked");
        const scopes = [];
        scopeCheckboxes.forEach(cb => scopes.push(cb.value));

        const payload = {
            client_name: name,
            client_type: clientType,
            redirect_uris: redirectUris,
            allowed_grant_types: grantTypes,
            allowed_scopes: scopes
        };

        try {
            const res = await fetch("/api/v1/clients", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok) {
                showToast(`[OK] Client '${name}' successfully registered!`, "success");
                displayNewClientCredentials(data);
                form.reset();
                loadRegisteredClients();
            } else {
                showToast(`Registration failed: ${data.error_description || data.error}`, "error");
            }
        } catch (err) {
            showToast(`Registration error: ${err.message}`, "error");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "[REGISTER APPLICATION]";
            }
        }
    });
}

function displayNewClientCredentials(clientData) {
    const card = document.getElementById("portal-new-credentials-card");
    const idDisplay = document.getElementById("new-cred-client-id");
    const secretDisplay = document.getElementById("new-cred-client-secret");
    const secretRow = document.getElementById("new-cred-secret-row");
    const copyIdBtn = document.getElementById("new-cred-copy-id-btn");
    const copySecretBtn = document.getElementById("new-cred-copy-secret-btn");

    if (!card) return;
    card.style.display = "block";

    if (idDisplay) idDisplay.textContent = clientData.client_id;

    if (clientData.client_secret) {
        if (secretRow) secretRow.style.display = "flex";
        if (secretDisplay) secretDisplay.textContent = clientData.client_secret;
    } else {
        if (secretRow) secretRow.style.display = "none";
    }

    if (copyIdBtn) {
        copyIdBtn.onclick = () => copyToClipboard(clientData.client_id, "Client ID copied.");
    }
    if (copySecretBtn && clientData.client_secret) {
        copySecretBtn.onclick = () => copyToClipboard(clientData.client_secret, "Client Secret copied.");
    }

    card.scrollIntoView({ behavior: "smooth" });
}

export async function loadRegisteredClients() {
    const tableBody = document.getElementById("portal-clients-table-body");
    if (!tableBody) return;

    try {
        const res = await fetch("/api/v1/clients");
        if (!res.ok) {
            tableBody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align: center;">Failed to load clients.</td></tr>`;
            return;
        }

        const data = await res.json();
        const clients = data.clients || [];

        if (clients.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align: center;">No registered clients found.</td></tr>`;
            return;
        }

        tableBody.innerHTML = "";
        clients.forEach(c => {
            const tr = document.createElement("tr");

            const isConfidential = c.client_type === "confidential";
            const badgeClass = isConfidential ? "badge-info" : "badge-success";
            const typeLabel = isConfidential ? "[CONFIDENTIAL]" : "[PUBLIC]";

            const scopesText = (c.allowed_scopes || []).map(s => `<span class="badge" style="font-size: 0.65rem; margin: 1px;">${s}</span>`).join(" ");
            const urisText = (c.redirect_uris || []).join(", ") || "-";

            tr.innerHTML = `
                <td>
                    <strong>${escapeHtml(c.client_name)}</strong><br>
                    <code style="font-size: 0.75rem; color: var(--text-secondary);">${c.client_id}</code>
                </td>
                <td><span class="badge ${badgeClass}">${typeLabel}</span></td>
                <td><small>${scopesText}</small></td>
                <td><small style="word-break: break-all;">${escapeHtml(urisText)}</small></td>
                <td><small>${c.created_at ? c.created_at.substring(0, 10) : "-"}</small></td>
                <td style="white-space: nowrap;">
                    <button class="btn btn-sm btn-secondary btn-load-pg" data-id="${c.client_id}" title="Test in Playground">[PLAYGROUND]</button>
                    ${isConfidential ? `<button class="btn btn-sm btn-secondary btn-rotate-sec" data-id="${c.client_id}" title="Rotate Secret">[ROTATE]</button>` : ""}
                    <button class="btn btn-sm btn-danger btn-delete-client" data-id="${c.client_id}" title="Delete Client">[DELETE]</button>
                </td>
            `;

            tableBody.appendChild(tr);
        });

        attachClientActionHandlers();
    } catch (err) {
        tableBody.innerHTML = `<tr><td colspan="6" class="text-danger" style="text-align: center;">Network error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function attachClientActionHandlers() {
    // Delete Client
    document.querySelectorAll(".btn-delete-client").forEach(btn => {
        btn.addEventListener("click", async () => {
            const clientId = btn.getAttribute("data-id");
            if (!confirm(`Are you sure you want to delete client '${clientId}'?`)) return;

            try {
                const res = await fetch(`/api/v1/clients/${clientId}`, { method: "DELETE" });
                if (res.ok) {
                    showToast(`[OK] Client '${clientId}' deleted.`, "success");
                    loadRegisteredClients();
                } else {
                    const data = await res.json();
                    showToast(`Delete failed: ${data.error_description || data.error}`, "error");
                }
            } catch (err) {
                showToast(`Delete request error: ${err.message}`, "error");
            }
        });
    });

    // Rotate Secret
    document.querySelectorAll(".btn-rotate-sec").forEach(btn => {
        btn.addEventListener("click", async () => {
            const clientId = btn.getAttribute("data-id");
            if (!confirm(`Rotate secret for '${clientId}'? Existing secret will be immediately invalidated.`)) return;

            try {
                const res = await fetch(`/api/v1/clients/${clientId}/rotate-secret`, { method: "POST" });
                const data = await res.json();
                if (res.ok) {
                    displayNewClientCredentials({
                        client_id: clientId,
                        client_secret: data.client_secret
                    });
                    showToast(`[OK] Secret rotated for '${clientId}'!`, "success");
                } else {
                    showToast(`Rotation failed: ${data.error_description || data.error}`, "error");
                }
            } catch (err) {
                showToast(`Rotate secret error: ${err.message}`, "error");
            }
        });
    });

    // Load in Playground
    document.querySelectorAll(".btn-load-pg").forEach(btn => {
        btn.addEventListener("click", () => {
            const clientId = btn.getAttribute("data-id");
            const clientIdInput = document.getElementById("pg-client-id");
            const clientSelect = document.getElementById("pg-client-select");
            const clientSecretInput = document.getElementById("pg-client-secret");

            if (clientSelect) {
                if (PRESET_CLIENTS[clientId]) {
                    clientSelect.value = clientId;
                    clientSelect.dispatchEvent(new Event("change"));
                } else {
                    clientSelect.value = "custom";
                    clientSelect.dispatchEvent(new Event("change"));
                    if (clientIdInput) clientIdInput.value = clientId;
                    if (clientSecretInput) clientSecretInput.value = "";
                }
            }

            // Switch to playground tab
            window.location.hash = "playground";
            showToast(`Loaded '${clientId}' into Playground Console.`, "info");
        });
    });
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
