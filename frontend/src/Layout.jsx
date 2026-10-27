import { Bell, CheckCheck, LogOut, MessageCircle, OctagonX, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router-dom";
import { get, post } from "./api";
import AssistantPanel from "./AssistantPanel";
import { TABS, tabOf } from "./Dashboard";
import { useAuth } from "./state";
import { Button, ErrorNote, Field, KavachMark, Modal, cx, fmtTime, goTo, inputCls } from "./ui";

function StepUpModal() {
  const { stepUp, finishStepUp, user } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!stepUp) return null;
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await post("/auth/step-up", { password });
      setPassword("");
      setError(null);
      finishStepUp(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal eyebrow="Step-up · re-authentication" title="Confirm it's you" onClose={() => finishStepUp(false)}>
      <form onSubmit={submit} className="space-y-5">
        <p className="text-[14px] leading-relaxed text-fg2">This change loosens your protections, so Kavach needs the password for <span className="text-fg">{user?.email}</span> again. It stays confirmed for 5 minutes.</p>
        <Field label="Password"><input autoFocus type="password" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <ErrorNote error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => finishStepUp(false)}>Cancel</Button>
          <Button variant="primary" loading={busy}>Confirm</Button>
        </div>
      </form>
    </Modal>
  );
}

function Drawer({ open, onClose }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-[#0b0b0b]/40" onMouseDown={onClose}>
      <aside className="drawer-in flex h-full w-full max-w-[440px] flex-col border-l-2 border-fg bg-surface" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b-2 border-fg bg-yellow px-6 py-4">
          <div>
            <div className="label text-muted">Explainer · read-only</div>
            <div className="mt-0.5 text-[17px] tracking-[-0.02em]">Ask Kavach</div>
          </div>
          <button onClick={onClose} className=" p-1.5 text-muted hover:bg-raised hover:text-fg" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <AssistantPanel compact />
      </aside>
    </div>
  );
}

const NOTE_TONE = { bad: "border-ember bg-ember/10", warn: "border-sand bg-sand/10", info: "border-gold bg-gold/10" };

