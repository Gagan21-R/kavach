import { Copy, Eye, FileClock, Mail, RefreshCw, ShieldCheck, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import {
  Badge, Button, CLASS_TONE, Card, Decision, Empty, ErrorNote, Field, Modal, PageHeader, Spinner, cx, fmtTime, inputCls, label,
} from "../ui";

function Diff({ diff }) {
  return (
    <p className="text-[13px] leading-6">
      {diff.map((d, i) => (
        <span key={i} className={d.op === "insert" ? "rounded bg-emerald-100 px-0.5 text-emerald-900" : d.op === "delete" ? "rounded bg-red-100 px-0.5 text-red-800 line-through" : "text-slate-600"}>
          {d.text}{" "}
        </span>
      ))}
    </p>
  );
}

function DraftModal({ policyId, event, type, onClose }) {
  const [draft, setDraft] = useState(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    post("/provider-requests/draft", { policy_source_id: policyId, request_type: type, watch_event_id: event?.id })
      .then((d) => { setDraft(d); setBody(d.body); }).catch(setError);
  }, [policyId, event, type]);
  return (
    <Modal title="Editable request draft" onClose={onClose} wide>
      <ErrorNote error={error} />
      {!draft ? <Spinner /> : (
        <div className="space-y-3">
          <div className="text-[12.5px] text-slate-500">To: {draft.to_hint}</div>
          <div className="text-[13px] font-medium text-slate-900">Subject: {draft.subject}</div>
          <textarea rows={14} className={cx(inputCls, "font-mono text-[12.5px]")} value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="rounded-lg bg-amber-50 p-3 text-[12px] text-amber-900">{draft.disclaimer}</div>
          <div className="flex justify-end gap-2">
            <Button icon={Copy} onClick={async () => { await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${body}`); setCopied(true); }}>{copied ? "Copied" : "Copy to clipboard"}</Button>
            <Button variant="primary" onClick={onClose}>Done</Button>
          </div>
          <p className="text-right text-[11.5px] text-slate-400">Kavach never sends this for you.</p>
        </div>
      )}
    </Modal>
  );
}

function EventDetail({ ev, policyId, rules }) {
  const [draftType, setDraftType] = useState(null);
  const material = ["POTENTIALLY_MATERIAL", "AMBIGUOUS"].includes(ev.classification);
  if (ev.status === "UNKNOWN") {
    return <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-900"><b>UNKNOWN.</b> {ev.error}. We could not retrieve the policy, so we can't say it is unchanged.</div>;
  }
  if (ev.status === "NO_CHANGE") return <div className="text-[13px] text-slate-600">Checked: no change.</div>;
  const ruleMap = Object.fromEntries((rules || []).map((r) => [r.id, r]));
  return (
    <div className="space-y-4">
      {material && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="font-serif text-[18px] font-semibold text-red-900">Your earlier approval was assessed against the old wording. This change isn't covered.</div>
          <p className="mt-1 text-[13px] text-red-800">{ev.affected_token_ids.length} agent token(s) for this policy are paused and {ev.affected_rule_ids.length} of your rules are affected. Re-approval is needed under your rules before agents can act again. This is not a legal finding about your consent.</p>
        </div>
      )}
      {ev.changes.map((c, i) => (
        <div key={i} className="rounded-lg border border-slate-200 p-3.5">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <Badge tone={CLASS_TONE[c.classification]}>{label(c.classification)}</Badge>
            {c.categories.map((x) => <Badge key={x} tone="purple">{label(x)}</Badge>)}
            <span className="text-[12px] text-slate-500">{c.old_clause_id ? `old ${c.old_clause_id}` : "new clause"}{c.new_clause_id ? ` → ${c.new_clause_id}` : " → removed"}</span>
          </div>
          {c.diff?.length ? <Diff diff={c.diff} /> : <p className="text-[13px] text-slate-500">{c.explanation}</p>}
          {c.diff?.length > 0 && <p className="mt-1.5 text-[12px] text-slate-500"><b className="text-slate-700">Interpretation:</b> {c.explanation}</p>}
        </div>
      ))}
      {ev.confidence && <div className="text-[12px] text-slate-500"><b className="text-slate-700">Confidence:</b> {Math.round(ev.confidence.value * 100)}% ({ev.confidence.basis}) · {ev.confidence.explanation}</div>}
      {ev.affected_rule_ids.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[13px] font-semibold text-slate-800">Affected rules</h4>
          <div className="flex flex-wrap gap-1.5">{ev.affected_rule_ids.map((id) => {
            const r = ruleMap[id];
            return <Badge key={id} tone={r?.effect === "DENY" ? "red" : r?.effect === "ALLOW" ? "green" : "amber"}>{r ? `${r.effect}: ${r.data_categories.join(", ")}${r.purposes.length ? ` for ${r.purposes.join(", ")}` : ""}` : id}</Badge>;
          })}</div>
        </div>
      )}
      <div>
        <h4 className="mb-1.5 text-[13px] font-semibold text-slate-800">Recommended next steps</h4>
        <div className="space-y-2">
          {ev.recommendations.map((r) => (
            <div key={r.id} className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 p-3">
              <div><div className="text-[13px] font-medium text-slate-800">{r.title}</div><div className="text-[12px] text-slate-500">{r.detail}</div></div>
              {["withdraw_consent", "access", "deletion"].includes(r.id) && <Button size="sm" icon={Mail} onClick={() => setDraftType(r.id)}>Draft email</Button>}
            </div>
          ))}
        </div>
      </div>
      {draftType && <DraftModal policyId={policyId} event={ev} type={draftType} onClose={() => setDraftType(null)} />}
    </div>
  );
}

export default function Watchman() {
  const policies = useLoad(() => get("/policies"));
  const fx = useLoad(() => get("/demo/fixtures"));
  const rules = useLoad(() => get("/consent/rules"));
  const [sel, setSel] = useState(null);
  const [events, setEvents] = useState([]);
  const [snaps, setSnaps] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [current, setCurrent] = useState(null);

  const policy = policies.data?.find((p) => p.id === sel);
  useEffect(() => { if (!sel && policies.data?.length) setSel(policies.data[0].id); }, [policies.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadPolicy = async (id) => {
    const [ev, sn] = await Promise.all([get(`/policies/${id}/watch-events`), get(`/policies/${id}/snapshots`)]);
    setEvents(ev);
    setSnaps(sn);
    setCurrent(ev[0] || null);
    const latest = sn[sn.length - 1];
    if (latest) setText((await get(`/policies/${id}/snapshots/${latest.id}`)).text);
  };
  useEffect(() => { if (sel) loadPolicy(sel).catch(setError); }, [sel]);

  const publish = async () => {
    setBusy("publish");
    setError(null);
    try {
      const r = await post(`/policies/${sel}/snapshots`, { text });
      await policies.reload();
      await loadPolicy(sel);
      if (r.watch_event) setCurrent(r.watch_event);
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const act = async (path, key) => {
    setBusy(key);
    setError(null);
    try {
      await post(path);
      await policies.reload();
      await loadPolicy(sel);
    } catch (e) { setError(e); } finally { setBusy(null); }
  };

  const isMaps = policy?.domain === "maps.example.com";
  return (
    <>
      <PageHeader title="Watchman" subtitle="Policies change after you agree. Watchman keeps every version, ignores formatting noise, and pauses your authorizations when the meaning changes." />
      <ErrorNote error={error} />
      {policies.loading ? <Spinner /> : !policies.data?.length ? <Card><Empty icon={Eye} title="No policies on watch">Put a policy on trial or load the demo data from the Overview.</Empty></Card> : (
        <div className="grid gap-6 xl:grid-cols-5">
          <div className="space-y-6 xl:col-span-2">
            <Card title="Policies" pad={false}>
              {policies.data.map((p) => (
                <button key={p.id} onClick={() => setSel(p.id)} className={cx("flex w-full items-center justify-between border-b border-slate-50 px-5 py-3 text-left last:border-0", sel === p.id ? "bg-indigo-50/60" : "hover:bg-slate-50")}>
                  <div><div className="text-[13px] font-medium text-slate-900">{p.name} <span className="font-normal text-slate-400">v{p.current_version}</span></div><div className="text-[12px] text-slate-500">{p.domain}</div></div>
                  {p.requires_reassessment ? <Badge tone="red">Needs review</Badge> : p.watch_status === "UNKNOWN" ? <Badge tone="amber">UNKNOWN</Badge> : <Badge tone="green">Current</Badge>}
                </button>
              ))}
            </Card>
            {policy && (
              <Card title="Publish a new version" subtitle="Simulates the company editing its policy. In production Watchman fetches the URL on a schedule.">
                {isMaps && fx.data && (
                  <div className="mb-3 flex flex-wrap gap-2">
                    <Button size="sm" icon={Wand2} onClick={() => setText(fx.data.betrayal_text)}>The Betrayal: add AI partners</Button>
                    <Button size="sm" onClick={() => setText(fx.data.reformatted_text)}>Reformat only</Button>
                    <Button size="sm" onClick={() => setText(fx.data.policies[1].text.replace("send receipts and security alerts", "send you receipts and account security alerts"))}>Rephrase</Button>
                  </div>
                )}
                <textarea rows={9} className={cx(inputCls, "font-mono text-[12px]")} value={text} onChange={(e) => setText(e.target.value)} />
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="primary" icon={FileClock} loading={busy === "publish"} onClick={publish}>Publish and compare</Button>
                  <Button icon={RefreshCw} loading={busy === "check"} onClick={() => act(`/policies/${sel}/check`, "check")}>Check URL now</Button>
                  {policy.requires_reassessment && <Button variant="success" icon={ShieldCheck} loading={busy === "re"} onClick={() => act(`/policies/${sel}/reassess`, "re")}>I've reviewed it</Button>}
                </div>
              </Card>
            )}
          </div>
          <div className="space-y-6 xl:col-span-3">
            <Card title="Latest change" subtitle={current ? `${current.status}${current.from_version ? ` · v${current.from_version}${current.to_version ? ` → v${current.to_version}` : ""}` : ""} · ${fmtTime(current.created_at)}` : "No changes recorded yet"}>
              {current ? <EventDetail ev={current} policyId={sel} rules={rules.data} /> : <Empty icon={FileClock} title="No changes yet">Publish a new version to see Watchman classify it.</Empty>}
            </Card>
            <Card title="Version timeline">
              <ol className="relative space-y-3 border-l border-slate-200 pl-5">
                {[...snaps].reverse().map((s) => {
                  const ev = events.find((e) => e.to_version === s.version);
                  return (
                    <li key={s.id} className="relative">
                      <span className={cx("absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white", s.classification ? { POTENTIALLY_MATERIAL: "bg-red-500", AMBIGUOUS: "bg-amber-500", WORDING_NO_MATERIAL_CHANGE: "bg-indigo-500", FORMATTING_ONLY: "bg-emerald-500" }[s.classification] : "bg-slate-400")} />
                      <div className="flex flex-wrap items-center gap-2 text-[13px]">
                        <b className="text-slate-900">v{s.version}</b>
                        {s.classification ? <Badge tone={CLASS_TONE[s.classification]}>{label(s.classification)}</Badge> : <Badge>first version</Badge>}
                        <span className="text-[12px] text-slate-400">{fmtTime(s.retrieved_at)} · {s.content_hash.slice(0, 10)}</span>
                        {ev && <button className="text-[12px] text-indigo-600 hover:underline" onClick={() => setCurrent(ev)}>details</button>}
                      </div>
                    </li>
                  );
                })}
                {events.filter((e) => e.status === "UNKNOWN").slice(0, 3).map((e) => (
                  <li key={e.id} className="relative"><span className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white bg-amber-400" />
                    <div className="text-[13px]"><Badge tone="amber">UNKNOWN</Badge> <span className="text-[12px] text-slate-500">{fmtTime(e.created_at)} · {e.error}</span></div></li>
                ))}
              </ol>
              {policy?.analysis && <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-3 text-[12.5px] text-slate-600">Current verdict: <Decision value={policy.analysis.recommendation} /> {policy.analysis.headline}</div>}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
