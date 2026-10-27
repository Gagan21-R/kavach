import { Check, ChevronDown, LifeBuoy, OctagonX, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { get, post } from "../api";
import { useAuth, useLoad } from "../state";
import { Button, Card, Chip, Empty, ErrorNote, Field, PageHeader, cx, fmtTime, inputCls, label } from "../ui";

const STATE_TONE = { SUSPECTED: "sand", CONTAINED: "ember", INVESTIGATING: "sand", RECOVERING: "fg", RESOLVED: "mint" };
const NODE = { SUSPECTED: "border-sand", CONTAINED: "border-ember bg-ember", INVESTIGATING: "border-sand", RECOVERING: "border-fg2", RESOLVED: "border-mint bg-mint" };
const REASONS = ["An AI agent is acting strangely", "I shared an agent key by mistake", "My account may be compromised", "Just a drill"];
const OPTIONS = [
  ["revoke_tokens", "Cancel every active agent permission", true],
  ["deny_pending_approvals", "Deny agent requests waiting for you", true],
  ["revoke_other_sessions", "Sign out every other device", true],
  ["pause_monitoring", "Pause scheduled checks for this account", true],
  ["disconnect_extensions", "Disconnect browser extensions", false],
  ["revoke_agents", "Disable all agent keys (you’ll issue new ones)", false],
];
const HOLD_MS = 900;

/** Press and hold so a stray click can't fire it; Enter or Space works at once for keyboard users. */
function HoldButton({ disabled, busy, onFire }) {
  const [p, setP] = useState(0);
  const timer = useRef(null);
  const start = useRef(0);
  const stop = () => { cancelAnimationFrame(timer.current); setP(0); };
  const tick = () => {
    const k = Math.min(1, (performance.now() - start.current) / HOLD_MS);
    setP(k);
    if (k >= 1) { stop(); onFire(); } else timer.current = requestAnimationFrame(tick);
  };
  useEffect(() => () => cancelAnimationFrame(timer.current), []);
  return (
    <button type="button" disabled={disabled || busy}
      onPointerDown={() => { if (disabled || busy) return; start.current = performance.now(); timer.current = requestAnimationFrame(tick); }}
      onPointerUp={stop} onPointerLeave={stop}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onFire(); } }}
      className="group relative flex h-24 w-full select-none items-center justify-between overflow-hidden border-2 border-fg bg-surface px-7 text-ember shadow-[4px_4px_0_#0b0b0b] transition-colors hover:bg-ember/10 disabled:opacity-40">
      <span className="absolute inset-y-0 left-0 bg-ember transition-none" style={{ width: `${p * 100}%` }} />
      <span className={cx("relative text-left", p > 0.45 && "text-surface")}>
        <span className="block font-mono text-[10.5px] uppercase tracking-[0.16em] opacity-80">{busy ? "Containing…" : "Press and hold"}</span>
        <span className="block font-display text-[22px] font-bold uppercase tracking-[0.04em]">Stop all agents</span>
      </span>
      <OctagonX className={cx("relative h-10 w-10 transition-transform group-hover:rotate-12", p > 0.85 && "text-surface")} strokeWidth={2} />
    </button>
  );
}

