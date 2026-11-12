/**
 * PulseAuth Interactive In-Browser OAuth 2.0 & OIDC Playground Console
 * Strict Zero-Emoji Compliant
 */

import { showToast, copyToClipboard } from "./app.js";

// Preset Demo Clients
export const PRESET_CLIENTS = {
    "pulse-web-app": {
        id: "pulse-web-app",
        secret: "pulse_web_secret_2026",
        type: "confidential",
        redirectUri: `${window.location.origin}/callback`,
        grantTypes: ["authorization_code", "refresh_token"],
        scopes: ["openid", "profile", "email", "offline_access", "read:documents", "write:documents"]
    },
    "pulse-mobile-app": {
        id: "pulse-mobile-app",
        secret: "",
        type: "public",
        redirectUri: `${window.location.origin}/callback`,
        grantTypes: ["authorization_code", "refresh_token"],
        scopes: ["openid", "profile", "email", "offline_access", "read:documents"]
    },
    "pulse-m2m-service": {
        id: "pulse-m2m-service",
        secret: "pulse_m2m_secret_2026",
        type: "confidential",
        redirectUri: `${window.location.origin}/callback`,
        grantTypes: ["client_credentials"],
        scopes: ["read:documents", "write:documents"]
    }
};

// State Store for Current Playground Session
const playgroundState = {
    codeVerifier: "",
    codeChallenge: "",
    codeChallengeMethod: "S256",
    authCode: "",
    tokens: {
        access_token: null,
        id_token: null,
        refresh_token: null,
        token_type: null,
        expires_in: null,
        scope: null
    }
};

// Base64URL Encoding Utility
function base64urlEncode(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary)
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
}

// Generate Cryptographically Secure PKCE Code Verifier
export function generateCodeVerifier(length = 64) {
    const charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
    const randomBytes = new Uint8Array(length);
    window.crypto.getRandomValues(randomBytes);
    let result = "";
    for (let i = 0; i < length; i++) {
        result += charset[randomBytes[i] % charset.length];
    }
    return result;
}

// Generate S256 PKCE Code Challenge from Verifier
export async function generateCodeChallenge(verifier) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const digest = await window.crypto.subtle.digest("SHA-256", data);
    return base64urlEncode(digest);
}

// Base64URL JWT Decoder
export function parseJwt(token) {
    if (!token || typeof token !== "string") return null;
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    try {
        const decodePart = (b64url) => {
            let b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
            while (b64.length % 4) {
                b64 += "=";
            }
            return JSON.parse(decodeURIComponent(escape(atob(b64))));
        };

        return {
            raw: token,
            parts: {
                headerRaw: parts[0],
                payloadRaw: parts[1],
                signatureRaw: parts[2]
            },
            header: decodePart(parts[0]),
            payload: decodePart(parts[1])
        };
    } catch (e) {
        return null;
    }
}

// Initialize Playground Controller
export function initPlayground() {
    setupClientSelector();
    setupPkceControls();
    setupAuthorizeActions();
    setupTokenExchange();
    setupResourceActions();
    setupWindowMessageReceiver();

    // Trigger initial PKCE generation
    regeneratePkce();
}

function setupClientSelector() {
    const select = document.getElementById("pg-client-select");
    const clientIdInput = document.getElementById("pg-client-id");
    const clientSecretInput = document.getElementById("pg-client-secret");
    const grantTypeSelect = document.getElementById("pg-grant-type");
    const redirectUriInput = document.getElementById("pg-redirect-uri");

    if (!select) return;

    select.addEventListener("change", () => {
        const key = select.value;
        if (key && PRESET_CLIENTS[key]) {
            const client = PRESET_CLIENTS[key];
            clientIdInput.value = client.id;
            clientSecretInput.value = client.secret;
            redirectUriInput.value = client.redirectUri;

            // Adjust grant type options based on client
            if (client.grantTypes.includes("client_credentials")) {
                grantTypeSelect.value = "client_credentials";
            } else {
                grantTypeSelect.value = "authorization_code";
            }
            updateScopeCheckboxes(client.scopes);
            updateUiForGrantType();
        } else if (key === "custom") {
            clientIdInput.value = "";
            clientSecretInput.value = "";
            redirectUriInput.value = `${window.location.origin}/callback`;
        }
    });

    grantTypeSelect.addEventListener("change", () => {
        updateUiForGrantType();
    });

    // Populate initial state
    if (select.value && PRESET_CLIENTS[select.value]) {
        const c = PRESET_CLIENTS[select.value];
        clientIdInput.value = c.id;
        clientSecretInput.value = c.secret;
        redirectUriInput.value = c.redirectUri;
        updateScopeCheckboxes(c.scopes);
        updateUiForGrantType();
    }
}