/** The bell: the few new things to take care of. Reading one clears it from the list. */
function Notifications({ go }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ unread_count: 0, items: [] });
  const box = useRef(null);
  const load = () => get("/notifications").then(setData).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    const h = () => load();
    window.addEventListener("kavach:changed", h);
    return () => { clearInterval(t); window.removeEventListener("kavach:changed", h); };
  }, []);
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => e.key === "Escape" && setOpen(false);
    const away = (e) => { if (!box.current?.contains(e.target)) setOpen(false); };
    window.addEventListener("keydown", k);
    window.addEventListener("mousedown", away);
    return () => { window.removeEventListener("keydown", k); window.removeEventListener("mousedown", away); };
  }, [open]);
  const read = async (n, thenGo) => {
    await post(`/notifications/${n.id}/read`).catch(() => {});
    setData((d) => ({ unread_count: Math.max(0, d.unread_count - 1), items: d.items.filter((x) => x.id !== n.id) }));
    if (thenGo && n.section) { setOpen(false); go(n.section); }
  };
  const clearAll = async () => { await post("/notifications/read-all").catch(() => {}); setData({ unread_count: 0, items: [] }); };

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen(!open)} aria-label={`Notifications, ${data.unread_count} new`} aria-expanded={open}
        className={cx("relative flex h-10 w-10 items-center justify-center border-2 border-fg transition-colors", open ? "bg-fg text-surface" : "bg-surface hover:bg-yellow")}>
        <Bell className="h-4 w-4" strokeWidth={2} />
        {data.unread_count > 0 && (
          <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center border-2 border-fg bg-ember px-1 font-mono text-[10px] font-bold text-surface">{data.unread_count}</span>
        )}
      </button>
      {open && (
        <div className="card fade fixed inset-x-4 top-[76px] z-50 sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-[420px]">
          <div className="flex items-center justify-between border-b-2 border-fg bg-yellow px-4 py-3">
            <span className="font-bold uppercase">Needs your attention</span>
            {data.items.length > 0 && <button onClick={clearAll} className="label flex items-center gap-1 text-fg hover:underline"><CheckCheck className="h-3.5 w-3.5" />Mark all read</button>}
          </div>
          {!data.items.length ? (
            <p className="px-4 py-8 text-center text-[14px] text-fg2">All caught up. New policy changes, risky sites and agent requests show up here.</p>
          ) : (
            <ul className="scroll-thin max-h-[60vh] divide-y-2 divide-line overflow-auto">
              {data.items.map((n) => (
                <li key={n.id} className="px-4 py-3">
                  <div className="flex items-start gap-3">
                    <span className={cx("mt-1 h-3 w-3 shrink-0 border-2", NOTE_TONE[n.tone] || NOTE_TONE.info)} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] font-bold leading-snug text-fg">{n.title}</div>
                      {n.body && <div className="mt-0.5 line-clamp-2 text-[13px] text-fg2">{n.body}</div>}
                      <div className="mt-2 flex items-center gap-3">
                        {n.section && <button onClick={() => read(n, true)} className="label text-gold hover:underline">Open ↗</button>}
                        <button onClick={() => read(n, false)} className="label hover:text-fg">Mark read</button>
                        <span className="ml-auto font-mono text-[10.5px] text-dim">{fmtTime(n.created_at)}</span>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** A running strip of live status, like a news ticker. */
function Ticker() {
  const [items, setItems] = useState([]);
  const load = async () => {
    try {
      const [w, s] = await Promise.all([get("/watchman/status"), get("/emergency-stop/status")]);
      setItems([
        s.frozen ? "Agents frozen" : "Guardian online",
        `Watching ${w.policies} ${w.policies === 1 ? "policy" : "policies"}`,
        w.needs_review ? `${w.needs_review} change${w.needs_review === 1 ? "" : "s"} to review` : "No changes to review",
        `Checks every ${Math.round(w.every_minutes / 60)} h`,
        w.unknown ? `${w.unknown} couldn't be read` : "Every policy readable",
        "Explainable, not legal advice",
      ]);
    } catch { /* signed out */ }
  };
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("kavach:changed", h);
    return () => window.removeEventListener("kavach:changed", h);
  }, []);
  if (!items.length) return null;
  const row = items.map((t, i) => (
    <span key={i} className="flex items-center gap-6 px-6 font-mono text-[12px] font-bold uppercase tracking-[0.06em]">
      {t}<span className="text-yellow">✦</span>
    </span>
  ));
  return (
    <div className="overflow-hidden border-y-2 border-fg bg-fg py-2.5 text-surface" aria-hidden="true">
      <div className="ticker-track whitespace-nowrap">{row}{row}{row}{row}</div>
    </div>
  );
}

export default function Layout() {
  const { user, logout, frozen } = useAuth();
  const [ask, setAsk] = useState(false);
  const [tab, setTab] = useState(() => tabOf((window.location.hash || "").slice(1)) || "home");

  // goTo(id) from anywhere: open the tab that holds the section, then scroll to it.
  useEffect(() => {
    const h = (e) => {
      const { id, smooth } = e.detail;
      const t = tabOf(id);
      if (!t) return;
      setTab(t);
      setTimeout(() => {
        const el = document.getElementById(id);
        if (TABS.some((x) => x.id === id) || !el) window.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
        else el.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
      }, 60);
      window.history.replaceState(null, "", `#${id}`);
    };
    window.addEventListener("kavach:goto", h);
    const first = (window.location.hash || "").slice(1);
    const t0 = first && !TABS.some((x) => x.id === first) && tabOf(first) ? setTimeout(() => goTo(first, false), 350) : null;
    return () => { window.removeEventListener("kavach:goto", h); clearTimeout(t0); };
  }, []);

  return (
    <div className="dotgrid min-h-full">
      <header className="sticky top-0 z-30 border-b-2 border-fg bg-bg">
        <div className="mx-auto flex h-[68px] max-w-[1320px] items-center gap-3 px-4 sm:px-6">
          <button onClick={() => goTo("home")} className="flex shrink-0 items-center gap-2.5" aria-label="Kavach — home">
            <span className="flex h-10 w-10 items-center justify-center border-2 border-fg bg-[#05070c]"><KavachMark className="h-7 w-7" /></span>
            <span className="wordmark hidden text-[15px] text-fg sm:inline">KAVACH</span>
          </button>
          <nav aria-label="Main" className="ml-2 hidden gap-2 md:flex">
            {TABS.map(({ id, label: name, icon: Icon }) => (
              <button key={id} onClick={() => goTo(id)} aria-current={tab === id ? "page" : undefined}
                className={cx("flex h-10 items-center gap-2 border-2 px-3.5 font-mono text-[12px] font-bold uppercase tracking-[0.04em] transition-colors",
                  tab === id ? "border-fg bg-fg text-surface" : "border-fg bg-surface text-fg hover:bg-yellow")}>
                <Icon className="h-4 w-4" strokeWidth={2} />{name}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <button onClick={() => goTo("emergency-stop")} title={frozen ? "Agents are frozen: open the emergency stop" : "Emergency stop: freeze every AI agent"}
              className={cx("flex h-10 items-center gap-2 border-2 border-fg px-3 font-mono text-[12px] font-bold uppercase",
                frozen ? "bg-ember text-surface" : "bg-surface text-ember hover:bg-ember hover:text-surface")}>
              <OctagonX className="h-4 w-4" strokeWidth={2} />{frozen ? "Frozen" : "Stop"}
            </button>
            <Notifications go={goTo} />
            <span className="hidden max-w-[180px] truncate font-mono text-[11px] text-fg2 xl:block">{user?.email}</span>
            <button onClick={logout} title="Sign out" className="flex h-10 w-10 items-center justify-center border-2 border-fg bg-surface hover:bg-yellow"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
        <nav aria-label="Main" className="flex gap-2 overflow-x-auto px-4 pb-3 md:hidden">
          {TABS.map(({ id, label: name, icon: Icon }) => (
            <button key={id} onClick={() => goTo(id)}
              className={cx("flex h-9 shrink-0 items-center gap-2 border-2 border-fg px-3 font-mono text-[11px] font-bold uppercase",
                tab === id ? "bg-fg text-surface" : "bg-surface text-fg")}>
              <Icon className="h-3.5 w-3.5" />{name}
            </button>
          ))}
        </nav>
        <Ticker />
        {frozen && (
          <div className="border-b-2 border-fg bg-ember text-surface">
            <div className="mx-auto flex max-w-[1320px] items-center gap-3 px-6 py-2 font-mono text-[12px] font-bold uppercase">
              <OctagonX className="h-4 w-4" /> Every protected agent action is frozen
              <button onClick={() => goTo("emergency-stop")} className="ml-auto underline underline-offset-4">Open emergency stop</button>
            </div>
          </div>
        )}
      </header>

      <main>
        <div className="mx-auto max-w-[1320px] px-4 pb-24 pt-10 sm:px-6"><Outlet context={{ tab }} /></div>
        <footer className="mx-auto flex max-w-[1320px] flex-col gap-3 border-t-2 border-fg px-6 pb-16 pt-6 font-mono text-[11px] font-bold uppercase text-fg2 md:flex-row md:items-center md:justify-between">
          <span className="flex items-center gap-2.5 text-fg"><span className="flex h-6 w-6 items-center justify-center bg-[#05070c]"><KavachMark className="h-5 w-5" /></span>Kavach · consent, guarded</span>
          <span>Explainable signals, not legal advice</span>
          <button onClick={() => goTo("home")} className="text-left hover:underline">Back to top ↑</button>
        </footer>
      </main>

      <button onClick={() => setAsk(true)}
        className="fixed bottom-6 right-6 z-30 inline-flex h-12 items-center gap-2.5 border-2 border-fg bg-yellow px-4 font-mono text-[12px] font-bold uppercase text-fg shadow-[4px_4px_0_#0b0b0b] transition-transform hover:-translate-y-0.5">
        <MessageCircle className="h-4 w-4" strokeWidth={2} /> Ask Kavach
      </button>

      <Drawer open={ask} onClose={() => setAsk(false)} />
      <StepUpModal />
    </div>
  );
}
