import { BadgeCheck, FileSearch, Gavel, Megaphone, Play, RotateCcw, Scale, Shield, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import {
  Badge, Button, Card, Collapse, Decision, Empty, ErrorNote, Field, PageHeader, RISK_TONE, cx, inputCls, label,
} from "../ui";

const AGENTS = {
  sentinel: { name: "Sentinel", icon: ShieldCheck, tone: "bg-slate-700", role: "screens input" },
  prosecutor: { name: "Prosecutor", icon: Megaphone, tone: "bg-red-600", role: "argues risk" },
  defense: { name: "Defense", icon: Shield, tone: "bg-sky-600", role: "argues purpose" },
  evidence_clerk: { name: "Evidence Clerk", icon: FileSearch, tone: "bg-violet-600", role: "verifies citations" },
  judge: { name: "Judge", icon: Scale, tone: "bg-indigo-700", role: "rules" },
  auditor: { name: "Independent Auditor", icon: BadgeCheck, tone: "bg-emerald-600", role: "checks the ruling" },
};
const SEV_TONE = { HIGH: "red", CRITICAL: "red", MEDIUM: "amber", LOW: "blue" };
const POS_TONE = { justified: "green", partially_justified: "amber", not_justified: "red", insufficient_evidence: "gray" };

function Message({ m, onCite, active }) {
  const a = AGENTS[m.agent];
  const Icon = a.icon;
  const right = m.agent === "defense";
  return (
    <div className={cx("rise flex gap-3", right && "flex-row-reverse")}>
      <div className={cx("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white", a.tone)} title={a.role}><Icon className="h-4 w-4" /></div>
      <div className={cx("max-w-[85%] rounded-xl border px-3.5 py-2.5", right ? "border-sky-100 bg-sky-50/60" : m.agent === "prosecutor" ? "border-red-100 bg-red-50/50" : "border-slate-200 bg-white",
        active && "ring-2 ring-amber-300")}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[12px]">
          <span className="font-semibold text-slate-900">{a.name}</span>
          {m.finding_id && <Badge>{m.finding_id}</Badge>}
          {m.category && <Badge tone="purple">{label(m.category)}</Badge>}
          {m.severity && <Badge tone={SEV_TONE[m.severity]}>{m.severity}</Badge>}
          {m.agent === "defense" && <Badge tone={POS_TONE[m.kind]}>{label(m.kind)}</Badge>}
          {m.agent === "evidence_clerk" && <Badge tone={m.kind === "verified" ? "green" : "red"}>{m.kind}</Badge>}
          {m.recommendation && <Decision value={m.recommendation} />}
          {m.verdict && <Decision value={m.verdict} />}
        </div>
        <p className="text-[13px] leading-relaxed text-slate-700">{m.text}</p>
        {m.citations?.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {m.citations.map((c, i) => (
              <button key={i} onClick={() => onCite(c.clause_id, m.seq)} className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[11.5px] text-amber-800 hover:bg-amber-100">
                cites {c.clause_id}
              </button>
            ))}
          </div>
        )}
        {m.signals?.filter((s) => s.assessment === "suspicious").map((s) => (
          <div key={s.id} className="mt-1.5 rounded border border-red-200 bg-red-50 px-2 py-1 text-[12px] text-red-700">
            <b>{label(s.kind)}:</b> “{s.excerpt}”
          </div>
        ))}
      </div>
    </div>
  );
}