function updateScopeCheckboxes(allowedScopes) {
    const checkboxes = document.querySelectorAll("input[name='pg-scope']");
    checkboxes.forEach(cb => {
        cb.checked = allowedScopes.includes(cb.value);
    });
}

function getSelectedScopes() {
    const checkboxes = document.querySelectorAll("input[name='pg-scope']:checked");
    const scopes = [];
    checkboxes.forEach(cb => scopes.push(cb.value));
    return scopes.join(" ");
}

function updateUiForGrantType() {
    const grantType = document.getElementById("pg-grant-type").value;
    const authCodeStep = document.getElementById("step-auth-code-container");
    const pkceStep = document.getElementById("step-pkce-container");
    const codeExchangeInputs = document.getElementById("exchange-code-inputs");

    if (grantType === "client_credentials") {
        if (authCodeStep) authCodeStep.style.display = "none";
        if (pkceStep) pkceStep.style.display = "none";
        if (codeExchangeInputs) codeExchangeInputs.style.display = "none";
    } else {
        if (authCodeStep) authCodeStep.style.display = "block";
        if (pkceStep) pkceStep.style.display = "block";
        if (codeExchangeInputs) codeExchangeInputs.style.display = "block";
    }
}

async function regeneratePkce() {
    const verifierInput = document.getElementById("pg-code-verifier");
    const challengeInput = document.getElementById("pg-code-challenge");
    const methodSelect = document.getElementById("pg-challenge-method");

    const verifier = generateCodeVerifier(64);
    playgroundState.codeVerifier = verifier;

    let challenge = verifier;
    if (methodSelect && methodSelect.value === "S256") {
        challenge = await generateCodeChallenge(verifier);
        playgroundState.codeChallengeMethod = "S256";
    } else {
        playgroundState.codeChallengeMethod = "plain";
    }
    playgroundState.codeChallenge = challenge;

    if (verifierInput) verifierInput.value = verifier;
    if (challengeInput) challengeInput.value = challenge;
}

function setupPkceControls() {
    const regenBtn = document.getElementById("pg-regen-pkce-btn");
    const methodSelect = document.getElementById("pg-challenge-method");

    if (regenBtn) {
        regenBtn.addEventListener("click", () => {
            regeneratePkce();
            showToast("[OK] New cryptographically secure PKCE verifier generated.", "info");
        });
    }

    if (methodSelect) {
        methodSelect.addEventListener("change", () => {
            regeneratePkce();
        });
    }
}

function buildAuthorizationUrl() {
    const clientId = document.getElementById("pg-client-id").value.trim();
    const redirectUri = document.getElementById("pg-redirect-uri").value.trim();
    const scopes = getSelectedScopes();
    const state = document.getElementById("pg-state").value.trim() || "state_demo_" + Math.random().toString(36).substring(7);
    const nonce = document.getElementById("pg-nonce").value.trim() || "nonce_demo_" + Math.random().toString(36).substring(7);

    const params = new URLSearchParams();
    params.set("response_type", "code");
    params.set("client_id", clientId);
    params.set("redirect_uri", redirectUri);
    params.set("scope", scopes);
    params.set("state", state);
    params.set("nonce", nonce);

    const usePkce = document.getElementById("pg-use-pkce").checked;
    if (usePkce) {
        params.set("code_challenge", playgroundState.codeChallenge);
        params.set("code_challenge_method", playgroundState.codeChallengeMethod);
    }

    return `${window.location.origin}/oauth/authorize?${params.toString()}`;
}

