import { ClipboardList } from "lucide-react";
import { Fragment, useState } from "react";
import { get } from "../api";
import { useLoad } from "../state";
import { Badge, Card, Decision, Empty, ErrorNote, Json, PageHeader, Spinner, cx, fmtTime, inputCls, label } from "../ui";

export default function Audit() {
  const [type, setType] = useState("");
  const events = useLoad(() => get(`/audit/events?limit=200${type ? `&event_type=${encodeURIComponent(type)}` : ""}`), [type]);
  const [open, setOpen] = useState(null);
  const types = ["", "token.issued", "token.revoked", "gateway.executed", "gateway.blocked", "guardian.authorize.denied", "guardian.approval.requested",
    "consent.rule.created", "consent.review.required", "policy.analyzed", "policy.snapshot.created", "incident.contained", "incident.resolved", "auth.login", "auth.step_up"];
  return (
    <>
      <PageHeader title="Audit Log" subtitle="Append-only and hash-chained: each event includes the hash of the one before, so edits or deletions are detectable. Secrets and payloads are never written.">
        <select className={cx(inputCls, "w-64")} value={type} onChange={(e) => setType(e.target.value)}>{types.map((t) => <option key={t} value={t}>{t || "All events"}</option>)}</select>
      </PageHeader>
      <ErrorNote error={events.error} />
      <Card pad={false}>
        {events.loading ? <div className="p-5"><Spinner /></div> : !events.data?.length ? <div className="p-5"><Empty icon={ClipboardList} title="No events" /></div> : (
          <table className="w-full text-[12.5px]">
            <thead><tr className="border-b border-slate-100 text-left text-slate-500"><th className="px-5 py-2.5 font-medium">#</th><th className="font-medium">When</th><th className="font-medium">Event</th><th className="font-medium">Actor</th><th className="font-medium">Decision</th><th className="pr-5 font-medium">Summary</th></tr></thead>
            <tbody>{events.data.map((e) => {
              const d = e.details || {};
              const summary = d.reason || (d.reasons || []).join("; ") || (d.destination ? `${label(d.action)} → ${d.destination}` : "") || d.classification || d.label || "";
              return (
                <Fragment key={e.id}>
                  <tr key={e.id} onClick={() => setOpen(open === e.id ? null : e.id)} className="cursor-pointer border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-5 py-2.5 tabular-nums text-slate-400">{e.seq}</td>
                    <td className="whitespace-nowrap text-slate-500">{fmtTime(e.created_at)}</td>
                    <td className="font-medium text-slate-800">{e.event_type}</td>
                    <td><Badge tone={e.actor_type === "agent" ? "purple" : e.actor_type === "system" ? "gray" : "blue"}>{e.actor_type}</Badge></td>
                    <td>{e.decision ? <Decision value={e.decision} /> : <span className="text-slate-300">—</span>}</td>
                    <td className="max-w-md truncate pr-5 text-slate-600">{d.code && <b className="mr-1">{d.code}</b>}{summary}</td>
                  </tr>
                  {open === e.id && <tr key={`${e.id}-d`}><td colSpan={6} className="bg-slate-50 px-5 py-3"><div className="mb-1 text-[11.5px] text-slate-500">correlation {e.correlation_id}</div><Json value={d} /></td></tr>}
                </Fragment>
              );
            })}</tbody>
          </table>
        )}
      </Card>
    </>
  );
}