function Evidence({ text, clauses, charges, highlight }) {
  const ref = useRef(null);
  const sev = useMemo(() => {
    const m = {};
    const rank = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };
    for (const ch of charges || []) for (const c of ch.citations) if (!m[c.clause_id] || rank[ch.severity] > rank[m[c.clause_id]]) m[c.clause_id] = ch.severity;
    return m;
  }, [charges]);
  useEffect(() => {
    if (highlight) ref.current?.querySelector(`[data-clause="${highlight}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight]);
  const parts = [];
  let pos = 0;
  for (const c of clauses) {
    if (c.start > pos) parts.push(<span key={`g${pos}`}>{text.slice(pos, c.start)}</span>);
    const s = sev[c.id];
    parts.push(
      <span key={c.id} data-clause={c.id} title={c.id}
        className={cx("rounded px-0.5 transition", highlight === c.id && "bg-amber-200",
          s && "underline decoration-2 underline-offset-4", s === "HIGH" ? "decoration-red-400" : s === "MEDIUM" ? "decoration-amber-400" : s ? "decoration-sky-400" : "")}>
        <sup className="mr-0.5 text-[9px] text-slate-400">{c.id}</sup>{text.slice(c.start, c.end)}
      </span>,
    );
    pos = c.end;
  }
  if (pos < text.length) parts.push(<span key="tail">{text.slice(pos)}</span>);
  return <div ref={ref} className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 font-serif text-[14px] leading-7 text-slate-700 scroll-thin">{parts}</div>;
}

function Verdict({ r }) {
  const j = r.judge;
  const a = r.auditor;
  if (!j) return <ErrorNote error={{ code: "ANALYSIS FAILED", message: a?.abstain_reason || r.errors?.join("; ") }} />;
  const score = j.risk_score?.value;
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5">
        <div className="flex flex-wrap items-center gap-2"><Decision value={j.recommendation} /><span className="text-[12px] text-slate-500">Judge's recommendation (advisory; the Guardian enforces your rules)</span></div>
        <h3 className="mt-2 font-serif text-[21px] font-semibold leading-snug text-slate-900">{j.headline}</h3>
        <div className="mt-4 flex flex-wrap items-center gap-6">
          <div>
            <div className="text-[12px] text-slate-500">Risk score</div>
            <div className="flex items-center gap-2"><span className="text-[28px] font-semibold tabular-nums text-slate-900">{score}</span><span className="text-[12px] text-slate-400">/ 100</span></div>
          </div>
          <div className="flex-1">
            <div className="h-2 rounded-full bg-slate-100"><div className={cx("h-2 rounded-full", score >= 50 ? "bg-red-500" : score >= 25 ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${score}%` }} /></div>
            <div className="mt-1.5"><Collapse label="why this score">
              <p className="text-[12px] text-slate-600">{j.risk_score.method}. It is a transparent sum, not a probability of harm.</p>
              <div className="mt-1 flex flex-wrap gap-1.5">{Object.entries(j.risk_score.inputs).filter(([, v]) => v > 0).map(([k, v]) => <Badge key={k}>{label(k)} +{v}</Badge>)}</div>
            </Collapse></div>
          </div>
          <div>
            <div className="text-[12px] text-slate-500">Independent auditor</div>
            <Decision value={a.verdict} />
          </div>
        </div>
        <p className="mt-3 text-[12.5px] text-slate-600">{a.explanation}</p>
        {a.issues?.length > 0 && <ul className="mt-2 space-y-1">{a.issues.map((i, k) => <li key={k} className="text-[12px] text-red-700">• {label(i.kind)} ({i.severity}): {i.explanation}</li>)}</ul>}
      </div>

      <div>
        <h4 className="mb-2 text-[13px] font-semibold text-slate-800">Data trade-off map</h4>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {j.category_map.map((c) => (
            <div key={c.category} className={cx("rounded-lg border p-2.5", { high: "border-red-200 bg-red-50", medium: "border-amber-200 bg-amber-50", low: "border-sky-200 bg-sky-50", none: "border-emerald-200 bg-emerald-50", unknown: "border-slate-200 bg-slate-50" }[c.risk_level])}>
              <div className="flex items-center justify-between"><span className="text-[12.5px] font-medium capitalize text-slate-800">{label(c.category)}</span><Badge tone={RISK_TONE[c.risk_level]}>{c.risk_level}</Badge></div>
              <div className="mt-1 text-[11.5px] leading-snug text-slate-600">{c.explanation}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div><h4 className="mb-2 text-[13px] font-semibold text-slate-800">Questions to ask</h4>
          {j.questions_to_ask.length ? <ul className="space-y-1.5 text-[12.5px] text-slate-600">{j.questions_to_ask.map((q) => <li key={q}>• {q}</li>)}</ul> : <p className="text-[12.5px] text-slate-400">None.</p>}</div>
        <div><h4 className="mb-2 text-[13px] font-semibold text-slate-800">Safer choices</h4>
          {j.safer_choices.length ? <ul className="space-y-1.5 text-[12.5px] text-slate-600">{j.safer_choices.map((q) => <li key={q}>• {q}</li>)}</ul> : <p className="text-[12.5px] text-slate-400">None needed.</p>}</div>
      </div>

      <div>
        <h4 className="mb-2 text-[13px] font-semibold text-slate-800">Confidence, by component</h4>
        <div className="grid gap-2 md:grid-cols-2">
          {j.confidence.map((c) => (
            <div key={c.component} className="rounded-lg border border-slate-200 p-2.5">
              <div className="flex items-center justify-between text-[12.5px]"><span className="font-medium capitalize text-slate-800">{label(c.component)}</span>
                <span className="tabular-nums text-slate-700">{c.value == null ? "n/a" : `${Math.round(c.value * 100)}%`} <Badge tone={c.basis === "calibrated" ? "green" : "gray"}>{c.basis}</Badge></span></div>
              <div className="mt-1 text-[11.5px] text-slate-500">{c.explanation}</div>
            </div>
          ))}
        </div>
      </div>

      {(j.disagreements.length > 0 || j.missing_information.length > 0) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12.5px] text-amber-900">
          {j.disagreements.filter((d) => !d.resolved).map((d) => <div key={d.finding_id}>• Unresolved ({d.finding_id}): {d.resolution}</div>)}
          {j.missing_information.map((m) => <div key={m}>• The policy does not say {m}.</div>)}
        </div>
      )}
      <p className="text-[11.5px] text-slate-400">{j.limitations.join(" ")}</p>
    </div>
  );
}

