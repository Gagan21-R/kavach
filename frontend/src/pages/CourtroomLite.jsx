import { Gavel } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Button, Chip, Collapse, ErrorNote, RISK_TONE, Ring, cx, inputCls } from "../ui";
import { REC } from "./Websites";

const AGENT_TONE = { sentinel: "text-earth", prosecutor: "text-ember", defense: "text-mint", evidence_clerk: "text-fg2", judge: "text-gold", auditor: "text-sand" };

/** Paste any policy text and put it through the six agents. Nothing is tracked or stored. */
export default function CourtroomLite() {
  const fx = useLoad(() => get("/demo/fixtures"));
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [r, setR] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async () => {
    setBusy(true); setError(null); setR(null);
    try { setR(await post("/sites/trial", { name: name || "This policy", text })); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const rec = r && REC[r.recommendation];

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
      <div>
        <div className="flex flex-wrap gap-1.5">
          {(fx.data?.policies || []).map((p) => (
            <button key={p.name} onClick={() => { setName(p.name); setText(p.text); }}
              className="h-7 border-2 border-fg px-2.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-fg2 hover:bg-yellow hover:text-fg">
              Sample: {p.name}
            </button>
          ))}
        </div>
        <input className={cx(inputCls, "mt-3")} value={name} onChange={(e) => setName(e.target.value)} placeholder="Company or app name" />
        <textarea rows={9} className={cx(inputCls, "mt-2 text-[13px] leading-relaxed")} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a privacy policy or terms…" />
        <Button className="mt-3" variant="primary" icon={Gavel} loading={busy} disabled={text.trim().length < 20} onClick={run}>Put on trial</Button>
        <div className="mt-3"><ErrorNote error={error} /></div>
      </div>
      <div>
        {!r ? <p className="text-[14px] text-muted">The six agents read the text, argue each practice with the exact sentence as evidence, and an independent auditor checks the verdict.</p> : !rec ? (
          <p className="text-[14px] text-sand">{r.headline}</p>
        ) : (
          <div className="fade">
            <div className="flex items-center gap-5">
              <Ring value={r.risk_score} size={96} tone={r.risk_score >= 60 ? "ember" : r.risk_score >= 30 ? "sand" : "mint"} sub="risk" />
              <div className="min-w-0">
                <p className={cx("font-mono text-[12px] uppercase tracking-[0.14em]", rec.color)}>{rec.words}</p>
                <p className="mt-1.5 text-[14.5px] text-fg">{r.headline}</p>
                <p className="label mt-2">Confidence <span className="text-fg">{r.confidence ?? "—"}%</span> · Auditor <span className={r.audit === "PASS" ? "text-mint" : "text-sand"}>{r.audit}</span></p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {(r.factors || []).map((f) => <Chip key={f.category} tone={RISK_TONE[f.level]}>{f.label} · {f.level}</Chip>)}
            </div>
            <ol className="mt-4 space-y-1.5">
              {r.how_decided.map((s, i) => (
                <li key={s.agent} className="grid grid-cols-[22px_100px_1fr] gap-2 text-[13px]">
                  <span className="font-mono text-gold/70">{String(i + 1).padStart(2, "0")}</span><span className="text-fg">{s.agent}</span><span className="text-muted">{s.text}</span>
                </li>
              ))}
            </ol>
            <div className="mt-4">
              <Collapse label="the full debate">
                <ol className="scroll-thin max-h-80 space-y-2 overflow-auto pr-2">
                  {r.transcript.map((m) => (
                    <li key={m.seq} className="text-[12.5px] leading-relaxed">
                      <span className={cx("font-mono text-[10.5px] uppercase tracking-[0.1em]", AGENT_TONE[m.agent] || "text-fg2")}>{m.agent.replace("_", " ")}</span>
                      <span className="ml-2 text-fg2">{m.text}</span>
                    </li>
                  ))}
                </ol>
              </Collapse>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
