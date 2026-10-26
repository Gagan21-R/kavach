import { FlaskConical, Play } from "lucide-react";
import { Fragment, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Stat, cx, fmtTime, inputCls } from "../ui";

const ST = { PASS: "green", FAIL: "red", ABSTAIN: "amber" };
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function RedTeam() {
  const runs = useLoad(() => get("/red-team/runs"));
  const [run, setRun] = useState(null);
  const [seed, setSeed] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [open, setOpen] = useState(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setRun(await post("/red-team/runs", { seed: Number(seed) }));
      runs.reload();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const s = run?.summary;
  const rows = (run?.results || []).filter((r) => filter === "ALL" || r.status === filter);

  return (
    <>
      <PageHeader title="Red Team Lab" subtitle="Replays synthetic policies and attacks against a fresh, isolated copy of the whole system. Every scenario has a known expected result; failures are shown, not hidden.">
        <input type="number" className={cx(inputCls, "w-24")} value={seed} onChange={(e) => setSeed(e.target.value)} aria-label="Seed" />
        <Button variant="primary" icon={Play} loading={busy} onClick={start}>Run lab</Button>
      </PageHeader>
      <ErrorNote error={error} />
      {!run ? (
        <Card>
          <Empty icon={FlaskConical} title="Run the lab to see results">
            36 scenarios: benign and abusive policies, hidden and visible prompt injections, formatting vs material changes, expired, revoked, wrong-scope, stale and replayed tokens, data laundering, auditor tampering, cross-user access, Emergency Stop, database outage and timeouts.
          </Empty>
          {runs.data?.length > 0 && (
            <div className="mt-4 space-y-1.5">
              <div className="text-[12.5px] font-medium text-slate-700">Previous runs</div>
              {runs.data.map((r) => (
                <button key={r.id} onClick={async () => setRun(await get(`/red-team/runs/${r.id}`))} className="flex w-full justify-between rounded-lg px-2 py-1.5 text-[13px] hover:bg-slate-50">
                  <span>seed {r.seed} · {fmtTime(r.created_at)}</span><span>{r.summary.passed}/{r.summary.total} passed</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6">
            <Stat label="Passed" value={`${s.passed}/${s.total}`} tone="green" hint={`${s.failed} failed · ${s.abstained} abstained`} />
            <Stat label="False approvals" value={s.false_approvals} tone={s.false_approvals ? "red" : "green"} hint="unsafe ALLOWs" />
            <Stat label="False blocks" value={s.false_blocks} tone={s.false_blocks ? "amber" : "green"} hint="safe actions refused" />
            <Stat label="Attack success" value={pct(s.attack_success_rate)} tone={s.attack_success_rate ? "red" : "green"} hint="lower is better" />
            <Stat label="Injection P / R" value={`${pct(s.injection_detection.precision)} / ${pct(s.injection_detection.recall)}`} hint={`tp ${s.injection_detection.tp} fn ${s.injection_detection.fn} fp ${s.injection_detection.fp}`} />
            <Stat label="Change detection P / R" value={`${pct(s.semantic_change_detection.precision)} / ${pct(s.semantic_change_detection.recall)}`} hint={`citations ${pct(s.citation_support_rate)} verified`} />
          </div>
          <div className="mt-3 text-[12px] text-slate-500">Seed {run.seed} · {s.total_seconds}s total · p50 {s.latency_ms.p50} ms · cost {s.cost}. {s.dataset_note}</div>
          <Card className="mt-6" pad={false} title="Scenarios"
            action={<div className="flex gap-1">{["ALL", "PASS", "FAIL", "ABSTAIN"].map((f) => <Button key={f} size="sm" variant={filter === f ? "primary" : "ghost"} onClick={() => setFilter(f)}>{f}</Button>)}</div>}>
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-slate-100 text-left text-slate-500"><th className="px-5 py-2.5 font-medium">ID</th><th className="font-medium">Scenario</th><th className="font-medium">Expected</th><th className="font-medium">Actual</th><th className="font-medium">Status</th><th className="pr-5 text-right font-medium">ms</th></tr></thead>
              <tbody>{rows.map((r) => (
                <Fragment key={r.id}>
                  <tr key={r.id} onClick={() => setOpen(open === r.id ? null : r.id)} className={cx("cursor-pointer border-b border-slate-50 align-top hover:bg-slate-50", r.status === "FAIL" && "bg-red-50/40")}>
                    <td className="px-5 py-2.5 font-mono text-[11.5px] text-slate-500">{r.id}</td>
                    <td className="py-2.5"><div className="font-medium text-slate-800">{r.category}</div><div className="text-slate-500">{r.description}</div></td>
                    <td className="py-2.5 text-slate-600">{r.expected}</td>
                    <td className="max-w-xs py-2.5 text-slate-700">{r.actual}</td>
                    <td className="py-2.5"><Badge tone={ST[r.status]}>{r.status}</Badge></td>
                    <td className="pr-5 text-right tabular-nums text-slate-400">{r.duration_ms}</td>
                  </tr>
                  {open === r.id && (
                    <tr key={`${r.id}-x`} className="border-b border-slate-100 bg-slate-50"><td colSpan={6} className="px-5 py-3 text-[12px] text-slate-600">
                      {r.explanation && <div className="mb-1 text-red-700"><b>Why it failed:</b> {r.explanation}</div>}
                      <b className="text-slate-700">Evidence:</b> {r.evidence || "—"}
                    </td></tr>
                  )}
                </Fragment>
              ))}</tbody>
            </table>
          </Card>
        </>
      )}
    </>
  );
}
