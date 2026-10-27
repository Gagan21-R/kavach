// Thin client for the Kavach API. Session auth is an HttpOnly cookie; writes also send the CSRF token.
// Agent calls send X-Agent-Key (and X-Consent-Token at the gateway) exactly as a real agent would.

let csrf = null;
let stepUpHandler = null;
let unauthorizedHandler = null;

export function setCsrf(token) { csrf = token; }
export function onStepUp(fn) { stepUpHandler = fn; }
export function onUnauthorized(fn) { unauthorizedHandler = fn; }

export class ApiError extends Error {
  constructor(status, body) {
    const err = body?.error || {};
    super(err.message || (Array.isArray(body?.detail) ? body.detail.map((d) => d.msg).join("; ") : `HTTP ${status}`));
    this.status = status;
    this.code = err.code || (status === 422 ? "VALIDATION_ERROR" : undefined);
    this.body = body;
  }
}

async function raw(method, path, { body, agentKey, consentToken } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (agentKey) headers["X-Agent-Key"] = agentKey;
  if (consentToken !== undefined) headers["X-Consent-Token"] = consentToken;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  return { res, data };
}

// Calls that only read or preview (even though they POST) do not refresh the rest of the dashboard.
const QUIET = ["/auth/", "/chat", "/demo/trap", "/provider-requests/draft"];

export async function api(method, path, opts = {}) {
  let { res, data } = await raw(method, path, opts);
  if (res.status === 403 && data?.error?.code === "STEP_UP_REQUIRED" && stepUpHandler && !opts.agentKey) {
    const ok = await stepUpHandler();
    if (ok) ({ res, data } = await raw(method, path, opts));
  }
  if (res.status === 401 && !opts.agentKey && unauthorizedHandler && !path.startsWith("/auth/")) unauthorizedHandler();
  if (res.ok && method !== "GET" && !QUIET.some((p) => path.startsWith(p))) {
    window.dispatchEvent(new Event("kavach:changed"));
  }
  if (!res.ok && !opts.allowError) throw new ApiError(res.status, data);
  return opts.allowError ? { status: res.status, data } : data;
}

export const get = (p, o) => api("GET", p, o);
export const post = (p, body, o = {}) => api("POST", p, { ...o, body: body ?? {} });
export const put = (p, body, o = {}) => api("PUT", p, { ...o, body });
export const del = (p, o) => api("DELETE", p, o);
