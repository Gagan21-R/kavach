import { Activity, ArrowUpRight, Bell, Sparkles } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useAgent, useAuth, useLoad } from "../state";
import { Button, Chip, Empty, ErrorNote, Eyebrow, KavachMark, SectionTitle, Spinner, cx, fmtTime, goTo } from "../ui";
import { REC } from "./Websites";

const EVENT_WORDS = {
  "site.tracked": "Started tracking a website",
  "policy.acquired": "Fetched a policy",
  "policy.analyzed": "Six agents reviewed a policy",
  "policy.snapshot.created": "Saved a new policy version",
  "consent.review.required": "A policy changed: your review is needed",
  "policy.watch.unknown": "Couldn’t read a policy on its check",
  "email.policy_update": "An update email reached Kavach’s inbox",
  "extension.paired": "Browser extension connected",
  "extension.page_analyzed": "The extension reviewed a policy page",
  "extension.consent_moment": "The extension checked a signup page",
  "preferences.saved": "Your preferences were saved",
  "auth.login": "You signed in",
  "guardian.decision": "The Guardian decided on an agent request",
  "emergency_stop.engaged": "Emergency stop engaged",
};

function Stat({ label, value, tone, hint, onClick }) {
  return (
    <button onClick={onClick} className="group bg-surface p-6 text-left transition-colors hover:bg-yellow">
      <div className="label">{label}</div>
      <div className={cx("num mt-4 text-[48px] leading-none", tone || "text-fg")}>{value}</div>
      {hint && <div className="mt-3 flex items-center gap-1 font-mono text-[12px] font-bold uppercase text-gold group-hover:underline">{hint}<ArrowUpRight className="h-3.5 w-3.5" /></div>}
    </button>
  );
}

