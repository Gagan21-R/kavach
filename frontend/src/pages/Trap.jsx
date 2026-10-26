import { Bot, CheckCircle2, EyeOff, MousePointerClick, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Badge, Button, Card, ErrorNote, PageHeader, cx, label } from "../ui";

function PagePreview({ segments, reveal }) {
  if (!segments) return null;
  return (
    <div className="rounded-lg border border-slate-300 bg-white shadow-inner">
      <div className="flex items-center gap-1.5 border-b border-slate-200 bg-slate-100 px-3 py-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-red-300" /><span className="h-2.5 w-2.5 rounded-full bg-amber-300" /><span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
        <span className="ml-2 rounded bg-white px-2 py-0.5 text-[11px] text-slate-500">https://quickdeals.example/signup</span>
      </div>
      <div className="whitespace-pre-line p-4 text-[13px] leading-6 text-slate-700">
        {segments.map((s, i) => {
          if (!s.hidden) return <span key={i}>{s.text.replace(/\n\s*\n+/g, "\n")}</span>;
          if (!reveal) return null;
          return (
            <span key={i} className={cx("my-1 block rounded border-2 border-dashed px-2 py-1 text-[12px]", s.suspicious ? "border-red-400 bg-red-50 text-red-700" : "border-slate-300 bg-slate-50 text-slate-500")}>
              <span className="mr-1.5 inline-flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wide"><EyeOff className="h-3 w-3" />hidden · {s.reason}</span>
              {s.text.trim()}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function AgentRun({ title, icon: Icon, tone, run, busy, onRun, buttonLabel }) {
  const [visible, setVisible] = useState(0);
  useEffect(() => {
    if (!run) return undefined;
    setVisible(0);
    const t = setInterval(() => setVisible((n) => (n >= run.steps.length ? (clearInterval(t), n) : n + 1)), 700);
    return () => clearInterval(t);
  }, [run]);
  const done = run && visible >= run.steps.length;
  const bad = run?.outcome === "ACCEPTED_ALL";
  return (
    <Card title={<span className="flex items-center gap-2"><Icon className={cx("h-4 w-4", tone)} />{title}</span>}
      action={<Button size="sm" variant={bad === false && run ? "secondary" : "primary"} loading={busy} onClick={onRun} icon={MousePointerClick}>{buttonLabel}</Button>}>
      {!run ? <p className="text-[13px] text-slate-500">Not run yet.</p> : (
        <div className="space-y-2">
          {run.steps.slice(0, visible).map((s, i) => (
            <div key={i} className="rise flex gap-2 text-[13px] text-slate-700"><span className="mt-0.5 text-[11px] tabular-nums text-slate-400">{i + 1}.</span>{s}</div>
          ))}
          {done && (
            <div className={cx("rise mt-3 flex items-center gap-2 rounded-lg px-3 py-2.5 text-[13px] font-medium",
              bad ? "bg-red-600 text-white" : run.outcome === "BLOCKED" ? "bg-emerald-600 text-white" : "bg-amber-100 text-amber-900")}>
              {bad ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
              {bad ? "Accepted every data-sharing option on your behalf." : run.outcome === "BLOCKED" ? "Blocked. Nothing was clicked; you decide." : label(run.outcome)}
            </div>
          )}
          {done && run.signals?.filter((s) => s.assessment === "suspicious").map((s) => (
            <div key={s.id} className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-[12px] text-red-800">
              <Badge tone="red">{label(s.kind)}</Badge> <span className="ml-1">{s.explanation}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function Trap() {
  const fx = useLoad(() => get("/demo/fixtures"));
  const [html, setHtml] = useState("");
  const [naive, setNaive] = useState(null);
  const [guarded, setGuarded] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [segments, setSegments] = useState(null);

  useEffect(() => { if (fx.data && !html) setHtml(fx.data.trap_page); }, [fx.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (guardedMode) => {
    setBusy(guardedMode ? "g" : "n");
    setError(null);
    try {
      const r = await post("/demo/trap", { html, guarded: guardedMode });
      setSegments(r.segments);
      if (guardedMode) { setGuarded(r); setReveal(true); } else setNaive(r);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };
  useEffect(() => { if (fx.data && html && !segments) post("/demo/trap", { html, guarded: false }).then((r) => setSegments(r.segments)).catch(() => {}); }, [fx.data, html]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader title="The Trap" subtitle="A signup page hides an instruction for AI agents in white-on-white text and an HTML comment. People can't see it; a naive browser agent reads it and obeys. Consent Court's Sentinel catches it first.">
        <Button onClick={() => { setNaive(null); setGuarded(null); setReveal(false); }}>Reset</Button>
      </PageHeader>
      <ErrorNote error={error} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="The signup page" subtitle="What a person sees. Hidden content appears only after the Sentinel exposes it."
          action={<Button size="sm" icon={EyeOff} onClick={() => setReveal(!reveal)}>{reveal ? "Hide" : "Reveal"} hidden text</Button>}>
          <PagePreview segments={segments} reveal={reveal} />
          <div className="mt-3 flex flex-wrap gap-2">
            {fx.data && <Button size="sm" onClick={() => { setHtml(fx.data.trap_page); setSegments(null); setNaive(null); setGuarded(null); }}>Malicious page</Button>}
            {fx.data && <Button size="sm" onClick={() => { setHtml(fx.data.benign_page); setSegments(null); setNaive(null); setGuarded(null); }}>Benign page</Button>}
          </div>
        </Card>
        <div className="space-y-6">
          <AgentRun title="Naive AI agent" icon={Bot} tone="text-red-500" run={naive} busy={busy === "n"} onRun={() => run(false)} buttonLabel="Let it sign up" />
          <AgentRun title="Agent with Consent Court" icon={ShieldCheck} tone="text-emerald-600" run={guarded} busy={busy === "g"} onRun={() => run(true)} buttonLabel="Sign up, guarded" />
          {guarded?.headline && (
            <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white p-4 text-[13px] text-slate-700 shadow-sm">
              <ShieldAlert className="mt-0.5 h-4 w-4 text-indigo-600" />
              <div><b className="text-slate-900">Court's view:</b> {guarded.headline} {guarded.charges?.length ? `The page also discloses ${guarded.charges.length} data practice(s) the Prosecutor charged.` : ""}</div>
            </div>
          )}
        </div>
      </div>
      <p className="mt-6 text-[12px] text-slate-400">Both agents are simulations: nothing is clicked on a real site. In production the same check runs through the Guardian API, which also refuses tokens for any policy page the Sentinel flags.</p>
    </>
  );
}
