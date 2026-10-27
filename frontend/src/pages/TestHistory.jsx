import { ChevronDown, FlaskConical, Printer, ShieldAlert, Swords } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Button, Chip, Collapse, Empty, ErrorNote, Modal, SectionTitle, Spinner, cx, fmtTime } from "../ui";
import { REC } from "./Websites";

const OUTCOME = {
  SAFE: { words: "Safe", tone: "mint" },
  MISSED: { words: "Threat got through", tone: "ember" },
  FALSE_ALARM: { words: "False alarm", tone: "sand" },
  INCONCLUSIVE: { words: "Inconclusive", tone: "muted" },
};
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const secs = (v) => (v == null ? "—" : v < 1 ? `${Math.round(v * 1000)} ms` : `${v.toFixed(1)} s`);

function Stat({ k, v, tone }) {
  return (
    <div className="border-2 border-fg bg-surface px-4 py-3">
      <div className="label">{k}</div>
      <div className={cx("num mt-1 text-[24px] leading-none", tone)}>{v}</div>
    </div>
  );
}

function Verdict({ v }) {
  if (!v?.recommendation) return <Chip tone="muted">Not assessed</Chip>;
  const r = REC[v.recommendation];
  return <Chip tone={r.tone}>{r.words}{v.risk_score != null ? ` · risk ${v.risk_score}` : ""}</Chip>;
}