export default function Courtroom() {
  const fixtures = useLoad(() => get("/demo/fixtures"));
  const policies = useLoad(() => get("/policies"));
  const [form, setForm] = useState({ name: "", domain: "", text: "" });
  const [result, setResult] = useState(null);
  const [shown, setShown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [highlight, setHighlight] = useState(null);
  const [activeMsg, setActiveMsg] = useState(null);
  const streamRef = useRef(null);

  const transcript = result?.transcript || [];
  useEffect(() => {
    if (!result) return undefined;
    setShown(0);
    const t = setInterval(() => setShown((n) => (n >= transcript.length ? (clearInterval(t), n) : n + 1)), 650);
    return () => clearInterval(t);
  }, [result]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" }); }, [shown]);

  const load = (p) => setForm({ name: p.name, domain: p.domain, text: p.text });
  const start = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    setHighlight(null);
    try {
      const r = await post("/policies/analyze", form);
      setResult(r.analysis.result);
      policies.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const openExisting = async (id) => {
    setError(null);
    setHighlight(null);
    try {
      const a = await get(`/policies/${id}/analysis`);
      setResult(a.result);
    } catch (err) {
      setError(err);
    }
  };
  const done = result && shown >= transcript.length;

  return (
    <>
      <PageHeader title="The Courtroom" subtitle="Every policy goes on trial. The Sentinel screens it, the Prosecutor and Defense argue each clause with citations, the Evidence Clerk verifies them, the Judge rules and an independent auditor checks the ruling." />
      <div className="grid gap-6 xl:grid-cols-5">
        <div className="space-y-6 xl:col-span-2">
          <Card title="Put a policy on trial" subtitle="Paste a privacy policy or a signup page. It is treated as data, never as instructions.">
            <form onSubmit={start} className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {fixtures.data?.policies.map((p) => <Button type="button" size="sm" key={p.name} onClick={() => load(p)}>Load {p.name}</Button>)}
                {fixtures.data && <Button type="button" size="sm" onClick={() => setForm({ name: "QuickDeals", domain: "quickdeals.example", text: fixtures.data.trap_page })}>Load trap page</Button>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="App or company"><input required className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="FlashLight" /></Field>
                <Field label="Domain"><input required className={inputCls} value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="flashlight.example" /></Field>
              </div>
              <Field label="Policy text or HTML"><textarea required rows={9} className={cx(inputCls, "font-mono text-[12px]")} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} /></Field>
              <ErrorNote error={error} />
              <Button variant="primary" icon={Gavel} loading={busy} className="w-full">Start trial</Button>
            </form>
          </Card>
          {policies.data?.length > 0 && (
            <Card title="Past trials">
              <div className="space-y-1.5">
                {policies.data.map((p) => (
                  <button key={p.id} onClick={() => openExisting(p.id)} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-slate-50">
                    <span><span className="font-medium text-slate-800">{p.name}</span> <span className="text-slate-400">v{p.current_version}</span></span>
                    <Decision value={p.analysis?.recommendation} />
                  </button>
                ))}
              </div>
            </Card>
          )}
          {result && (
            <Card title="Evidence" subtitle="Canonical visible text. Underlines mark charged clauses; click a citation to highlight it.">
              <Evidence text={result.canonical_text} clauses={result.clauses} charges={result.prosecutor?.charges} highlight={highlight} />
            </Card>
          )}
        </div>
        <div className="space-y-6 xl:col-span-3">
          <Card title="Live debate" subtitle={result ? `${Math.min(shown, transcript.length)} of ${transcript.length} statements` : "Waiting for a case"}
            action={result && <Button size="sm" icon={done ? RotateCcw : Play} onClick={() => setShown(done ? 0 : transcript.length)}>{done ? "Replay" : "Skip to verdict"}</Button>}>
            {!result ? <Empty icon={Gavel} title="No case in session">Load FlashLight and start a trial to watch the agents argue.</Empty> : (
              <div ref={streamRef} className="max-h-[560px] space-y-3 overflow-y-auto pr-1 scroll-thin">
                {transcript.slice(0, shown).map((m) => <Message key={m.seq} m={m} active={activeMsg === m.seq} onCite={(cid, seq) => { setHighlight(cid); setActiveMsg(seq); }} />)}
                {!done && <div className="flex items-center gap-2 pl-11 text-[12px] text-slate-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />{AGENTS[transcript[shown]?.agent]?.name || "Court"} is speaking…</div>}
              </div>
            )}
          </Card>
          {done && <Card title="Verdict"><Verdict r={result} /></Card>}
        </div>
      </div>
    </>
  );
}