function setupAuthorizeActions() {
    const launchBtn = document.getElementById("pg-launch-auth-btn");
    const simulateBtn = document.getElementById("pg-simulate-auth-btn");
    const copyUrlBtn = document.getElementById("pg-copy-auth-url-btn");
    const urlDisplay = document.getElementById("pg-auth-url-display");

    function refreshAuthUrlDisplay() {
        if (urlDisplay) {
            urlDisplay.textContent = buildAuthorizationUrl();
        }
    }

    // Update url on input change
    ["pg-client-id", "pg-redirect-uri", "pg-state", "pg-nonce"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("input", refreshAuthUrlDisplay);
    });

    document.querySelectorAll("input[name='pg-scope']").forEach(cb => {
        cb.addEventListener("change", refreshAuthUrlDisplay);
    });

    const usePkce = document.getElementById("pg-use-pkce");
    if (usePkce) usePkce.addEventListener("change", refreshAuthUrlDisplay);

    refreshAuthUrlDisplay();

    if (copyUrlBtn) {
        copyUrlBtn.addEventListener("click", () => {
            copyToClipboard(buildAuthorizationUrl(), "Authorization URL copied.");
        });
    }

    if (launchBtn) {
        launchBtn.addEventListener("click", () => {
            const authUrl = buildAuthorizationUrl();
            const width = 600;
            const height = 750;
            const left = window.screenX + (window.outerWidth - width) / 2;
            const top = window.screenY + (window.outerHeight - height) / 2;
            window.open(authUrl, "pulseauth_consent_popup", `width=${width},height=${height},left=${left},top=${top}`);
            showToast("Authorize consent prompt opened in popup window.", "info");
        });
    }

    if (simulateBtn) {
        simulateBtn.addEventListener("click", async () => {
            simulateBtn.disabled = true;
            simulateBtn.textContent = "[RUNNING...]";

            try {
                // 1. Log in as demo user to get session / user verification
                const loginRes = await fetch("/api/v1/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        email: "developer@pulseauth.dev",
                        password: "DevPass2026!"
                    })
                });

                if (!loginRes.ok) {
                    throw new Error("Failed to authenticate demo user developer@pulseauth.dev");
                }
                const loginData = await loginRes.json();
                const userId = loginData.user.id;

                // 2. Perform direct consent authorization request
                const authPayload = {
                    client_id: document.getElementById("pg-client-id").value.trim(),
                    redirect_uri: document.getElementById("pg-redirect-uri").value.trim(),
                    response_type: "code",
                    scope: getSelectedScopes(),
                    state: document.getElementById("pg-state").value.trim() || "simulated_state",
                    nonce: document.getElementById("pg-nonce").value.trim() || "simulated_nonce",
                    user_id: userId,
                    consent_action: "approve"
                };

                const usePkceVal = document.getElementById("pg-use-pkce").checked;
                if (usePkceVal) {
                    authPayload.code_challenge = playgroundState.codeChallenge;
                    authPayload.code_challenge_method = playgroundState.codeChallengeMethod;
                }

                const authRes = await fetch("/oauth/authorize", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(authPayload)
                });

                const authData = await authRes.json();

                if (!authRes.ok) {
                    throw new Error(authData.error_description || authData.error || "Authorization error.");
                }

                if (authData.code) {
                    setReceivedAuthorizationCode(authData.code, authData.state);
                    showToast("[OK] Authorization code successfully issued for developer@pulseauth.dev", "success");
                } else if (authData.redirect_uri) {
                    const parsedUrl = new URL(authData.redirect_uri);
                    const code = parsedUrl.searchParams.get("code");
                    const state = parsedUrl.searchParams.get("state");
                    if (code) {
                        setReceivedAuthorizationCode(code, state);
                        showToast("[OK] Code received via redirect payload.", "success");
                    }
                }
            } catch (err) {
                showToast(`Simulation failed: ${err.message}`, "error");
            } finally {
                simulateBtn.disabled = false;
                simulateBtn.textContent = "[FAST SIMULATE: LOGIN & APPROVE]";
            }
        });
    }
}