function Steps({ steps }) {
  if (!steps?.length) return <p className="text-[13.5px] text-fg2">No actions through the app in this check: it ran the agents directly on the text.</p>;
  return (
    <ol className="space-y-1.5">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-3 text-[13.5px]">
          <span className="mt-0.5 font-mono text-[11px] font-bold text-dim">{String(i + 1).padStart(2, "0")}</span>
          <div className="min-w-0 flex-1">
            <b>{s.actor}</b> {s.did}
            {s.request?.destination && <span className="text-fg2"> · to {s.request.destination}</span>}
            {s.request?.purpose && <span className="text-fg2"> · for {String(s.request.purpose).replaceAll("_", " ")}</span>}
            {s.request?.data_categories && <span className="text-fg2"> · {s.request.data_categories.join(", ")}</span>}
            <span className={cx("ml-2 font-mono text-[11px] font-bold uppercase", s.status >= 400 ? "text-ember" : "text-mint")}>→ {String(s.outcome).replaceAll("_", " ")}</span>
            {s.reasons && <div className="text-[12.5px] text-fg2">{Array.isArray(s.reasons) ? s.reasons.join("; ") : s.reasons}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Check({ r, open, onToggle }) {
  const o = OUTCOME[r.outcome];
  return (
    <li className="border-b-2 border-line last:border-b-0">
      <button onClick={onToggle} className={cx("flex w-full items-center gap-3 px-4 py-3 text-left", open ? "bg-yellow" : "hover:bg-raised")}>
        <span className="w-[62px] shrink-0 font-mono text-[11.5px] font-bold">{r.id}</span>
        <span className="min-w-0 flex-1 text-[14px]"><b>{r.category}</b> <span className="text-fg2">· {r.description}</span></span>
        <Chip tone={o.tone}>{o.words}</Chip>
        <ChevronDown className={cx("h-4 w-4 shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t-2 border-fg bg-surface px-4 py-4 text-[14px]">
          <div className="grid gap-3 sm:grid-cols-2">
            <div><div className="label mb-1">Should happen</div>{r.expected}</div>
            <div><div className="label mb-1">What happened</div>{r.actual}</div>
          </div>
          <div><div className="label mb-1">What Kavach did</div>{r.kavach_did}</div>
          {r.root_cause && <div><div className="label mb-1">Why</div>{r.root_cause}</div>}
          {r.policies?.length > 0 && (
            <div>
              <div className="label mb-1.5">Policies in this check</div>
              <div className="flex flex-wrap gap-2">{r.policies.map((p) => <span key={p.name} className="flex items-center gap-2 border-2 border-fg px-2 py-1 text-[13px]"><b>{p.name}</b><Verdict v={p.verdict} /></span>)}</div>
            </div>
          )}
          {r.steps !== undefined && r.steps !== null && <div><div className="label mb-1.5">Step by step</div><Steps steps={r.steps} /></div>}
          {r.evidence && <div className="text-[12.5px] text-fg2"><span className="label mr-2">Evidence</span>{r.evidence}</div>}
          <div className="font-mono text-[11px] text-dim">took {r.duration_ms} ms</div>
        </div>
      )}
    </li>
  );
}

function RedTeamReport({ id }) {
  const rep = useLoad(() => get(`/test-history/redteam/${id}`), [id]);
  const [open, setOpen] = useState(null);
  if (!rep.data) return rep.error ? <ErrorNote error={rep.error} /> : <Spinner />;
  const d = rep.data, s = d.summary, c = d.counts;
  const wrong = d.results.filter((r) => r.outcome !== "SAFE");
  const attacks = Math.round((s.attack_success_rate ?? 0) * 100);
  return (
    <div className="space-y-8">
      <div className={cx("border-2 border-fg px-5 py-4", c.MISSED ? "bg-ember/10" : "bg-mint/10")}>
        <div className="label text-fg">Summary</div>
        <p className="mt-1 text-[17px] font-bold leading-snug">
          {s.passed} of {s.total} checks held.{" "}
          {c.MISSED ? `${c.MISSED} threat${c.MISSED === 1 ? "" : "s"} got past a check` : "No threat got through"}
          {c.FALSE_ALARM ? `, ${c.FALSE_ALARM} false alarm${c.FALSE_ALARM === 1 ? "" : "s"}` : ""}
          {c.INCONCLUSIVE ? `, ${c.INCONCLUSIVE} couldn't finish` : ""}.{" "}
          {attacks === 0 ? "No attack on agent permissions succeeded and no data was sent where it shouldn't go." : `${attacks}% of attacks on agent permissions succeeded.`}
        </p>
        <p className="mt-2 text-[13px] text-fg2">Run {fmtTime(d.created_at)} · seed {d.seed} · {secs(s.total_seconds)} · an isolated copy of Kavach, so no real data was touched. {s.dataset_note}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat k="Checks held" v={`${s.passed}/${s.total}`} tone={c.MISSED ? "text-sand" : "text-mint"} />
        <Stat k="Wrongly allowed" v={s.false_approvals} tone={s.false_approvals ? "text-ember" : "text-mint"} />
        <Stat k="Wrongly blocked" v={s.false_blocks} tone={s.false_blocks ? "text-sand" : "text-mint"} />
        <Stat k="Attacks that worked" v={pct(s.attack_success_rate)} tone={attacks ? "text-ember" : "text-mint"} />
        <Stat k="Hidden instructions caught" v={pct(s.injection_detection?.recall)} />
        <Stat k="Policy changes caught" v={pct(s.semantic_change_detection?.recall)} />
        <Stat k="Quotes verified" v={pct(s.citation_support_rate)} />
        <Stat k="Slowest check" v={`${s.latency_ms?.max ?? "—"} ms`} />
      </div>

      <section>
        <SectionTitle icon={ShieldAlert}>What went wrong</SectionTitle>
        {!wrong.length ? <p className="text-[14px] text-fg2">Nothing. Every check behaved as expected.</p> : (
          <div className="space-y-3">
            {wrong.map((r) => (
              <div key={r.id} className="border-2 border-fg bg-surface p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] font-bold">{r.id}</span>
                  <b className="text-[15px]">{r.category}</b>
                  <Chip tone={OUTCOME[r.outcome].tone}>{OUTCOME[r.outcome].words}</Chip>
                </div>
                <dl className="mt-3 grid gap-2 text-[14px] sm:grid-cols-[130px_1fr]">
                  <dt className="label pt-1">What happened</dt><dd>{r.kavach_did}</dd>
                  <dt className="label pt-1">Impact</dt><dd>{r.impact}</dd>
                  {r.root_cause && <><dt className="label pt-1">Root cause</dt><dd>{r.root_cause}</dd></>}
                  {r.follow_up && <><dt className="label pt-1">Follow-up</dt><dd>{r.follow_up}</dd></>}
                </dl>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionTitle icon={FlaskConical}>Policies tested</SectionTitle>
        {!d.policies.length ? <p className="text-[14px] text-fg2">This run was recorded before Kavach kept the policies and steps of each check. Run the Red Team again for a full report.</p> : (
          <ul className="divide-y-2 divide-line border-2 border-fg">
            {d.policies.map((p) => (
              <li key={p.name} className="bg-surface px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <b className="text-[15px]">{p.name}</b>
                  <Verdict v={p.verdict} />
                  <span className="font-mono text-[11px] text-dim">{p.how} · used in {p.scenarios.join(", ")}</span>
                </div>
                {p.verdict?.headline && <p className="mt-1 text-[13.5px] text-fg2">{p.verdict.headline}</p>}
                {p.verdict?.factors?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{p.verdict.factors.map((f) => <Chip key={f} tone="fg" dot={false}>{f}</Chip>)}</div>}
                <div className="mt-2"><Collapse label="the policy text"><pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap border-2 border-line bg-bg p-3 font-mono text-[11.5px] text-fg2 scroll-thin">{p.text}{p.chars > p.text.length ? "\n…" : ""}</pre></Collapse></div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <SectionTitle icon={Swords}>Every check</SectionTitle>
        <ul className="border-2 border-fg">
          {d.results.map((r) => <Check key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />)}
        </ul>
      </section>
    </div>
  );
}

function PytestReport({ id }) {
  const rep = useLoad(() => get(`/test-history/pytest/${id}`), [id]);
  if (!rep.data) return rep.error ? <ErrorNote error={rep.error} /> : <Spinner />;
  const d = rep.data, t = d.totals, bad = t.failed + t.error;
  return (
    <div className="space-y-8">
      <div className={cx("border-2 border-fg px-5 py-4", bad ? "bg-ember/10" : "bg-mint/10")}>
        <div className="label text-fg">Summary</div>
        <p className="mt-1 text-[17px] font-bold">{t.passed} of {t.total} automated tests passed{bad ? `, ${bad} failed` : ""}{t.skipped ? `, ${t.skipped} skipped` : ""}.</p>
        <p className="mt-2 text-[13px] text-fg2">Run {fmtTime(d.started_at)} · {secs(d.duration_s)} · code version {d.commit || "unknown"}{d.dirty ? " with unsaved changes" : ""} · Python {d.python}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat k="Passed" v={t.passed} tone="text-mint" />
        <Stat k="Failed" v={bad} tone={bad ? "text-ember" : "text-mint"} />
        <Stat k="Areas covered" v={d.areas.length} />
        <Stat k="Time" v={secs(d.duration_s)} />
      </div>
      <section>
        <SectionTitle icon={ShieldAlert}>What went wrong</SectionTitle>
        {!d.failures.length ? <p className="text-[14px] text-fg2">Nothing. Every test passed.</p> : d.failures.map((f) => (
          <div key={f.id} className="mb-3 border-2 border-fg bg-surface p-4">
            <div className="flex flex-wrap items-center gap-2"><b>{f.name}</b><Chip tone="ember">{f.outcome}</Chip><span className="font-mono text-[11px] text-dim">{f.area}</span></div>
            <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap border-2 border-line bg-bg p-3 font-mono text-[11.5px] text-fg2 scroll-thin">{f.message}</pre>
          </div>
        ))}
      </section>
      <section>
        <SectionTitle icon={FlaskConical}>By area</SectionTitle>
        <ul className="border-2 border-fg">
          {d.areas.map((a) => (
            <li key={a.area} className="border-b-2 border-line px-4 py-3 last:border-b-0">
              <div className="flex items-center gap-3">
                <b className="min-w-0 flex-1 text-[14.5px]">{a.area}</b>
                <Chip tone={a.failed ? "ember" : "mint"}>{a.passed}/{a.total} passed</Chip>
              </div>
              <div className="mt-1"><Collapse label={`the ${a.total} tests`}>
                <ul className="mt-2 space-y-1">
                  {a.tests.map((x) => (
                    <li key={x.id} className="flex gap-2 text-[13px]">
                      <span className={cx("font-mono text-[11px] font-bold uppercase", x.outcome === "passed" ? "text-mint" : x.outcome === "skipped" ? "text-dim" : "text-ember")}>{x.outcome === "passed" ? "✓" : x.outcome === "skipped" ? "–" : "✗"}</span>
                      <span className="min-w-0 flex-1">{x.name}{x.doc && <span className="text-fg2"> · {x.doc}</span>}</span>
                      <span className="font-mono text-[11px] text-dim">{secs(x.duration_s)}</span>
                    </li>
                  ))}
                </ul>
              </Collapse></div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function TestHistory() {
  const data = useLoad(() => get("/test-history"));
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const runRedTeam = async () => {
    setBusy(true); setError(null);
    try {
      const r = await post("/red-team/runs", { seed: Math.floor(Math.random() * 1000) });
      data.reload();
      setOpen({ kind: "redteam", id: r.id, created_at: r.created_at });
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const runs = data.data?.runs || [];
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[14px] text-fg2">Every run is kept. Click one for its postmortem: the policies tested, whether you were safe, what Kavach did and what went wrong.</p>
        <Button variant="primary" icon={Swords} loading={busy} onClick={runRedTeam}>Run Red Team now</Button>
      </div>
      <ErrorNote error={error} />
      {data.loading && !data.data ? <Spinner /> : !runs.length ? (
        <Empty icon={FlaskConical} title="No runs yet">Press Run Red Team now, or run the automated tests (pytest in the backend folder). Each run shows up here.</Empty>
      ) : (
        <ul className="border-2 border-fg">
          {runs.map((r) => {
            const bad = r.failed;
            return (
              <li key={`${r.kind}-${r.id}`} className="border-b-2 border-line last:border-b-0">
                <button onClick={() => setOpen(r)} className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 bg-surface px-4 py-3 text-left hover:bg-yellow md:grid-cols-[170px_1fr_auto_auto]">
                  <span className="font-mono text-[12px] font-bold">{fmtTime(r.created_at)}</span>
                  <span className="order-3 flex min-w-0 items-center gap-2 md:order-none">
                    <Chip tone="fg" dot={false}>{r.kind === "redteam" ? "Red Team" : "Automated"}</Chip>
                    <span className="truncate text-[14px]">{r.passed}/{r.total} passed{r.commit ? <span className="text-fg2"> · {r.commit}{r.dirty ? "+" : ""}</span> : ""}</span>
                  </span>
                  <span className="order-2 md:order-none">
                    {r.kind === "redteam" && r.missed ? <Chip tone="ember">{r.missed} threat{r.missed === 1 ? "" : "s"} missed</Chip>
                      : bad ? <Chip tone={r.kind === "redteam" ? "sand" : "ember"}>{bad} failed</Chip> : <Chip tone="mint">All passed</Chip>}
                  </span>
                  <span className="order-4 hidden font-mono text-[11px] text-dim md:block">{secs(r.duration_s)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {open && (
        <Modal wide eyebrow={`Postmortem · ${open.kind === "redteam" ? "Red Team attack run" : "Automated tests"}`} title={fmtTime(open.created_at)} onClose={() => setOpen(null)}>
          <div className="print-area">
            <div className="mb-6 flex justify-end no-print"><Button size="sm" icon={Printer} onClick={() => window.print()}>Print or save as PDF</Button></div>
            {open.kind === "redteam" ? <RedTeamReport id={open.id} /> : <PytestReport id={open.id} />}
          </div>
        </Modal>
      )}
    </div>
  );
}
