import { ArrowUpRight, Check, Chrome, Globe, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Button, Chip, Collapse, Empty, ErrorNote, PageHeader, RISK_TONE, Ring, cx, fmtTime, goTo } from "../ui";

export const REC = {
  ALLOW: { words: "Looks reasonable", tone: "mint", color: "text-mint" },
  REVIEW: { words: "Needs your review", tone: "sand", color: "text-sand" },
  BLOCK: { words: "Not recommended", tone: "ember", color: "text-ember" },
};
const PREF = {
  OK: ["mint", "Fine for your preferences"],
  CAUTION: ["sand", "Worth a look"],
  CONFLICT: ["ember", "Goes against your preferences"],
  UNKNOWN: ["muted", "Not checked against your preferences"],
  LOOKING: ["muted", "Reading…"],
};
const ringTone = (score) => (score >= 60 ? "ember" : score >= 30 ? "sand" : "mint");

/** One combined review of a website: its privacy policy and terms, through all six agents. */
export function Review({ r, onTrack, tracking, groups, onAssign }) {
  const rec = REC[r.recommendation];
  const [ptone, ptext] = PREF[r.status] || PREF.UNKNOWN;
  if (!r.recommendation) {
    return (
      <div className="card p-6">
        <div className="text-[18px] text-fg">{r.name || r.domain}</div>
        <p className="mt-2 text-[14px] text-muted">{r.headline}</p>
        <ul className="mt-3 space-y-1 text-[13px] text-fg2">{(r.reasons || []).map((x) => <li key={x}>{x}</li>)}</ul>
      </div>
    );
  }
  return (
    <article className="card rise overflow-hidden">
      <div className="grid gap-6 p-6 md:grid-cols-[auto_1fr_auto] md:items-center md:p-8">
        <Ring value={r.risk_score} tone={ringTone(r.risk_score)} size={124} sub="risk / 100" />
        <div className="min-w-0">
          <div className="label text-gold/90">{r.domain}</div>
          <h3 className="h-display mt-2 text-[clamp(1.4rem,2.6vw,2.1rem)]">{r.name}</h3>
          <p className={cx("mt-2 font-mono text-[13px] uppercase tracking-[0.14em]", rec.color)}>{rec.words}</p>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-fg2">{r.headline}</p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <span className="label">Confidence <span className="text-fg">{r.confidence ?? "—"}%</span></span>
          <span className="label">Auditor <span className={r.audit === "PASS" ? "text-mint" : "text-sand"}>{r.audit}</span></span>
          {r.rules && (
            <label className="label flex items-center gap-2">Rules
              {groups && onAssign ? (
                <select value={r.rules.group_id || ""} onChange={(e) => onAssign(e.target.value || null)}
                  className="h-7 border-2 border-fg bg-bg px-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-gold">
                  <option value="">General rules</option>
                  {groups.map((g) => <option key={g.id} value={g.id}>{g.name} group</option>)}
                </select>
              ) : <span className="text-gold">{r.rules.label}</span>}
            </label>
          )}
          {r.tracked ? (
            <button onClick={() => goTo("watchman")} className="mt-2 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mint">
              <Check className="h-3.5 w-3.5" />Tracked · Watchman
            </button>
          ) : onTrack && <Button className="mt-2" variant="primary" loading={tracking} onClick={onTrack}>Track this website</Button>}
        </div>
      </div>

      {r.hidden_instructions && (
        <div className="mx-6 mb-6 border-2 border-ember bg-ember/[0.07] px-4 py-3 text-[14px] text-fg md:mx-8">
          This site’s policy contains instructions hidden for AI agents. Don’t let an agent accept it for you.
        </div>
      )}

      <div className="grid gap-px border-t border-line bg-line md:grid-cols-2">
        <div className="bg-surface p-6 md:p-8">
          <div className="flex items-center justify-between gap-3">
            <span className="label text-fg">Your preferences</span>
            <Chip tone={ptone}>{ptext}</Chip>
          </div>
          <ul className="mt-4 space-y-2 text-[14px] text-fg2">
            {(r.reasons || []).map((x) => <li key={x} className="flex gap-2.5"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gold" />{x}</li>)}
          </ul>
          {r.missing?.length > 0 && <p className="mt-4 text-[13px] text-muted">The policies don’t say {r.missing.join(" or ")}.</p>}
        </div>
        <div className="bg-surface p-6 md:p-8">
          <span className="label text-fg">Riskiest practices</span>
          {!r.factors?.length ? <p className="mt-4 text-[14px] text-muted">Nothing above low risk.</p> : (
            <ul className="mt-4 space-y-3">
              {r.factors.slice(0, 5).map((f) => (
                <li key={f.category}>
                  <div className="flex items-center gap-2">
                    <Chip tone={RISK_TONE[f.level]}>{f.level}</Chip>
                    <span className="text-[14.5px] capitalize text-fg">{f.label}</span>
                    <span className="ml-auto font-mono text-[10.5px] uppercase text-dim">{f.source}</span>
                  </div>
                  {f.quote && <p className="mt-1.5 border-l border-gold/30 pl-3 text-[13px] italic leading-relaxed text-muted">“{f.quote}”</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="border-t border-line px-6 py-5 md:px-8">
        <div className="flex flex-wrap gap-x-8 gap-y-2">
          {(r.documents || []).map((d) => (
            <div key={d.url} className="flex min-w-0 items-center gap-3 text-[13px]">
              <span className="text-fg">{d.label}</span>
              {d.error ? <span className="text-sand">{d.error}</span> : (
                <>
                  <span className="font-mono text-[11px] text-dim">{d.source}</span>
                  {d.risk_score != null && <span className="font-mono text-[11px] text-fg2">risk {d.risk_score}</span>}
                </>
              )}
              <a href={d.url} target="_blank" rel="noreferrer" className="text-dim hover:text-gold" aria-label={`Open ${d.label}`}><ArrowUpRight className="h-3.5 w-3.5" /></a>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <Collapse label="how Kavach decided">
            <div className="grid gap-5 md:grid-cols-2">
              {(r.documents || []).filter((d) => d.how_decided?.length).map((d) => (
                <div key={d.url}>
                  <div className="label mb-2 text-fg">{d.label}</div>
                  <ol className="space-y-1.5">
                    {d.how_decided.map((s, i) => (
                      <li key={s.agent} className="grid grid-cols-[22px_110px_1fr] gap-2 text-[13px]">
                        <span className="font-mono text-gold/70">{String(i + 1).padStart(2, "0")}</span>
                        <span className="text-fg">{s.agent}</span>
                        <span className="text-muted">{s.text}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </Collapse>
        </div>
      </div>
    </article>
  );
}

function ExtensionStatus({ ext }) {
  return (
    <div className="border-2 border-fg bg-surface flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 text-line-strong">
      <Chrome className="h-4 w-4 text-gold" />
      {ext?.connected ? (
        <span className="text-[14px] text-fg2">Browser extension connected{ext.last_seen_at ? ` · last seen ${fmtTime(ext.last_seen_at)}` : ""}. It reviews policy pages as you read them.</span>
      ) : (
        <span className="text-[14px] text-fg2">
          Add the browser extension: open <span className="font-mono text-fg">chrome://extensions</span>, turn on Developer mode, choose Load unpacked and pick the <span className="font-mono text-fg">extension</span> folder. It signs in by itself while you’re signed in here.
        </span>
      )}
    </div>
  );
}

export default function Websites() {
  const sites = useLoad(() => get("/sites"));
  const groups = useLoad(() => get("/rule-groups"));
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const review = async (domain) => {
    setQuery(domain); setBusy("review"); setError(null); setResult(null);
    try { setResult(await post("/sites/review", { domain })); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const track = async () => {
    setBusy("track"); setError(null);
    try { setResult(await post("/sites/track", { domain: result.domain })); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const assignGroup = async (groupId) => {
    setBusy("review"); setError(null);
    try {
      await post("/rule-groups/assign", { domain: result.domain, group_id: groupId });
      setResult(await post("/sites/review", { domain: result.domain }));
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const looking = sites.data?.sites?.some((s) => s.looking);
  useEffect(() => {
    if (!looking) return undefined;
    const t = setTimeout(() => sites.reload(), 4000);
    return () => clearTimeout(t);
  }, [looking, sites.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = sites.data?.sites || [];
  return (
    <>
      <PageHeader index={2} eyebrow="Websites · one review per site" title="Check any website"
        subtitle="Type a website. Kavach finds its privacy policy and terms, puts both through all six agents, and gives you one answer, checked against what you said you’re OK with." />

      <form data-reveal onSubmit={(e) => { e.preventDefault(); if (query.trim()) review(query.trim()); }} className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-dim" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="spotify.com, duolingo.com, any site…"
            className="h-14 w-full border-2 border-fg bg-surface pl-11 pr-4 text-[16px] text-fg outline-none placeholder:text-dim focus:shadow-[3px_3px_0_#2b3af0]" />
        </div>
        <Button variant="primary" size="lg" loading={busy === "review"} disabled={!query.trim()}>Review</Button>
      </form>

      <div data-reveal className="mt-4 flex flex-wrap gap-1.5">
        <span className="label mr-2 self-center">Popular</span>
        {(sites.data?.popular || []).map((p) => (
          <button key={p.id} onClick={() => review(p.domain)} className="h-7 border-2 border-fg px-2.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-fg2 transition-colors hover:bg-yellow hover:text-fg">
            {p.name}
          </button>
        ))}
      </div>

      <div className="mt-6"><ErrorNote error={error} /></div>
      {busy === "review" && (
        <div className="card fade flex items-center gap-4 p-6">
          <span className="h-2 w-2 rounded-full bg-gold live-dot" />
          <span className="text-[14.5px] text-fg2">Reading {query}’s privacy policy and terms. Six agents are reviewing them…</span>
        </div>
      )}
      {result && <Review r={result} onTrack={track} tracking={busy === "track"} groups={groups.data?.groups} onAssign={assignGroup} />}

      <div className="mt-12 grid gap-5">
        <div data-reveal className="flex items-end justify-between">
          <span className="label text-fg">Your websites</span>
          <span className="label">{list.filter((s) => s.tracked).length} tracked · {list.length} in total</span>
        </div>
        {!list.length ? (
          <Empty icon={Globe} title="No websites yet">Review a website above, or browse with the extension: every site you check shows up here.</Empty>
        ) : (
          <div data-reveal className="card overflow-hidden">
            {list.map((s) => {
              const rec = REC[s.recommendation];
              return (
                <button key={s.domain} onClick={() => review(s.domain)} className="group grid w-full grid-cols-[1fr_auto] items-center gap-4 border-b border-line px-5 py-4 text-left last:border-b-0 hover:bg-raised md:grid-cols-[1.4fr_1fr_auto_auto]">
                  <div className="min-w-0">
                    <div className="truncate text-[15.5px] text-fg group-hover:text-gold">{s.name}</div>
                    <div className="font-mono text-[11px] text-dim">{s.domain} · {s.via === "extension" ? "seen with the extension" : "checked here"} · {fmtTime(s.last_seen_at)}</div>
                  </div>
                  <div className="hidden truncate text-[13px] text-muted md:block">{s.looking ? "Reading its policies…" : s.headline}</div>
                  <div className="hidden items-center gap-2 md:flex">
                    {s.changes_pending && <Chip tone="ember">Changed</Chip>}
                    {s.tracked && <Chip tone="mint" dot={false}>Tracked</Chip>}
                    {s.group && <Chip dot={false}>{s.group.name}</Chip>}
                  </div>
                  <div className="flex items-center gap-3">
                    {s.risk_score != null && <span className="num text-[15px] text-fg2">{s.risk_score}</span>}
                    {rec ? <Chip tone={rec.tone}>{rec.words}</Chip> : <Chip>{s.looking ? "Reading" : "No verdict"}</Chip>}
                  </div>
                </button>
              );
            })}
          </div>
        )}
        <ExtensionStatus ext={sites.data?.extension} />
      </div>
    </>
  );
}
