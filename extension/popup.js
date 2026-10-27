const main = document.getElementById("main");
const TONE = { ALLOW: "#7fd3a6", REVIEW: "#f2a65a", BLOCK: "#ff6b5b" };

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function review(r) {
  const wrap = el("div");
  wrap.append(el("div", "site", r.domain || ""));
  wrap.append(el("div", "name", r.name || r.domain || ""));
  if (!r.recommendation) {
    const st = STATUS_STYLE[r.status] || STATUS_STYLE.UNKNOWN;
    wrap.append(el("p", "muted", (r.reasons || [st.label])[0]));
    return wrap;
  }
  const row = el("div", "verdict");
  const score = el("span", "score", String(r.risk_score));
  score.style.borderColor = TONE[r.recommendation];
  score.style.color = TONE[r.recommendation];
  const words = el("div");
  const rec = el("div", "rec", REC_WORDS[r.recommendation]);
  rec.style.color = TONE[r.recommendation];
  words.append(rec, el("div", "muted", `Confidence ${r.confidence ?? "—"}% · risk out of 100`));
  row.append(score, words);
  wrap.append(row);
  const st = STATUS_STYLE[r.status];
  if (st) {
    const p = el("div", "pref", st.label);
    p.style.color = st.color;
    wrap.append(p);
  }
  const ul = el("ul");
  (r.reasons || []).slice(0, 3).forEach((t) => ul.append(el("li", "", t)));
  wrap.append(ul);
  if (r.factors?.length) {
    wrap.append(el("div", "label", "Riskiest practices"));
    const fl = el("ul");
    r.factors.slice(0, 4).forEach((f) => fl.append(el("li", "", `${f.label} — ${f.level}`)));
    wrap.append(fl);
  }
  return wrap;
}

async function render(force = false) {
  const s = await settings();
  document.getElementById("dash").onclick = () => chrome.tabs.create({ url: s.server });
  document.getElementById("pause").checked = s.paused;
  main.replaceChildren();
  if (!s.key) {
    main.append(el("p", "", "Open Kavach in this browser while you’re signed in. The extension connects by itself; there’s nothing to paste."));
    const b = el("button", "", "Open Kavach");
    b.onclick = () => chrome.tabs.create({ url: s.server });
    main.append(b);
    return;
  }
  if (s.paused) {
    main.append(el("p", "muted", "Checks are paused. Kavach isn’t looking at any sites."));
    return;
  }
  const cur = await chrome.runtime.sendMessage({ type: "current", force });
  if (!cur?.page && !cur?.data) {
    main.append(el("p", "muted", "Kavach doesn’t check this page (browser pages, local addresses and sites you excluded are skipped)."));
    return;
  }
  const r = cur.page || cur.data.verdict || {};
  main.append(review({ ...r, domain: r.domain || cur.data?.domain }));
  const actions = el("div", "actions");
  if (r.tracked) {
    actions.append(el("span", "ok", "✓ Tracked · Watchman is watching"));
  } else if (r.recommendation) {
    const b = el("button", "", "Track this website");
    b.onclick = async () => {
      b.disabled = true;
      b.textContent = "Adding…";
      const t = await chrome.runtime.sendMessage({ type: "track", tabId: cur.tabId, url: cur.url, title: "" });
      if (t?.error) { b.disabled = false; b.textContent = "Try again"; main.append(el("p", "muted", t.error)); } else render(true);
    };
    actions.append(b);
  }
  main.append(actions);
  if (cur.data?.status === "LOOKING") setTimeout(() => render(true), 6000);
}

document.getElementById("pause").onchange = async (e) => {
  await chrome.storage.local.set({ paused: e.target.checked });
  render();
};

(async () => {
  const s = await settings();
  document.getElementById("who").textContent = s.email ? s.email : "Not connected";
})();
render();