function setReceivedAuthorizationCode(code, state) {
    playgroundState.authCode = code;
    const input = document.getElementById("pg-auth-code-input");
    if (input) input.value = code;

    const exchangeCodeInput = document.getElementById("pg-exchange-code");
    if (exchangeCodeInput) exchangeCodeInput.value = code;

    const exchangeVerifierInput = document.getElementById("pg-exchange-verifier");
    if (exchangeVerifierInput) exchangeVerifierInput.value = playgroundState.codeVerifier;

    showToast(`Authorization code captured: ${code.substring(0, 12)}...`, "info");
}

function setupWindowMessageReceiver() {
    window.addEventListener("message", (event) => {
        if (event.data && event.data.type === "PULSEAUTH_CALLBACK") {
            if (event.data.code) {
                setReceivedAuthorizationCode(event.data.code, event.data.state);
                showToast("[OK] Code automatically transferred from popup window.", "success");
            } else if (event.data.error) {
                showToast(`OAuth Error: ${event.data.error} - ${event.data.error_description}`, "error");
            }
        }
    });
}

function setupTokenExchange() {
    const exchangeBtn = document.getElementById("pg-exchange-token-btn");
    if (!exchangeBtn) return;

    exchangeBtn.addEventListener("click", async () => {
        exchangeBtn.disabled = true;
        exchangeBtn.textContent = "[EXCHANGING TOKENS...]";

        const startTime = performance.now();
        const grantType = document.getElementById("pg-grant-type").value;
        const clientId = document.getElementById("pg-client-id").value.trim();
        const clientSecret = document.getElementById("pg-client-secret").value.trim();
        const authMethod = document.getElementById("pg-auth-method").value;

        const bodyParams = new URLSearchParams();
        bodyParams.set("grant_type", grantType);

        const headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        };

        if (grantType === "authorization_code") {
            const code = document.getElementById("pg-exchange-code").value.trim();
            const verifier = document.getElementById("pg-exchange-verifier").value.trim();
            const redirectUri = document.getElementById("pg-redirect-uri").value.trim();

            bodyParams.set("code", code);
            bodyParams.set("redirect_uri", redirectUri);
            if (verifier) {
                bodyParams.set("code_verifier", verifier);
            }
        } else if (grantType === "client_credentials") {
            const scopes = getSelectedScopes();
            if (scopes) {
                bodyParams.set("scope", scopes);
            }
        }

        // Apply Client Authentication
        if (authMethod === "basic" && clientSecret) {
            headers["Authorization"] = "Basic " + btoa(`${clientId}:${clientSecret}`);
        } else if (authMethod === "post") {
            bodyParams.set("client_id", clientId);
            if (clientSecret) {
                bodyParams.set("client_secret", clientSecret);
            }
        } else {
            // None / Public
            bodyParams.set("client_id", clientId);
        }

        try {
            const res = await fetch("/oauth/token", {
                method: "POST",
                headers: headers,
                body: bodyParams.toString()
            });

            const duration = Math.round(performance.now() - startTime);
            const data = await res.json();

            renderTokenResponse(res.status, duration, data);

            if (res.ok && data.access_token) {
                playgroundState.tokens = { ...data };
                inspectTokens(data.access_token, data.id_token);
                showToast(`[OK] Tokens issued in ${duration}ms`, "success");
            } else {
                showToast(`Token Exchange Failed: ${data.error || res.status}`, "error");
            }
        } catch (err) {
            showToast(`Network request failed: ${err.message}`, "error");
        } finally {
            exchangeBtn.disabled = false;
            exchangeBtn.textContent = "[EXECUTE TOKEN EXCHANGE: POST /oauth/token]";
        }
    });
}

