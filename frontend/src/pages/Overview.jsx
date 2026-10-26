import { Activity, AlertTriangle, Ban, CheckCircle2, Eye, FileText, FlaskConical, Gavel, KeyRound, ShieldAlert, Sparkles, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api";
import { useAgent, useLoad } from "../state";
import { Badge, Button, Card, Decision, Empty, ErrorNote, PageHeader, Spinner, Stat, fmtTime, label } from "../ui";

function FlowChart({ days }) {
  const max = Math.max(1, ...days.map((d) => d.completed + d.blocked));
  return (
    <div>
      <div className="flex h-40 gap-3">
        {days.map((d) => (
          <div key={d.date} className="flex flex-1 flex-col items-center gap-1">
            <div className="flex w-full max-w-10 flex-1 flex-col justify-end gap-[2px]">
              {d.blocked > 0 && <div title={`${d.blocked} blocked`} className="rounded-t bg-red-400" style={{ height: `${(d.blocked / max) * 100}%` }} />}
              {d.completed > 0 && <div title={`${d.completed} completed`} className={`${d.blocked ? "" : "rounded-t"} bg-emerald-500`} style={{ height: `${(d.completed / max) * 100}%` }} />}
            </div>
            <div className="text-[11px] text-slate-400">{new Date(d.date + "T00:00").toLocaleDateString(undefined, { weekday: "short" })}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-[12px] text-slate-500">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" />Completed (simulated)</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-red-400" />Blocked before execution</span>
      </div>
    </div>
  );
}

function ScoreBar({ score }) {
  if (score == null) return <span className="text-slate-400">—</span>;
  const color = score >= 50 ? "bg-red-500" : score >= 25 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-slate-100"><div className={`h-1.5 rounded-full ${color}`} style={{ width: `${score}%` }} /></div>
      <span className="w-7 text-right text-[12px] tabular-nums text-slate-600">{score}</span>
    </div>
  );
}

export default function Overview() {
  const { data, loading, error, reload } = useLoad(() => get("/dashboard/summary"));
  const { setAgent } = useAgent();
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState(null);

  const seed = async () => {
    setSeeding(true);
    setSeedError(null);
    try {
      const r = await post("/demo/seed");
      setAgent({ id: r.agent_id, name: "demo-browser-agent", key: r.agent_key });
      await reload();
    } catch (e) {
      setSeedError(e);
    } finally {
      setSeeding(false);
    }
  };

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorNote error={error} />;
  const c = data.counts;
  const rt = data.red_team;

  return (
    <>
      <PageHeader title="Overview" subtitle="Everything Kavach is guarding for you: policies on trial, agent authority, blocked flows and system health.">
        {c.policies === 0 && <Button variant="primary" icon={Sparkles} loading={seeding} onClick={seed}>Load demo data</Button>}
      </PageHeader>
      <ErrorNote error={seedError} />

      {c.policies === 0 && (
        <Card className="mb-6">
          <Empty icon={Sparkles} title="Start with the demo">
            Loads sample rules (maps may use your location for directions, never for ads), two fictional policies (MapsCo and FlashLight), a demo agent and a data lineage chain.
          </Empty>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Policies on watch" value={c.policies} hint={c.needs_reassessment ? `${c.needs_reassessment} need your review` : "all assessed"} icon={FileText} tone={c.needs_reassessment ? "amber" : undefined} />
        <Stat label="Active agent tokens" value={c.active_tokens} hint={`${c.agents} agent(s) connected`} icon={KeyRound} />
        <Stat label="Blocked in 24h" value={c.blocked_24h} hint="stopped before execution" icon={Ban} tone={c.blocked_24h ? "red" : undefined} />
        <Stat label="Pending approvals" value={c.pending_approvals} hint={`${c.active_rules} active rules`} icon={Users} tone={c.pending_approvals ? "amber" : undefined} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Agent flows, last 7 days" subtitle="Every protected action an agent attempted through the gateway." className="lg:col-span-2">
          <FlowChart days={data.flows_by_day} />
        </Card>
        <Card title="System health">
          <div className="space-y-3 text-[13px]">
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Emergency Stop</span>
              {data.frozen ? <Badge tone="red"><AlertTriangle className="h-3 w-3" />ACTIVE</Badge> : <Badge tone="green"><CheckCircle2 className="h-3 w-3" />Normal</Badge>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Watchman</span>
              {data.policies.some((p) => p.watch_status === "UNKNOWN") ? <Badge tone="amber">Some checks UNKNOWN</Badge> : <Badge tone="green">All checks OK</Badge>}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Red Team Lab</span>
              {rt ? <Badge tone={rt.failed ? "amber" : "green"}>{rt.passed}/{rt.total} passed</Badge> : <Badge>Not run</Badge>}
            </div>
            {rt && (
              <div className="rounded-lg bg-slate-50 p-3 text-[12px] text-slate-600">
                False approvals <b className="text-slate-900">{rt.false_approvals}</b> · attack success <b className="text-slate-900">{Math.round((rt.attack_success_rate || 0) * 100)}%</b> · injection recall <b className="text-slate-900">{rt.injection_detection?.recall ?? "—"}</b>
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 pt-1">
              <Link to="/courtroom"><Button size="sm" icon={Gavel} className="w-full">Trial</Button></Link>
              <Link to="/trap"><Button size="sm" icon={ShieldAlert} className="w-full">Trap</Button></Link>
              <Link to="/watchman"><Button size="sm" icon={Eye} className="w-full">Watch</Button></Link>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Policies on trial" subtitle="Latest verdict for each policy you track." className="lg:col-span-2" pad={false}>
          {data.policies.length === 0 ? <div className="p-5"><Empty icon={Gavel} title="No policies yet">Put a policy on trial in the Courtroom.</Empty></div> : (
            <table className="w-full text-[13px]">
              <thead><tr className="border-b border-slate-100 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2.5 font-medium">Policy</th><th className="py-2.5 font-medium">Verdict</th><th className="py-2.5 font-medium">Risk</th><th className="py-2.5 font-medium">Auditor</th><th className="px-5 py-2.5 font-medium">Status</th>
              </tr></thead>
              <tbody>
                {data.policies.map((p) => (
                  <tr key={p.id} className="border-b border-slate-50 last:border-0">
                    <td className="px-5 py-3"><div className="font-medium text-slate-900">{p.name} <span className="font-normal text-slate-400">v{p.version}</span></div><div className="max-w-xs truncate text-[12px] text-slate-500">{p.headline}</div></td>
                    <td><Decision value={p.recommendation} /></td>
                    <td><ScoreBar score={p.risk_score} /></td>
                    <td><Decision value={p.audit_verdict} /></td>
                    <td className="px-5">{p.requires_reassessment ? <Badge tone="amber">Needs review</Badge> : p.watch_status === "UNKNOWN" ? <Badge tone="amber">UNKNOWN</Badge> : <Badge tone="green">Current</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Recent activity" action={<Link to="/audit" className="text-[12px] text-indigo-600 hover:underline">Audit log</Link>}>
          {data.recent.length === 0 ? <Empty icon={Activity} title="Nothing yet" /> : (
            <ol className="space-y-2.5">
              {data.recent.map((e) => (
                <li key={e.seq} className="flex items-start gap-2.5 text-[12.5px]">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${e.decision === "BLOCK" ? "bg-red-500" : e.decision === "ALLOW" ? "bg-emerald-500" : e.decision === "REVIEW" ? "bg-amber-500" : "bg-slate-300"}`} />
                  <div className="min-w-0">
                    <div className="truncate text-slate-800">{label(e.event_type)}{e.details?.destination ? ` · ${e.details.destination}` : ""}</div>
                    <div className="text-[11.5px] text-slate-400">{e.actor_type} · {fmtTime(e.created_at)}</div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
      {rt == null && c.policies > 0 && (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-3 text-[13px] text-indigo-800">
          <FlaskConical className="h-4 w-4" /> Run the Red Team Lab to measure how the system holds up against synthetic attacks.
          <Link to="/red-team" className="ml-auto font-medium underline">Open lab</Link>
        </div>
      )}
    </>
  );
}