export default function Overview() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useLoad(() => get("/dashboard/summary"));
  const sites = useLoad(() => get("/sites"));
  const watch = useLoad(() => get("/watchman/status"));
  const { setAgent } = useAgent();
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState(null);

  const seed = async () => {
    setSeeding(true); setSeedError(null);
    try {
      const r = await post("/demo/seed");
      setAgent({ id: r.agent_id, name: "demo-browser-agent", key: r.agent_key });
      await reload();
    } catch (e) { setSeedError(e); } finally { setSeeding(false); }
  };

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorNote error={error} />;
  const c = data.counts;
  const tracked = (sites.data?.sites || []).filter((s) => s.tracked);
  const attention = [
    ...data.policies.filter((p) => p.requires_reassessment).map((p) => ({ key: p.id, tone: "ember", text: `${p.name} changed in a way your earlier approval doesn’t cover.`, go: "watchman", cta: "Review the change" })),
    ...data.policies.filter((p) => p.watch_status === "UNKNOWN").map((p) => ({ key: `u${p.id}`, tone: "sand", text: `${p.name} couldn’t be read on its last check.`, go: "watchman", cta: "See Watchman" })),
    ...(c.pending_approvals ? [{ key: "appr", tone: "sand", text: `${c.pending_approvals} AI agent request${c.pending_approvals === 1 ? "" : "s"} waiting for your decision.`, go: "agents", cta: "Decide" }] : []),
  ];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <>
      <section className="grid items-stretch gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="rise">
          <Eyebrow index={1}>{greeting}{user?.email ? `, ${user.email.split("@")[0]}` : ""}</Eyebrow>
          <h1 className="h-display mt-6 text-[clamp(2.4rem,6vw,4.6rem)]">Your consent, <span className="marker">guarded.</span></h1>
          <p className="mt-6 max-w-xl border-l-4 border-fg pl-4 text-[17px] leading-relaxed text-fg2">
            Kavach reads the policies of the sites you use, checks them against your rules, and keeps watching for changes, so you don’t have to.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {[
              [data.frozen ? "ember" : "mint", data.frozen ? "Agents frozen" : "Guardian online"],
              [watch.data?.automatic ? "mint" : "sand", watch.data?.automatic ? `Checks every ${Math.round((watch.data?.every_minutes || 360) / 60)} h` : "Watchman ready"],
              [sites.data?.extension?.connected ? "mint" : "muted", sites.data?.extension?.connected ? "Extension connected" : "Extension not added"],
            ].map(([tone, text]) => <Chip key={text} tone={tone}>{text}</Chip>)}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button variant="primary" size="lg" onClick={() => goTo("websites")}>Check a website</Button>
            <Button size="lg" onClick={() => goTo("watchman")}>Open Watchman</Button>
          </div>
        </div>
        <div className="ink-block relative hidden min-h-[320px] overflow-hidden lg:block">
          <img src="/brand/kavach-emblem.webp" alt="Kavach emblem: a golden shield and padlock" className="glow absolute inset-0 size-full object-cover" />
          <span className="label absolute bottom-3 left-3 bg-yellow px-2 py-1 text-fg">Kavach · consent, guarded</span>
        </div>
      </section>

      <div className="card hairgrid mt-10 grid grid-cols-2 gap-[2px] overflow-hidden lg:grid-cols-4">
        <Stat label="Websites tracked" value={tracked.length} hint="Websites" onClick={() => goTo("websites")} />
        <Stat label="Need your review" value={attention.length} tone={attention.length ? "text-sand" : "text-mint"} hint="Watchman" onClick={() => goTo("watchman")} />
        <Stat label="Your rules" value={c.active_rules} hint="Your rules" onClick={() => goTo("rules")} />
        <Stat label="AI agents" value={c.agents} hint="AI agents" onClick={() => goTo("agents")} />
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.2fr_1fr]">
        <section className="card p-6">
          <SectionTitle icon={Bell}>Needs your attention</SectionTitle>
          {!attention.length ? (
            <p className="mt-4 text-[14.5px] text-muted">Nothing right now. Kavach will flag it here when a policy changes or an agent asks for something.</p>
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {attention.map((a) => (
                <li key={a.key} className="flex flex-wrap items-center gap-3 py-3">
                  <span className={cx("h-2 w-2 rounded-full", a.tone === "ember" ? "bg-ember" : "bg-sand")} />
                  <span className="min-w-0 flex-1 text-[14.5px] text-fg2">{a.text}</span>
                  <Button size="sm" onClick={() => goTo(a.go)}>{a.cta}</Button>
                </li>
              ))}
            </ul>
          )}
          {tracked.length > 0 && (
            <>
              <div className="label mt-8 text-fg">Tracked websites</div>
              <ul className="mt-3 divide-y divide-line">
                {tracked.slice(0, 6).map((s) => (
                  <li key={s.domain} className="flex items-center gap-3 py-2.5">
                    <span className="min-w-0 flex-1 truncate text-[14.5px] text-fg">{s.name}</span>
                    {s.risk_score != null && <span className="num text-[13px] text-muted">{s.risk_score}</span>}
                    {REC[s.recommendation] && <Chip tone={REC[s.recommendation].tone}>{REC[s.recommendation].words}</Chip>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section className="card p-6">
          <div className="flex items-center justify-between">
            <SectionTitle icon={Activity}>Recent activity</SectionTitle>
            <KavachMark className="h-5 w-5 opacity-60" />
          </div>
          {!data.recent.length ? <Empty title="Nothing yet">Activity shows up here as Kavach works.</Empty> : (
            <ul className="mt-4 space-y-3">
              {data.recent.slice(0, 9).map((e) => (
                <li key={e.seq} className="grid grid-cols-[1fr_auto] gap-3 text-[13.5px]">
                  <span className="text-fg2">{EVENT_WORDS[e.event_type] || e.event_type.replaceAll(".", " ").replaceAll("_", " ")}</span>
                  <span className="font-mono text-[11px] text-dim">{fmtTime(e.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-6 border-t border-line pt-4">
            <ErrorNote error={seedError} />
            <Button size="sm" icon={Sparkles} loading={seeding} onClick={seed}>Load demo data</Button>
            <p className="mt-2 text-[12px] text-dim">Adds two fictional policies, sample rules and a demo AI agent for the agent features.</p>
          </div>
        </section>
      </div>
    </>
  );
}
