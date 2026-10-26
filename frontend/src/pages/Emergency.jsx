import { CheckCircle2, LifeBuoy, OctagonX, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useAuth, useLoad } from "../state";
import { Badge, Button, Card, Empty, ErrorNote, Field, PageHeader, cx, fmtTime, inputCls, label } from "../ui";

const STATE_TONE = { SUSPECTED: "amber", CONTAINED: "red", INVESTIGATING: "amber", RECOVERING: "blue", RESOLVED: "green" };

export default function Emergency() {
  const { setFrozen } = useAuth();
  const status = useLoad(() => get("/emergency-stop/status"));
  const incidents = useLoad(() => get("/incidents"));
  const [opts, setOpts] = useState({ reason: "", revoke_tokens: true, revoke_agents: false, revoke_other_sessions: true, pause_monitoring: true });
  const [rec, setRec] = useState({ findings: "", confirmation: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const active = status.data?.active_incident;

  const refresh = async () => {
    await Promise.all([status.reload(), incidents.reload()]);
    const s = await get("/emergency-stop/status");
    setFrozen(s.frozen);
  };
  const run = (key, fn) => async () => {
    setBusy(key);
    setError(null);
    try { await fn(); await refresh(); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const activate = run("stop", () => post("/emergency-stop/activate", opts));
  const recover = run("recover", () => post("/emergency-stop/recover", { incident_id: active.id, ...rec }));
  const addNote = run("note", async () => { await post(`/incidents/${active.id}/notes`, { note }); setNote(""); });

  return (
    <>
      <PageHeader title="Emergency Center" subtitle="If an agent or credential may be compromised: contain first, investigate, then recover deliberately. Containment never deletes evidence." />
      <ErrorNote error={error} />
      <div className="grid gap-6 xl:grid-cols-2">
        {!status.data?.frozen ? (
          <Card title="Emergency Stop" subtitle="Freezes every protected agent action immediately. No password needed to stop; you'll need one to recover.">
            <div className="space-y-3">
              <Field label="What happened?"><input className={inputCls} value={opts.reason} onChange={(e) => setOpts({ ...opts, reason: e.target.value })} placeholder="My agent tried to send contacts to an unknown site" /></Field>
              {[["revoke_tokens", "Revoke every active consent token"], ["revoke_other_sessions", "Sign out all other devices"], ["revoke_agents", "Disable all agent API keys (rotate after recovery)"], ["pause_monitoring", "Pause scheduled Watchman checks"]].map(([k, t]) => (
                <label key={k} className="flex items-center gap-2 text-[13px] text-slate-700"><input type="checkbox" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} className="h-4 w-4 accent-red-600" />{t}</label>
              ))}
              <button disabled={opts.reason.length < 3 || busy === "stop"} onClick={activate}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 py-4 text-[16px] font-semibold text-white shadow-lg shadow-red-200 transition hover:bg-red-700 disabled:opacity-50">
                <OctagonX className="h-5 w-5" />{busy === "stop" ? "Stopping…" : "Activate Emergency Stop"}
              </button>
            </div>
          </Card>
        ) : (
          <Card title="Emergency Stop is active" subtitle={`Incident ${active?.id.slice(0, 8)} · ${active?.reason}`}>
            <div className="space-y-2">
              {active?.actions.map((a) => (
                <div key={a.step} className="flex items-start gap-2 text-[13px]"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" /><div><b className="text-slate-800">{a.detail}</b>{a.count != null && <span className="text-slate-500"> ({a.count})</span>}</div></div>
              ))}
              <p className="mt-3 rounded-lg bg-amber-50 p-3 text-[12.5px] text-amber-900">{active?.external_limits}</p>
            </div>
            <div className="mt-5 space-y-3 border-t border-slate-100 pt-4">
              <h4 className="text-[13px] font-semibold text-slate-800">Investigation notes</h4>
              <div className="flex gap-2"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Found the agent key in a shared log file" /><Button loading={busy === "note"} disabled={!note} onClick={addNote}>Add</Button></div>
              <h4 className="pt-2 text-[13px] font-semibold text-slate-800">Recover</h4>
              <Field label="Findings and fixes"><textarea rows={3} className={inputCls} value={rec.findings} onChange={(e) => setRec({ ...rec, findings: e.target.value })} placeholder="Key rotated; agent re-registered; no further flows observed" /></Field>
              <Field label="Type RESTORE to confirm"><input className={inputCls} value={rec.confirmation} onChange={(e) => setRec({ ...rec, confirmation: e.target.value })} /></Field>
              <Button variant="success" icon={LifeBuoy} loading={busy === "recover"} disabled={!rec.findings || rec.confirmation !== "RESTORE"} onClick={recover}>Recover (asks for your password)</Button>
              <p className="text-[12px] text-slate-500">Revoked tokens and keys stay revoked. Agents need new authorizations after recovery.</p>
            </div>
          </Card>
        )}
        <Card title="Incident history" pad={false}>
          {!incidents.data?.length ? <div className="p-5"><Empty icon={ShieldCheck} title="No incidents">Run a drill: activate the stop, then recover.</Empty></div> : (
            <div className="divide-y divide-slate-100">
              {incidents.data.map((i) => (
                <div key={i.id} className="px-5 py-3.5">
                  <div className="flex items-center gap-2 text-[13px]"><Badge tone={STATE_TONE[i.state]}>{i.state}</Badge><span className="font-medium text-slate-800">{i.reason}</span></div>
                  <ol className="mt-2 space-y-1 border-l border-slate-200 pl-3">
                    {i.timeline.map((t, k) => <li key={k} className="text-[12px] text-slate-600"><span className={cx("font-medium", STATE_TONE[t.state] === "red" ? "text-red-700" : "text-slate-700")}>{label(t.state)}</span> · {fmtTime(t.at)} · {t.note}</li>)}
                  </ol>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
