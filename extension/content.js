// Three jobs, each only where it matters:
//  1. On the Kavach dashboard: connect this browser to the signed-in account (no key to paste).
//  2. On a privacy policy or terms page: review the whole site (this page plus its other policy) through the six
//     agents and show one result, with a button to track it.
//  3. On signup / "I agree" / cookie pages: check the consent text for instructions hidden for AI agents.
// On ordinary pages nothing is sent from here.
(() => {
  if (window.top !== window || window.__kavach) return;
  window.__kavach = true;

  const POLICY_PATH = /(privacy|terms|legal|\btos\b|policy|policies|conditions|agreement|eula)/i;
  const POLICY_TITLE = /(privacy (policy|notice|statement)|terms (of (service|use)|and conditions|& conditions)|user agreement|conditions of use|data policy|legal)/i;
  const AGREE = /\b(i agree|agree to|accept( all)?|terms( of (service|use))?|privacy (policy|notice)|consent)\b/i;
  const SIGNUP = /\b(sign ?up|create (an |your )?account|register|join now|get started)\b/i;
  const COOKIES = /\bcookies?\b/i;
  const TONE = { ALLOW: "good", REVIEW: "warn", BLOCK: "bad" };
  const PREF = { CONFLICT: ["Goes against your preferences", "bad"], CAUTION: ["Worth a look", "warn"], OK: ["Fine for your preferences", "good"] };

  const send = (msg) => new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => resolve(chrome.runtime.lastError ? null : r));
    } catch {
      resolve(null);
    }
  });

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  // ---- 1. Connect from the dashboard -----------------------------------------------------------------

  async function connectFromDashboard() {
    const st = await send({ type: "status" });
    try {
      // Same-origin requests from the dashboard page carry its session cookie; the CSRF token proves intent.
      const res = await fetch("/api/auth/session", { credentials: "same-origin" });
      if (!res.ok) return; // not signed in here: nothing to do
      const session = await res.json();
      const email = session?.user?.email;
      if (st?.connected && st.email === email) return; // already connected as this account
      const pair = await fetch("/api/extension/pair", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
        body: JSON.stringify({ name: st?.install || "Browser extension" }),
      });
      if (!pair.ok) return;
      const data = await pair.json();
      await send({ type: "paired", key: data.key, email: data.email });
    } catch {
      /* the dashboard is offline; try again on the next visit */
    }
  }

  // ---- 2. Policy pages ---------------------------------------------------------------------------------

  function mainText() {
    const root = document.querySelector("main, article, [role=main]") || document.body;
    return (root.innerText || "").replace(/\n{3,}/g, "\n\n").slice(0, 60000);
  }

  function isPolicyPage() {
    if ((document.body?.innerText || "").length < 1500) return false;
    const h1 = document.querySelector("h1")?.innerText || "";
    return POLICY_PATH.test(location.pathname) || POLICY_TITLE.test(document.title) || POLICY_TITLE.test(h1);
  }

  function panel() {
    document.getElementById("kavach-panel")?.remove();
    const box = el("div");
    box.id = "kavach-panel";
    const head = el("div", "kv-head");
    const brand = el("span", "kv-mark");
    const logo = el("img");
    logo.src = chrome.runtime.getURL("icons/32.png");
    logo.alt = "";
    brand.append(logo, el("span", "", "KAVACH"));
    const btns = el("span", "kv-btns");
    const min = el("button", "kv-x", "–");
    min.title = "Minimise";
    min.onclick = () => box.classList.toggle("kv-min");
    const x = el("button", "kv-x", "×");
    x.title = "Close";
    x.onclick = () => box.remove();
    btns.append(min, x);
    head.append(brand, btns);
    const body = el("div", "kv-body");
    body.append(el("div", "kv-muted", "Reading this site’s privacy policy and terms…"));
    box.append(head, body);
    document.documentElement.appendChild(box);
    return body;
  }

  function renderResult(body, r, page) {
    body.replaceChildren();
    if (!r || r.error) {
      const msg = r?.error === "NOT_CONNECTED"
        ? "Open Kavach in this browser while signed in, and the extension connects by itself."
        : `Couldn’t review this site: ${r?.error || "Kavach is unreachable"}.`;
      body.append(el("div", "kv-muted", msg));
      if (r?.error === "NOT_CONNECTED") {
        const open = el("button", "kv-secondary kv-gap", "Open Kavach");
        open.onclick = () => send({ type: "open-dashboard", section: "overview" });
        body.append(open);
      }
      return;
    }
    if (!r.recommendation) {
      body.append(el("div", "kv-muted", r.headline || "We couldn’t read this site’s policies."));
      return;
    }
    const tone = TONE[r.recommendation] || "warn";
    const top = el("div", "kv-top");
    const score = el("div", `kv-score kv-${tone}`);
    score.append(el("span", "kv-num", r.risk_score ?? "—"), el("span", "kv-of", "risk / 100"));
    const side = el("div");
    side.append(el("div", "kv-site", r.name || r.domain));
    side.append(el("div", `kv-rec kv-${tone}`, REC_WORDS_LOCAL[r.recommendation]));
    side.append(el("div", "kv-muted", `Confidence ${r.confidence ?? "—"}% · auditor ${String(r.audit || "").toLowerCase()}`));
    top.append(score, side);
    body.append(top);
    if (r.headline) body.append(el("p", "kv-headline", r.headline));
    if (r.hidden_instructions) body.append(el("div", "kv-alert", "This site’s policy hides instructions aimed at AI agents. Don’t let an agent accept it for you."));

    const [pText, pTone] = PREF[r.status] || ["", "warn"];
    if (pText) {
      const pref = el("div", `kv-pref kv-${pTone}`);
      pref.append(el("div", "kv-label", pText));
      const ul = el("ul");
      (r.reasons || []).slice(0, 3).forEach((t) => ul.append(el("li", "", t)));
      pref.append(ul);
      body.append(pref);
    }

    if (r.factors?.length) {
      body.append(el("div", "kv-label kv-gap", "Riskiest practices"));
      r.factors.slice(0, 5).forEach((f) => {
        const d = el("details", "kv-factor");
        const s = el("summary");
        s.append(el("span", `kv-level kv-${f.level === "high" ? "bad" : f.level === "medium" ? "warn" : "muted"}`, f.level), el("span", "", ` ${f.label}`));
        d.append(s);
        d.append(el("div", "kv-quote", f.quote ? `“${f.quote}” — ${f.source}` : f.explanation));
        body.append(d);
      });
    }
    const docs = (r.documents || []).filter((d) => !d.error).map((d) => d.label);
    if (docs.length) body.append(el("div", "kv-muted kv-gap", `Reviewed: ${docs.join(" + ")} · six agents`));

    const actions = el("div", "kv-actions");
    if (r.tracked) {
      actions.append(el("span", "kv-tracked", "✓ Tracked · Watchman is watching this site"));
    } else {
      const track = el("button", "kv-primary", "Track this website");
      track.onclick = async () => {
        track.disabled = true;
        track.textContent = "Adding…";
        const t = await send({ type: "track", ...page });
        if (t && !t.error) renderResult(body, t, page);
        else { track.disabled = false; track.textContent = "Try again"; actions.append(el("div", "kv-muted", t?.error || "Kavach is unreachable")); }
      };
      actions.append(track);
    }
    const open = el("button", "kv-secondary", "Open dashboard");
    open.onclick = () => send({ type: "open-dashboard", section: r.tracked ? "watchman" : "websites" });
    actions.append(open);
    body.append(actions);
    body.append(el("div", "kv-foot", "Explainable signals, not legal advice. Confidence is a heuristic."));
  }
  const REC_WORDS_LOCAL = { ALLOW: "Looks reasonable", REVIEW: "Needs your review", BLOCK: "Not recommended" };

  async function reviewPolicyPage() {
    const page = { url: location.href.split("#")[0], title: document.title.slice(0, 300), text: mainText() };
    const st = await send({ type: "status" });
    if (!st || st.paused || st.skipped) return;
    const body = panel();
    if (!st.connected) return renderResult(body, { error: "NOT_CONNECTED" }, page);
    renderResult(body, await send({ type: "analyze", ...page }), page);
  }

  // ---- 3. Consent moments ------------------------------------------------------------------------------

  function linksIn(root) {
    return [...root.querySelectorAll("a[href]")].map((a) => a.href)
      .filter((h) => /^https:\/\//.test(h) && /privacy|terms|legal|policy/i.test(h)).slice(0, 10);
  }

  // Hidden text matters too: instructions aimed at AI agents are usually invisible to people.
  function hiddenTextOf(root) {
    const out = [];
    root.querySelectorAll("*").forEach((n) => {
      const cs = getComputedStyle(n);
      const hidden = cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0 || parseFloat(cs.fontSize) === 0;
      if (hidden && n.textContent.trim()) out.push(n.textContent.trim());
    });
    return out.join("\n").slice(0, 4000);
  }

  function findMoment() {
    for (const f of document.querySelectorAll("form")) {
      const t = (f.innerText || "") + " " + (f.querySelector("input[type=submit]")?.value || "");
      const hasPassword = !!f.querySelector("input[type=password]");
      const hasAgree = [...f.querySelectorAll("input[type=checkbox]")].some((c) => AGREE.test(c.closest("label, div, p")?.innerText || ""));
      if ((hasPassword && SIGNUP.test(t)) || hasAgree) return { kind: hasAgree ? "agree" : "signup", el: f };
    }
    const banner = [...document.querySelectorAll("[role=dialog], [aria-modal=true], [id*=cookie i], [class*=cookie i], [id*=consent i], [class*=consent i]")]
      .find((e) => COOKIES.test(e.innerText || "") && /accept/i.test(e.innerText || ""));
    return banner ? { kind: "cookies", el: banner } : null;
  }

  function warn(data) {
    const v = data?.verdict || {};
    const hidden = data?.hidden_instructions || [];
    if (!hidden.length && v.status !== "CONFLICT" && v.status !== "CAUTION") return;
    document.getElementById("kavach-banner")?.remove();
    const box = el("div", hidden.length || v.status === "CONFLICT" ? "kv-bad" : "kv-warn");
    box.id = "kavach-banner";
    const head = el("div", "kv-head");
    const x = el("button", "kv-x", "×");
    x.onclick = () => box.remove();
    head.append(el("span", "kv-mark", "KAVACH"), x);
    const title = hidden.length ? "This page hides instructions aimed at AI agents"
      : v.status === "CONFLICT" ? "This site’s policies go against your preferences" : "Worth a look before you agree";
    const ul = el("ul", "kv-list");
    (hidden.length ? [`Hidden text says: “${hidden[0]}”. Don’t let an AI agent accept this page for you.`] : (v.reasons || []).slice(0, 3))
      .forEach((r) => ul.append(el("li", "", r)));
    box.append(head, el("div", "kv-title", title), ul);
    if (v.risk_score != null) box.append(el("div", "kv-foot", `Risk ${v.risk_score}/100 · confidence ${v.confidence ?? "—"}% · not legal advice`));
    document.documentElement.appendChild(box);
  }

  let sent = false;
  function scanConsent() {
    if (sent) return;
    const m = findMoment();
    if (!m) return;
    sent = true;
    const text = ((m.el.innerText || "").slice(0, 8000) + "\n" + hiddenTextOf(m.el)).slice(0, 12000);
    send({ type: "consent", kind: m.kind, text, links: linksIn(document) }).then(warn);
  }

  chrome.storage.local.get({ server: "http://localhost:8000" }, ({ server }) => {
    let dashboard = false;
    try { dashboard = new URL(server).origin === location.origin; } catch { /* bad server url */ }
    if (dashboard) return void connectFromDashboard();
    if (isPolicyPage()) return void reviewPolicyPage();
    scanConsent();
    const obs = new MutationObserver(() => scanConsent()); // signup forms and cookie banners often appear late
    obs.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => obs.disconnect(), 15000);
  });
})();
