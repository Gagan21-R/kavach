import { ClipboardList } from "lucide-react";
import { Fragment, useState } from "react";
import { get } from "../api";
import { useLoad } from "../state";
import { Card, Empty, ErrorNote, Json, PageHeader, Spinner, cx, fmtTime, inputCls, label } from "../ui";

const TYPES = ["", "token.issued", "token.revoked", "gateway.executed", "gateway.blocked", "guardian.authorize.denied", "guardian.approval.requested",
  "consent.rule.created", "consent.review.required", "policy.analyzed", "policy.snapshot.created", "incident.contained", "incident.resolved", "auth.login", "auth.step_up"];

export default function Audit() {
  const [type, setType] = useState("");
  const events = useLoad(() => get(`/audit/events?limit=200${type ? `&event_type=${encodeURIComponent(type)}` : ""}`), [type]);
  const [open, setOpen] = useState(null);
  return (
    <>
      <PageHeader eyebrow="Audit log · append-only" title="Every decision, on the record"
        subtitle="Hash-chained: each event carries the hash of the one before, so edits or deletions are detectable. Secrets and payloads are never written.">
        <select className={cx(inputCls, "w-64 font-mono text-[12px] uppercase")} value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map((t) => <option key={t} value={t}>{t || "All events"}</option>)}</select>
      </PageHeader>
      <ErrorNote error={events.error} />
      <Card pad={false}>
        {events.loading ? <div className="px-6"><Spinner /></div> : !events.data?.length ? <div className="p-6"><Empty icon={ClipboardList} title="No events" /></div> : (
          <div className="overflow-x-auto scroll-thin">
            <table className="w-full font-mono text-[12px]">
              <thead><tr className="border-b border-line text-left">{["#", "When", "Event", "Actor", "Decision", "Summary"].map((h) => <th key={h} className="label px-5 py-3.5 font-normal text-muted">{h}</th>)}</tr></thead>
              <tbody>{events.data.map((e) => {
                const d = e.details || {};
                const summary = d.reason || (d.reasons || []).join("; ") || (d.destination ? `${label(d.action)} → ${d.destination}` : "") || d.classification || d.label || "";
                return (
                  <Fragment key={e.id}>
                    <tr onClick={() => setOpen(open === e.id ? null : e.id)} className="cursor-pointer border-b border-line hover:bg-raised/40">
                      <td className="px-5 py-3 text-dim">{e.seq}</td>
                      <td className="whitespace-nowrap px-5 text-muted">{fmtTime(e.created_at)}</td>
                      <td className="px-5 uppercase text-fg">{e.event_type}</td>
                      <td className={cx("px-5 uppercase", e.actor_type === "agent" ? "text-sand" : e.actor_type === "system" ? "text-dim" : "text-fg2")}>{e.actor_type}</td>
                      <td className={cx("px-5 uppercase", e.decision === "BLOCK" ? "text-ember" : e.decision === "ALLOW" ? "text-mint" : e.decision ? "text-sand" : "text-dim")}>{e.decision || "—"}</td>
                      <td className="max-w-md truncate px-5 font-sans text-[12.5px] text-fg2">{d.code && <span className="mr-1 font-mono text-fg">{d.code}</span>}{summary}</td>
                    </tr>
                    {open === e.id && <tr><td colSpan={6} className="bg-raised/40 px-5 py-4"><div className="label mb-2 text-dim">correlation · {e.correlation_id}</div><Json value={d} /></td></tr>}
                  </Fragment>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
