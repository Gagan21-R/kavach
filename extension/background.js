importScripts("shared.js");

const CACHE_MS = 30 * 60 * 1000; // a site's verdict is re-asked at most every 30 minutes
const LOOKING_RETRY_MS = 6000;

// Each install has its own name, so connecting again replaces this browser's old connection, not another one's.
async function installName() {
  const { install } = await chrome.storage.local.get({ install: "" });
  if (install) return install;
  const name = `Chrome · ${crypto.randomUUID().slice(0, 6)}`;
  await chrome.storage.local.set({ install: name });
  return name;
}
chrome.runtime.onInstalled.addListener(() => { installName(); });

async function cached(domain) {
  const { verdicts = {} } = await chrome.storage.session.get("verdicts");
  const hit = verdicts[domain];
  if (!hit) return null;
  const age = Date.now() - hit.at;
  if (hit.data.status === "LOOKING" ? age > LOOKING_RETRY_MS : age > CACHE_MS) return null;
  return hit.data;
}

async function remember(domain, data) {
  const { verdicts = {} } = await chrome.storage.session.get("verdicts");
  verdicts[domain] = { at: Date.now(), data };
  await chrome.storage.session.set({ verdicts });
}

const verdictOf = (data) => data?.verdict || data || {};

async function badge(tabId, data) {
  const v = verdictOf(data);
  const st = STATUS_STYLE[v.status] || STATUS_STYLE.UNKNOWN;
  await chrome.action.setBadgeText({ tabId, text: data ? (v.risk_score != null ? String(v.risk_score) : st.text) : "" });
  await chrome.action.setBadgeBackgroundColor({ tabId, color: st.color });
  await chrome.action.setTitle({ tabId, title: data ? `Kavach: ${v.recommendation ? REC_WORDS[v.recommendation] + " · " : ""}${st.label}` : "Kavach" });
}

async function check(tabId, url, force = false) {
  let host;
  try { host = new URL(url).hostname; } catch { return null; }
  if (!/^https?:/.test(url)) return badge(tabId, null);
  const s = await settings();
  if (s.paused || !s.key || skipHost(host, s)) return badge(tabId, null);
  let data = force ? null : await cached(host);
  if (!data) {
    data = await call("/ext/visit", { domain: host });
    if (data.error) return badge(tabId, null);
    await remember(host, data);
    if (data.status === "LOOKING") setTimeout(() => check(tabId, url, true), LOOKING_RETRY_MS);
  }
  const { [`page:${tabId}`]: page } = await chrome.storage.session.get(`page:${tabId}`);
  if (!page) await badge(tabId, data);
  return data;
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "loading") chrome.storage.session.remove(`page:${tabId}`);
  if (info.status === "complete" && tab.url && !tab.incognito) check(tabId, tab.url);
});
chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(`page:${tabId}`));

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    const s = await settings();
    const tab = sender.tab;
    const host = tab?.url ? new URL(tab.url).hostname : "";
    const off = s.paused || !s.key || (tab && skipHost(host, s));
    if (msg.type === "status") {
      reply({ connected: !!s.key, email: s.email, install: await installName(), paused: s.paused, skipped: tab ? skipHost(host, s) : false });
    } else if (msg.type === "paired") {
      // Sent by the content script on the Kavach dashboard after it created this browser's connection.
      const dashboard = tab && new URL(tab.url).origin === new URL(s.server).origin;
      if (dashboard && msg.key) {
        await chrome.storage.local.set({ key: msg.key, email: msg.email || "" });
        await chrome.storage.session.clear();
      }
      reply(!!dashboard);
    } else if (msg.type === "analyze" && tab) {
      if (off) return reply(null);
      const data = await call("/ext/analyze", { url: msg.url, title: msg.title, text: msg.text });
      if (!data.error) {
        await chrome.storage.session.set({ [`page:${tab.id}`]: { ...data, page: { url: msg.url, title: msg.title } } });
        await badge(tab.id, data);
      }
      reply(data);
    } else if (msg.type === "track") {
      if (s.paused || !s.key) return reply({ error: "NOT_CONNECTED" });
      const data = await call("/ext/track", { url: msg.url, title: msg.title || "", text: msg.text || "" });
      if (!data.error) {
        const tabId = tab?.id ?? msg.tabId;
        if (tabId != null) await chrome.storage.session.set({ [`page:${tabId}`]: { ...data, page: { url: msg.url, title: msg.title } } });
        await chrome.storage.session.remove("verdicts");
      }
      reply(data);
    } else if (msg.type === "consent" && tab) {
      if (off) return reply(null);
      const data = await call("/ext/consent", { domain: host, kind: msg.kind, text: msg.text, links: msg.links });
      if (!data.error) {
        await remember(host, data);
        await badge(tab.id, data);
      }
      reply(data);
    } else if (msg.type === "open-dashboard") {
      chrome.tabs.create({ url: `${s.server.replace(/\/$/, "")}/#${msg.section || "overview"}` });
      reply(true);
    } else if (msg.type === "current") {
      const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!active?.url) return reply(null);
      const { [`page:${active.id}`]: page } = await chrome.storage.session.get(`page:${active.id}`);
      const site = await check(active.id, active.url, msg.force);
      reply({ url: active.url, tabId: active.id, page: page && page.page?.url?.split("#")[0] === active.url.split("#")[0] ? page : null, data: site });
    }
  })();
  return true; // keeps the reply channel open for the async work
});
