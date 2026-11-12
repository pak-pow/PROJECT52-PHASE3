/**
 * PulseAuth OpenID Discovery & Cryptographic Metadata Viewer
 * Strict Zero-Emoji Compliant
 */

import { showToast, copyToClipboard } from "./app.js";

export function initMetadataViewer() {
    loadDiscoveryMetadata();
    loadJwksKeyset();

    const refreshBtn = document.getElementById("meta-refresh-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            loadDiscoveryMetadata();
            loadJwksKeyset();
            showToast("[OK] Provider metadata refreshed.", "info");
        });
    }

    const copyDiscoveryBtn = document.getElementById("meta-copy-discovery-btn");
    if (copyDiscoveryBtn) {
        copyDiscoveryBtn.addEventListener("click", () => {
            const text = document.getElementById("meta-discovery-json")?.textContent;
            copyToClipboard(text, "OpenID Configuration copied.");
        });
    }

    const copyJwksBtn = document.getElementById("meta-copy-jwks-btn");
    if (copyJwksBtn) {
        copyJwksBtn.addEventListener("click", () => {
            const text = document.getElementById("meta-jwks-json")?.textContent;
            copyToClipboard(text, "JWKS Keyset copied.");
        });
    }
}

async function loadDiscoveryMetadata() {
    const codeBox = document.getElementById("meta-discovery-json");
    const issuerDisplay = document.getElementById("meta-issuer-display");
    const scopesDisplay = document.getElementById("meta-scopes-display");
    const grantsDisplay = document.getElementById("meta-grants-display");

    try {
        const res = await fetch("/.well-known/openid-configuration");
        if (!res.ok) {
            if (codeBox) codeBox.textContent = `Error loading discovery: ${res.status}`;
            return;
        }

        const data = await res.json();
        if (codeBox) codeBox.textContent = JSON.stringify(data, null, 2);

        if (issuerDisplay) issuerDisplay.textContent = data.issuer || "-";
        if (scopesDisplay) {
            scopesDisplay.innerHTML = (data.scopes_supported || []).map(s => `<span class="badge badge-info" style="margin: 2px;">${s}</span>`).join(" ");
        }
        if (grantsDisplay) {
            grantsDisplay.innerHTML = (data.grant_types_supported || []).map(g => `<span class="badge badge-success" style="margin: 2px;">${g}</span>`).join(" ");
        }
    } catch (err) {
        if (codeBox) codeBox.textContent = `Network error: ${err.message}`;
    }
}

async function loadJwksKeyset() {
    const codeBox = document.getElementById("meta-jwks-json");
    const kidDisplay = document.getElementById("meta-active-kid-display");

    try {
        const res = await fetch("/.well-known/jwks.json");
        if (!res.ok) {
            if (codeBox) codeBox.textContent = `Error loading JWKS: ${res.status}`;
            return;
        }

        const data = await res.json();
        if (codeBox) codeBox.textContent = JSON.stringify(data, null, 2);

        if (kidDisplay && data.keys && data.keys.length > 0) {
            kidDisplay.textContent = data.keys[0].kid || "unknown";
        }
    } catch (err) {
        if (codeBox) codeBox.textContent = `Network error: ${err.message}`;
    }
}
