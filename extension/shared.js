// Helpers shared by the background worker, popup and options page.
// Privacy: on ordinary pages only the site's domain ever leaves the browser.

const DEFAULTS = { server: "http://localhost:8000", key: "", email: "", install: "", paused: false, excluded: [] };

async function settings() {
  const s = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...s };
}

// Hosts never checked: the Kavach dashboard itself, local addresses, IPs and browser pages.
function skipHost(host, s) {
  if (!host || !host.includes(".")) return true;
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host) || host.startsWith("[") || host.endsWith(".localhost") || host === "localhost") return true;
  try { if (new URL(s.server).hostname === host) return true; } catch { /* bad server url */ }
  return s.excluded.some((d) => host === d || host.endsWith("." + d));
}

async function call(path, body) {
  const s = await settings();
  if (!s.key) return { error: "NOT_CONNECTED" };
  try {
    const res = await fetch(`${s.server.replace(/\/$/, "")}/api${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-Extension-Key": s.key },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      await chrome.storage.local.set({ key: "", email: "" }); // connection was replaced or revoked
      return { error: "NOT_CONNECTED" };
    }
    if (!res.ok) return { error: data?.error?.message || `HTTP ${res.status}` };
    return data;
  } catch {
    return { error: "OFFLINE" };
  }
}

const STATUS_STYLE = {
  OK: { text: "OK", color: "#5fa57f", label: "Fine for your preferences" },
  CAUTION: { text: "!", color: "#d9893e", label: "Worth a look" },
  CONFLICT: { text: "✕", color: "#e0523f", label: "Goes against your preferences" },
  LOOKING: { text: "…", color: "#565d6b", label: "Reading the site's policies" },
  UNKNOWN: { text: "?", color: "#565d6b", label: "No verdict yet" },
};
const REC_WORDS = { ALLOW: "Looks reasonable", REVIEW: "Needs your review", BLOCK: "Not recommended" };
