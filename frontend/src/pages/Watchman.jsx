import { ArrowUpRight, Copy, Eye, FileClock, Mail, RefreshCw, ShieldCheck, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import MonitoringInbox from "./Inbox";
import {
  Button, CLASS_TONE, Card, Chip, Collapse, Decision, Empty, ErrorNote, Modal, PageHeader, Spinner, cx, fmtTime, inputCls, label,
} from "../ui";

const NODE = { POTENTIALLY_MATERIAL: "bg-ember border-ember", AMBIGUOUS: "bg-sand border-sand", WORDING_NO_MATERIAL_CHANGE: "bg-fg2 border-fg2", FORMATTING_ONLY: "bg-mint border-mint" };

function Diff({ diff }) {
  return (
    <p className="break-words text-[14px] leading-7">
      {diff.map((d, i) => (
        <span key={i} className={d.op === "insert" ? "bg-mint/15 text-mint" : d.op === "delete" ? "text-ember line-through decoration-ember/70" : "text-fg2"}>{d.text} </span>
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
    <Modal eyebrow={`Draft · ${label(type)} · never sent automatically`} title="Editable request" onClose={onClose} wide>
      <ErrorNote error={error} />
      {!draft ? <Spinner /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-[72px_1fr] gap-y-2 font-mono text-[12px]">
            <span className="uppercase text-dim">To</span><span className="text-fg2">{draft.to_hint}</span>
            <span className="uppercase text-dim">Subject</span><span className="text-fg">{draft.subject}</span>
          </div>
          <textarea rows={14} className={cx(inputCls, "font-mono text-[12.5px] leading-relaxed")} value={body} onChange={(e) => setBody(e.target.value)} />
          <p className="border-l border-sand pl-3 text-[12.5px] text-fg2">{draft.disclaimer}</p>
          <div className="flex justify-end gap-2">
            <Button icon={Copy} onClick={async () => { await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${body}`); setCopied(true); }}>{copied ? "Copied" : "Copy to clipboard"}</Button>
            <Button variant="primary" onClick={onClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function EventDetail({ ev, policyId, rules }) {
  const [draftType, setDraftType] = useState(null);
  const material = ["POTENTIALLY_MATERIAL", "AMBIGUOUS"].includes(ev.classification);
  if (ev.status === "UNKNOWN") return <div className="border-l border-sand pl-4 text-[14px] text-fg2"><span className="label mr-2 text-sand">Unknown</span>{ev.error}. We could not retrieve the policy, so we can't say it is unchanged.</div>;
  if (ev.status === "NO_CHANGE") return <p className="text-[14px] text-muted">No change. {ev.checked_by && <span className="text-fg2">{ev.checked_by}.</span>}</p>;
  const ruleMap = Object.fromEntries((rules || []).map((r) => [r.id, r]));
  return (
    <div className="space-y-6">
      {(ev.source === "EMAIL" || ev.checked_by) && (
        <p className="flex flex-wrap items-center gap-2 text-[13px] text-fg2">
          {ev.source === "EMAIL" && <Chip tone="sand"><Mail className="h-3 w-3" />From email</Chip>}
          {ev.checked_by}
        </p>
      )}
      {material && (
        <div className="rise border-2 border-ember bg-ember/[0.06] p-6">
          <div className="label flex items-center gap-2 text-ember"><span className="h-1.5 w-1.5 rounded-full bg-ember live-dot" />Consent no longer covers this</div>
          <p className="mt-3 text-[24px] leading-snug tracking-[-0.03em]">Your earlier approval was assessed against the old wording. This change isn't covered.</p>
          <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden bg-ember/25 sm:grid-cols-3">
            {[["Tokens paused", ev.affected_token_ids.length], ["Rules affected", ev.affected_rule_ids.length], ["Confidence", ev.confidence ? `${Math.round(ev.confidence.value * 100)}%` : "—"]].map(([k, v]) => (
              <div key={k} className="bg-surface p-4"><div className="label text-fg2">{k}</div><div className="num mt-2 text-[28px] leading-none">{v}</div></div>
            ))}
          </div>
          <p className="mt-4 text-[13px] text-muted">Re-approval is needed under your rules before agents can act again. This is not a legal finding about your consent.</p>
        </div>
      )}
      <div className="space-y-3">
        {ev.changes.map((c, i) => (
          <div key={i} className=" border-2 border-fg p-5">
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              <Chip tone={CLASS_TONE[c.classification]}>{label(c.classification)}</Chip>
              {c.categories.map((x) => <Chip key={x} dot={false}>{label(x)}</Chip>)}
              <span className="ml-auto font-mono text-[11px] uppercase text-dim">{c.old_clause_id || "new"} → {c.new_clause_id || "removed"}</span>
            </div>
            {c.diff?.length ? <Diff diff={c.diff} /> : <p className="text-[14px] text-muted">{c.explanation}</p>}
            {c.diff?.length > 0 && <p className="mt-3 text-[13px] text-muted"><span className="label mr-2 text-fg2">Reading</span>{c.explanation}</p>}
          </div>
        ))}
      </div>
      {ev.affected_rule_ids.length > 0 && (
        <div>
          <div className="label mb-2">[ Affected rules ]</div>
          <div className="flex flex-wrap gap-1.5">{ev.affected_rule_ids.map((id) => {
            const r = ruleMap[id];
            return <Chip key={id} tone={r?.effect === "DENY" ? "ember" : r?.effect === "ALLOW" ? "mint" : "sand"}>{r ? `${r.effect} · ${r.data_categories.join(", ")}${r.purposes.length ? ` · ${r.purposes.join(", ")}` : ""}` : id}</Chip>;
          })}</div>
        </div>
      )}
      <div>
        <div className="label mb-1">[ Next steps ]</div>
        <div className="border-t border-line">
          {ev.recommendations.map((r) => {
            const draftable = ["withdraw_consent", "access", "deletion"].includes(r.id);
            return (
              <div key={r.id} onClick={draftable ? () => setDraftType(r.id) : undefined}
                className={cx("group flex items-center gap-6 border-b border-line py-4", draftable && "cursor-pointer")}>
                <div className="flex-1">
                  <div className={cx("text-[17px] tracking-[-0.02em]", draftable ? "text-fg2 group-hover:text-fg" : "text-fg2")}>{r.title}</div>
                  <div className="mt-0.5 text-[13px] text-muted">{r.detail}</div>
                </div>
                {draftable && <span className="label flex items-center gap-1 text-dim group-hover:text-gold">Draft email <ArrowUpRight className="h-4 w-4" /></span>}
              </div>
            );
          })}
        </div>
      </div>
      {draftType && <DraftModal policyId={policyId} event={ev} type={draftType} onClose={() => setDraftType(null)} />}
    </div>
  );
}

function StatusBar({ onChecked }) {
  const status = useLoad(() => get("/watchman/status"));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [error, setError] = useState(null);
  const s = status.data;
  const hours = s ? Math.round(s.every_minutes / 60) : 6;
  const run = async () => {
    setBusy(true); setError(null); setNote(null);
    try {
      const r = await post("/watchman/check-all");
      setNote(`Checked ${r.checked} polic${r.checked === 1 ? "y" : "ies"}: ${r.changed} changed${r.unknown ? `, ${r.unknown} couldn’t be read` : ""}.`);
      await status.reload(); onChecked?.();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <div data-reveal className="border-2 border-fg bg-surface mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4 text-line-strong">
      <div className="flex items-center gap-2.5">
        <span className={cx("h-2 w-2 rounded-full", s?.automatic ? "bg-mint live-dot" : "bg-sand")} />
        <span className="label text-fg">{s?.automatic ? `Automatic checks every ${hours} h` : "Automatic checks run while the server is up"}</span>
      </div>
      <span className="label">Last check <span className="text-fg2">{s?.last_checked_at ? fmtTime(s.last_checked_at) : "—"}</span></span>
      {s?.next_run_at && <span className="label">Next <span className="text-fg2">{fmtTime(s.next_run_at)}</span></span>}
      <span className="label hidden lg:inline">Method <span className="text-fg2">ETag / Last-Modified, then compare</span></span>
      <div className="ml-auto flex items-center gap-3">
        {note && <span className="text-[13px] text-mint">{note}</span>}
        <Button size="sm" variant="primary" icon={RefreshCw} loading={busy} onClick={run}>Check all now</Button>
      </div>
      {error && <div className="w-full"><ErrorNote error={error} /></div>}
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

  useEffect(() => { if (!sel && policies.data?.length) setSel((policies.data.find((p) => p.requires_reassessment) || policies.data[0]).id); }, [policies.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const loadPolicy = async (id) => {
    const [ev, sn] = await Promise.all([get(`/policies/${id}/watch-events`), get(`/policies/${id}/snapshots`)]);
    setEvents(ev); setSnaps(sn); setCurrent(ev[0] || null);
    const latest = sn[sn.length - 1];
    if (latest) setText((await get(`/policies/${id}/snapshots/${latest.id}`)).text);
  };
  useEffect(() => { if (sel) loadPolicy(sel).catch(setError); }, [sel]);

  const publish = async () => {
    setBusy("publish"); setError(null);
    try {
      const r = await post(`/policies/${sel}/snapshots`, { text });
      await policies.reload(); await loadPolicy(sel);
      if (r.watch_event) setCurrent(r.watch_event);
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const act = async (path, key) => {
    setBusy(key); setError(null);
    try { await post(path); await policies.reload(); await loadPolicy(sel); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const isMaps = policy?.domain === "maps.example.com";

  return (
    <>
      <PageHeader index={3} eyebrow="Watchman · after you agree" title="Keep watching"
        subtitle="Kavach re-checks every tracked policy on its own, keeps every version, ignores formatting noise, and pauses your authorizations when the meaning changes. Update emails that reach Kavach’s monitoring inbox count too." />
      <StatusBar onChecked={() => { policies.reload(); if (sel) loadPolicy(sel); }} />
      <ErrorNote error={error} />
      {policies.loading ? <Spinner /> : !policies.data?.length ? <Empty icon={Eye} title="Nothing on watch yet">Check a website above and press Track. Watchman takes it from there.</Empty> : (
        <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
          <div className="space-y-5">
            <div className="border-t border-line">
              {policies.data.map((p) => (
                <button key={p.id} onClick={() => setSel(p.id)} className="group flex w-full items-center gap-4 border-b border-line py-4 text-left">
                  <div className="min-w-0 flex-1">
                    <div className={cx("text-[16px] font-medium transition-colors", sel === p.id ? "text-gold" : "text-fg2 group-hover:text-fg")}>{p.name} <span className="font-mono text-[12px] text-dim">v{p.current_version}</span></div>
                    <div className="mt-0.5 font-mono text-[11px] uppercase text-dim">{p.domain}</div>
                  </div>
                  {p.requires_reassessment ? <Chip tone="ember">Review</Chip> : p.watch_status === "UNKNOWN" ? <Chip tone="sand">Unknown</Chip> : <Chip tone="mint" dot={false}>Current</Chip>}
                </button>
              ))}
            </div>
            {policy && (
              <Card title={policy.name} meta={policy.last_checked_at ? `Last checked ${fmtTime(policy.last_checked_at)}` : "Not checked yet"}>
                {policy.url && <a href={policy.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 truncate font-mono text-[11.5px] text-dim hover:text-gold">{policy.url}<ArrowUpRight className="h-3 w-3 shrink-0" /></a>}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button icon={RefreshCw} loading={busy === "check"} onClick={() => act(`/policies/${sel}/check`, "check")} disabled={!policy.url}>Check now</Button>
                  {policy.requires_reassessment && <Button variant="primary" icon={ShieldCheck} loading={busy === "re"} onClick={() => act(`/policies/${sel}/reassess`, "re")}>I’ve reviewed it</Button>}
                </div>
                {!policy.url && fx.data && (
                  <div className="mt-5 border-t border-line pt-4">
                    <Collapse label="demo change (fictional policies only)">
                      {isMaps && (
                        <div className="mb-3 flex flex-wrap gap-1.5">
                          <Button size="sm" icon={Wand2} onClick={() => setText(fx.data.betrayal_text)}>The betrayal</Button>
                          <Button size="sm" onClick={() => setText(fx.data.reformatted_text)}>Reformat only</Button>
                        </div>
                      )}
                      <textarea rows={7} className={cx(inputCls, "font-mono text-[12px] leading-relaxed")} value={text} onChange={(e) => setText(e.target.value)} />
                      <Button className="mt-3" icon={FileClock} loading={busy === "publish"} onClick={publish}>Publish and compare</Button>
                    </Collapse>
                  </div>
                )}
              </Card>
            )}
          </div>

          <div className="space-y-5">
            <Card title="Change report" meta={current ? `${current.status} · ${current.from_version ? `v${current.from_version}${current.to_version ? ` → v${current.to_version}` : ""} · ` : ""}${fmtTime(current.created_at)}` : "No changes recorded yet"}>
              {current ? <EventDetail ev={current} policyId={sel} rules={rules.data} /> : <Empty icon={FileClock} title="No changes yet">Watchman reports here when this policy changes.</Empty>}
            </Card>
            <Card title="Version timeline" meta={policy?.analysis ? `Current verdict · ${policy.analysis.headline}` : undefined}
              action={policy?.analysis && <Decision value={policy.analysis.recommendation} />}>
              <ol className="relative ml-1.5 space-y-5 border-l border-line-strong pl-7">
                {[...snaps].reverse().map((s) => {
                  const ev = events.find((e) => e.to_version === s.version);
                  return (
                    <li key={s.id} className="relative">
                      <span className={cx("absolute -left-[33px] top-1 h-2.5 w-2.5 border", s.classification ? NODE[s.classification] : "border-fg2 bg-bg")} />
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-[16px] tracking-[-0.02em]">v{s.version}</span>
                        {s.classification ? <Chip tone={CLASS_TONE[s.classification]}>{label(s.classification)}</Chip> : <Chip dot={false}>First version</Chip>}
                        <span className="font-mono text-[11px] text-dim">{fmtTime(s.retrieved_at)} · {s.content_hash.slice(0, 10)}</span>
                        {ev && <button className="label text-fg2 hover:text-gold" onClick={() => setCurrent(ev)}>Open ↗</button>}
                      </div>
                    </li>
                  );
                })}
                {events.filter((e) => e.status === "UNKNOWN").slice(0, 3).map((e) => (
                  <li key={e.id} className="relative">
                    <span className="absolute -left-[33px] top-1 h-2.5 w-2.5 border border-sand" />
                    <div className="flex items-center gap-3"><Chip tone="sand">Unknown</Chip><span className="font-mono text-[11px] text-dim">{fmtTime(e.created_at)} · {e.error}</span></div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </div>
      )}
      <div className="mt-12"><MonitoringInbox onDelivered={() => { policies.reload(); if (sel) loadPolicy(sel); }} /></div>
    </>
  );
}