export default function Emergency() {
  const { setFrozen } = useAuth();
  const status = useLoad(() => get("/emergency-stop/status"));
  const incidents = useLoad(() => get("/incidents"));
  const [reason, setReason] = useState("");
  const [opts, setOpts] = useState(Object.fromEntries(OPTIONS.map(([k, , d]) => [k, d])));
  const [rec, setRec] = useState({ findings: "", confirmation: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState(false);
  const s = status.data;
  const active = s?.active_incident;
  const impact = s?.impact;

  const refresh = async () => { await Promise.all([status.reload(), incidents.reload()]); setFrozen((await get("/emergency-stop/status")).frozen); };
  const run = (key, fn) => async () => { setBusy(key); setError(null); try { await fn(); await refresh(); } catch (e) { setError(e); } finally { setBusy(null); } };
  const activate = run("stop", () => post("/emergency-stop/activate", { reason: reason || "Emergency stop", ...opts }));
  const recover = run("recover", () => post("/emergency-stop/recover", { incident_id: active.id, ...rec }));
  const addNote = run("note", async () => { await post(`/incidents/${active.id}/notes`, { note }); setNote(""); });
  const past = (incidents.data || []).filter((i) => i.id !== active?.id);

  return (
    <div id="emergency-stop" className="scroll-mt-[96px]">
      <PageHeader eyebrow="AI agents · Emergency stop" title={s?.frozen ? "Contained." : "Stop everything."}
        subtitle="If an agent or a key may be misused: stop first, look at what happened, then recover deliberately. Nothing is deleted, so the evidence stays." />
      <ErrorNote error={error} />
      {!s ? null : !s.frozen ? (
        <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
          <Card title="What a stop does right now" meta="Every protected agent action is refused until you recover">
            <div className="hairgrid grid grid-cols-2 gap-px overflow-hidden border-2 border-fg sm:grid-cols-3">
              {[["Agents frozen", impact?.agents], ["Permissions cancelled", impact?.active_tokens], ["Requests denied", impact?.pending_approvals],
                ["Devices signed out", impact?.other_sessions], ["Extensions", impact?.extensions]].map(([k, v]) => (
                <div key={k} className="bg-surface p-4"><div className="label">{k}</div><div className="num mt-2 text-[26px] leading-none text-fg">{v ?? "—"}</div></div>
              ))}
            </div>
            <div className="mt-6 label text-fg">What happened?</div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {REASONS.map((r) => (
                <button key={r} type="button" onClick={() => setReason(r)}
                  className={cx("h-8 border px-3 text-[12.5px] transition-colors", reason === r ? "border-ember/70 text-ember" : "border-line-strong text-fg2 hover:text-fg")}>{r}</button>
              ))}
            </div>
            <input className={cx(inputCls, "mt-3")} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Or describe it in a few words" />
            <div className="mt-5 border-t border-line">
              {OPTIONS.map(([k, t]) => (
                <label key={k} className="flex cursor-pointer items-center gap-3 border-b border-line py-3 text-[14px] text-fg2 hover:text-fg">
                  <span className={cx("flex h-4 w-4 shrink-0 items-center justify-center border", opts[k] ? "border-gold bg-gold text-surface" : "border-line-strong")}>{opts[k] && <Check className="h-3 w-3" strokeWidth={2.5} />}</span>
                  <input type="checkbox" className="sr-only" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />{t}
                </label>
              ))}
            </div>
          </Card>
          <div className="space-y-5">
            <Card title="Stop now" meta="No password needed to stop. You’ll need it to recover.">
              <HoldButton busy={busy === "stop"} onFire={activate} />
              <p className="mt-3 text-[12.5px] text-muted">Your browser extension keeps working unless you disconnect it above.</p>
            </Card>
            <PastIncidents items={past} open={history} setOpen={setHistory} />
          </div>
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
          <Card title={<span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-ember live-dot" />Stopped {fmtTime(active?.contained_at)}</span>} meta={active?.reason}>
            <div className="border-t border-line">
              {active?.actions.map((a) => (
                <div key={a.step} className="flex items-center gap-3 border-b border-line py-3 text-[14px]">
                  <Check className="h-4 w-4 shrink-0 text-mint" /><span className="flex-1 text-fg2">{a.detail}</span>{a.count != null && <span className="num font-mono text-fg">{a.count}</span>}
                </div>
              ))}
            </div>
            <div className="mt-6 label text-fg">Blocked since the stop · {s.blocked_since_stop.length}</div>
            {!s.blocked_since_stop.length ? <p className="mt-2 text-[13.5px] text-muted">No agent has tried anything since. If one does, it shows up here.</p> : (
              <ul className="mt-2 divide-y divide-line">
                {s.blocked_since_stop.map((b, i) => (
                  <li key={i} className="flex items-center gap-3 py-2 text-[13px]">
                    <span className="h-1.5 w-1.5 rounded-full bg-ember" /><span className="flex-1 text-fg2">{label(b.event.replaceAll(".", " "))} · {b.actor}</span>
                    <span className="font-mono text-[11px] text-dim">{fmtTime(b.at)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-5 border-l border-sand pl-3 text-[13px] text-fg2">{active?.external_limits}</p>
          </Card>
          <Card title="Recover" meta="Three steps, in order">
            <ol className="space-y-6">
              <li>
                <div className="label text-gold/90">01 · Note what you found</div>
                <div className="mt-2 flex gap-2"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="The agent key was in a shared log file" /><Button loading={busy === "note"} disabled={!note} onClick={addNote}>Add</Button></div>
              </li>
              <li>
                <div className="label text-gold/90">02 · Say what you fixed</div>
                <textarea rows={3} className={cx(inputCls, "mt-2")} value={rec.findings} onChange={(e) => setRec({ ...rec, findings: e.target.value })} placeholder="Key rotated; agent registered again" />
              </li>
              <li>
                <div className="label text-gold/90">03 · Confirm</div>
                <Field label="Type RESTORE"><input className={cx(inputCls, "font-mono uppercase")} value={rec.confirmation} onChange={(e) => setRec({ ...rec, confirmation: e.target.value })} /></Field>
                <Button className="mt-3" variant="primary" icon={LifeBuoy} loading={busy === "recover"} disabled={!rec.findings || rec.confirmation !== "RESTORE"} onClick={recover}>Recover · asks for your password</Button>
              </li>
            </ol>
            <p className="mt-5 text-[12.5px] text-muted">Cancelled permissions and disabled keys stay that way. Agents ask again after recovery; the extension reconnects when you open Kavach.</p>
          </Card>
        </div>
      )}
    </div>
  );
}

function PastIncidents({ items, open, setOpen }) {
  return (
    <Card title="Past stops" meta={items.length ? `${items.length} on record` : "None yet"} pad={false}
      action={items.length ? <button onClick={() => setOpen(!open)} className="label flex items-center gap-1 text-fg2 hover:text-gold">{open ? "Hide" : "Show"}<ChevronDown className={cx("h-3.5 w-3.5", open && "rotate-180")} /></button> : null}>
      {!items.length ? <div className="p-6"><Empty icon={ShieldCheck} title="No stops yet">Try a drill: hold the button, then recover.</Empty></div> : open && (
        <div className="mt-3 border-t border-line">
          {items.map((i) => (
            <div key={i.id} className="border-b border-line px-6 py-5 last:border-0">
              <div className="flex items-center gap-3"><Chip tone={STATE_TONE[i.state]}>{i.state}</Chip><span className="text-[14.5px]">{i.reason}</span></div>
              <ol className="relative ml-1 mt-4 space-y-3 border-l border-line-strong pl-5">
                {i.timeline.map((t, k) => (
                  <li key={k} className="relative">
                    <span className={cx("absolute -left-[25px] top-1.5 h-2 w-2 border", NODE[t.state] || "border-fg2")} />
                    <div className="font-mono text-[11px] uppercase text-dim">{label(t.state)} · {fmtTime(t.at)}</div>
                    <div className="text-[13px] text-fg2">{t.note}</div>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