function renderTokenResponse(status, duration, data) {
    const inspector = document.getElementById("pg-token-response-inspector");
    const statusPill = document.getElementById("pg-token-status-pill");
    const latencyPill = document.getElementById("pg-token-latency-pill");
    const rawBox = document.getElementById("pg-token-raw-json");

    if (inspector) inspector.style.display = "block";
    if (statusPill) {
        statusPill.textContent = `${status} ${status < 400 ? "OK" : "ERROR"}`;
        statusPill.className = `badge ${status < 400 ? "badge-success" : "badge-danger"}`;
    }
    if (latencyPill) {
        latencyPill.textContent = `${duration}ms`;
    }
    if (rawBox) {
        rawBox.textContent = JSON.stringify(data, null, 2);
    }
}

// RS256 JWT Claim Inspector
function inspectTokens(accessTokenStr, idTokenStr) {
    const container = document.getElementById("jwt-inspector-container");
    if (!container) return;
    container.style.display = "block";

    // 1. Inspect Access Token
    const parsedAccess = parseJwt(accessTokenStr);
    renderJwtBlock("access-token", parsedAccess, accessTokenStr);

    // 2. Inspect ID Token (if available)
    const idTokenSection = document.getElementById("jwt-id-token-section");
    if (idTokenStr) {
        if (idTokenSection) idTokenSection.style.display = "block";
        const parsedId = parseJwt(idTokenStr);
        renderJwtBlock("id-token", parsedId, idTokenStr);
    } else {
        if (idTokenSection) idTokenSection.style.display = "none";
    }
}

function renderJwtBlock(prefix, parsed, raw) {
    const rawContainer = document.getElementById(`jwt-${prefix}-raw`);
    const headerBox = document.getElementById(`jwt-${prefix}-header`);
    const payloadBox = document.getElementById(`jwt-${prefix}-payload`);
    const expBadge = document.getElementById(`jwt-${prefix}-exp-badge`);

    if (rawContainer && parsed) {
        rawContainer.innerHTML = `
            <span class="jwt-part-header">${parsed.parts.headerRaw}</span><span class="jwt-dot">.</span><span class="jwt-part-payload">${parsed.parts.payloadRaw}</span><span class="jwt-dot">.</span><span class="jwt-part-sig">${parsed.parts.signatureRaw}</span>
        `;
    }

    if (headerBox && parsed) {
        headerBox.textContent = JSON.stringify(parsed.header, null, 2);
    }

    if (payloadBox && parsed) {
        payloadBox.textContent = JSON.stringify(parsed.payload, null, 2);
    }

    if (expBadge && parsed && parsed.payload.exp) {
        const expTime = parsed.payload.exp * 1000;
        const now = Date.now();
        const isExpired = now > expTime;
        const remainingSeconds = Math.round((expTime - now) / 1000);

        if (isExpired) {
            expBadge.className = "badge badge-danger";
            expBadge.textContent = "[TOKEN EXPIRED]";
        } else {
            expBadge.className = "badge badge-success";
            expBadge.textContent = `[ACTIVE: EXPIRES IN ${remainingSeconds}s]`;
        }
    }
}

// Resource Server Actions & Inspection
function setupResourceActions() {
    const actions = [
        { id: "action-userinfo", method: "GET", url: "/oauth/userinfo", auth: "bearer" },
        { id: "action-profile", method: "GET", url: "/api/v1/resource/profile", auth: "bearer" },
        { id: "action-get-docs", method: "GET", url: "/api/v1/resource/documents", auth: "bearer" },
        {
            id: "action-post-doc",
            method: "POST",
            url: "/api/v1/resource/documents",
            auth: "bearer",
            body: { title: "PulseAuth Production Architecture", content: "Zero-Trust RS256 Specification" }
        },
        {
            id: "action-introspect",
            method: "POST",
            url: "/oauth/introspect",
            auth: "client_post",
            requiresTokenParam: true
        },
        {
            id: "action-revoke",
            method: "POST",
            url: "/oauth/revoke",
            auth: "client_post",
            requiresTokenParam: true
        },
        {
            id: "action-refresh",
            method: "POST",
            url: "/oauth/token",
            auth: "client_post",
            isRefresh: true
        }
    ];

    actions.forEach(action => {
        const btn = document.getElementById(action.id);
        if (!btn) return;

        btn.addEventListener("click", async () => {
            await executeResourceCall(action);
        });
    });
}

async function executeResourceCall(action) {
    const inspector = document.getElementById("pg-resource-response-inspector");
    const methodPill = document.getElementById("pg-res-method-pill");
    const urlText = document.getElementById("pg-res-url-text");
    const statusPill = document.getElementById("pg-res-status-pill");
    const latencyPill = document.getElementById("pg-res-latency-pill");
    const headersBox = document.getElementById("pg-res-headers-display");
    const bodyBox = document.getElementById("pg-res-body-display");

    const token = playgroundState.tokens.access_token;
    const refreshToken = playgroundState.tokens.refresh_token;

    if (action.auth === "bearer" && !token) {
        showToast("No active access token. Execute Token Exchange in Step 3 first.", "error");
        return;
    }

    if (action.isRefresh && !refreshToken) {
        showToast("No refresh token issued (did you include offline_access scope?).", "error");
        return;
    }

    const headers = {};
    let body = null;

    if (action.auth === "bearer") {
        headers["Authorization"] = `Bearer ${token}`;
    }

    if (action.method === "POST") {
        headers["Content-Type"] = "application/x-www-form-urlencoded";
        const formParams = new URLSearchParams();

        if (action.requiresTokenParam) {
            formParams.set("token", token || "");
            formParams.set("token_type_hint", "access_token");
        }

        if (action.isRefresh) {
            formParams.set("grant_type", "refresh_token");
            formParams.set("refresh_token", refreshToken);
        }

        if (action.auth === "client_post") {
            const clientId = document.getElementById("pg-client-id").value.trim();
            const clientSecret = document.getElementById("pg-client-secret").value.trim();
            formParams.set("client_id", clientId);
            if (clientSecret) formParams.set("client_secret", clientSecret);
        }

        if (action.body) {
            headers["Content-Type"] = "application/json";
            body = JSON.stringify(action.body);
        } else {
            body = formParams.toString();
        }
    }

    if (inspector) inspector.style.display = "block";
    if (methodPill) methodPill.textContent = action.method;
    if (urlText) urlText.textContent = action.url;
    if (headersBox) headersBox.textContent = JSON.stringify(headers, null, 2);

    const startTime = performance.now();
    try {
        const res = await fetch(action.url, {
            method: action.method,
            headers: headers,
            body: body
        });

        const duration = Math.round(performance.now() - startTime);
        let responseData;
        const contentType = res.headers.get("content-type") || "";

        if (contentType.includes("application/json")) {
            responseData = await res.json();
        } else {
            responseData = await res.text();
        }

        if (statusPill) {
            statusPill.textContent = `${res.status} ${res.statusText || (res.ok ? "OK" : "ERROR")}`;
            statusPill.className = `badge ${res.ok ? "badge-success" : "badge-danger"}`;
        }
        if (latencyPill) latencyPill.textContent = `${duration}ms`;
        if (bodyBox) {
            bodyBox.textContent = typeof responseData === "object"
                ? JSON.stringify(responseData, null, 2)
                : responseData;
        }

        // Handle refresh token update
        if (action.isRefresh && res.ok && responseData.access_token) {
            playgroundState.tokens.access_token = responseData.access_token;
            if (responseData.refresh_token) {
                playgroundState.tokens.refresh_token = responseData.refresh_token;
            }
            inspectTokens(responseData.access_token, responseData.id_token);
            showToast(`[OK] Token refreshed & rotated in ${duration}ms!`, "success");
        } else {
            showToast(`[${action.method}] ${action.url} -> ${res.status} (${duration}ms)`, res.ok ? "success" : "error");
        }
    } catch (err) {
        showToast(`Request failed: ${err.message}`, "error");
    }
}
