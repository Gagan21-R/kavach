import { ArrowLeft, ArrowRight, Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useAuth } from "../state";
import { Button, ErrorNote, Modal, Spinner, cx } from "../ui";

const ANSWERS = ["OK", "ASK", "NEVER"];
const ANSWER_LABEL = { OK: "OK", ASK: "Ask me", NEVER: "Never" };
const ANSWER_STYLE = {
  OK: "border-fg bg-mint text-surface font-bold",
  ASK: "border-fg bg-sand text-surface font-bold",
  NEVER: "border-fg bg-ember text-surface font-bold",
};

function preset(kind, groups, uses, defaults) {
  if (kind === "balanced") return structuredClone(defaults);
  const out = {};
  for (const g of groups) {
    out[g.id] = {};
    for (const u of uses) {
      if (kind === "strict") out[g.id][u.id] = u.id === "service" ? (g.id === "basic" ? "OK" : "ASK") : "NEVER";
      else out[g.id][u.id] = u.id === "service" || u.id === "analytics" ? "OK" : u.id === "sharing" ? "NEVER" : "ASK";
    }
  }
  return out;
}

export function PreferenceGrid({ meta, value, onChange, fallback = "ASK", presets = true }) {
  const set = (g, u) => {
    const next = ANSWERS[(ANSWERS.indexOf(value[g]?.[u] || fallback) + 1) % ANSWERS.length];
    onChange({ ...value, [g]: { ...value[g], [u]: next } });
  };
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {presets && <span className="text-[13px] text-muted">Start from</span>}
        {presets && [["balanced", "Balanced (recommended)"], ["strict", "Strict"], ["relaxed", "Relaxed"]].map(([k, l]) => (
          <Button key={k} size="sm" variant="quiet" type="button" onClick={() => onChange(preset(k, meta.groups, meta.uses, meta.defaults))}>{l}</Button>
        ))}
        <span className="ml-auto text-[12.5px] text-muted">Tap an answer to change it</span>
      </div>
      <div className="scroll-thin overflow-x-auto border-2 border-fg">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead>
            <tr className="bg-raised/40">
              <th className="w-[190px] px-4 py-3 text-left font-normal text-muted">Your…</th>
              {meta.uses.map((u) => <th key={u.id} className="px-2 py-3 text-left font-normal leading-snug text-fg2">{u.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {meta.groups.map((g) => (
              <tr key={g.id} className="border-t border-line">
                <td className="px-4 py-2.5 text-fg">{g.label}</td>
                {meta.uses.map((u) => {
                  const a = value[g.id]?.[u.id] || fallback;
                  return (
                    <td key={u.id} className="px-2 py-2">
                      <button type="button" onClick={() => set(g.id, u.id)} aria-label={`${g.label}, ${u.label}: ${ANSWER_LABEL[a]}`}
                        className={cx("h-8 w-[88px] border text-[12.5px] transition-colors", ANSWER_STYLE[a])}>
                        {ANSWER_LABEL[a]}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[12.5px] text-muted">
        <span className="text-mint">OK</span> lets it happen · <span className="text-sand">Ask me</span> means Kavach checks with you first ·{" "}
        <span className="text-ember">Never</span> blocks it and warns you on sites that do it.
      </p>
    </div>
  );
}

function CopyBox({ text }) {
  const [done, setDone] = useState(false);
  return (
    <div className="flex items-center gap-2 border-2 border-fg bg-raised/50 px-3 py-2">
      <code className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-fg">{text}</code>
      <button type="button" className="flex items-center gap-1 text-[12px] text-fg2 hover:text-fg"
        onClick={() => { navigator.clipboard?.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); }}>
        {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{done ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
export { CopyBox };

const STEPS = ["What you're OK with", "Apps you use", "Stay protected"];

export default function Onboarding() {
  const { refresh, user } = useAuth();
  const [meta, setMeta] = useState(null);
  const [choices, setChoices] = useState(null);
  const [services, setServices] = useState(["google", "whatsapp", "instagram"]);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    get("/onboarding").then((m) => { setMeta(m); setChoices(structuredClone(m.current || m.defaults)); }).catch(setError);
  }, []);

  const finish = async (skip = false) => {
    setBusy(true);
    setError(null);
    try {
      await post("/onboarding", skip ? { skip: true } : { choices, services });
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dotgrid min-h-full">
      <div className="mx-auto max-w-[1040px] px-4 pb-20 pt-8 sm:px-6">
        <div className="flex items-center justify-between">
          <span className="wordmark text-[13px]">KAVACH</span>
          <button onClick={() => finish(true)} className="text-[13px] text-muted underline decoration-line-strong underline-offset-4 hover:text-fg">Skip for now</button>
        </div>

        <div className="rise mt-12">
          <div className="label text-dim">Welcome{user?.email ? `, ${user.email}` : ""}</div>
          <h1 className="h-display mt-4 text-[clamp(34px,5vw,56px)]">Let's set up your protection.</h1>
          <p className="mt-3 max-w-2xl text-[15px] text-muted">Three quick steps. You can change any of this later from <span className="text-fg2">Your rules</span>.</p>
        </div>

        <ol className="mt-10 grid grid-cols-3 gap-px overflow-hidden border-2 border-fg hairgrid">
          {STEPS.map((s, i) => (
            <li key={s} className={cx("bg-surface px-4 py-3 text-[13px]", i === step ? "text-fg" : "text-dim")}>
              <span className="mr-2 font-mono text-[11px]">{String(i + 1).padStart(2, "0")}</span>{s}
            </li>
          ))}
        </ol>

        <div className="card rise mt-6 p-6 sm:p-8">
          {!meta || !choices ? <Spinner /> : step === 0 ? (
            <>
              <h2 className="text-[22px] tracking-[-0.03em]">What are you OK with companies doing with your data?</h2>
              <p className="mb-6 mt-1 text-[14px] text-muted">Kavach compares every site's privacy policy with these answers and enforces them for your AI agents.</p>
              <PreferenceGrid meta={meta} value={choices} onChange={setChoices} />
            </>
          ) : step === 1 ? (
            <>
              <h2 className="text-[22px] tracking-[-0.03em]">Which of these do you use?</h2>
              <p className="mb-6 mt-1 text-[14px] text-muted">Kavach will fetch their privacy policies, check them against your answers and keep watching for changes.</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {meta.services.map((s) => {
                  const on = services.includes(s.id);
                  return (
                    <button key={s.id} type="button" onClick={() => setServices(on ? services.filter((x) => x !== s.id) : [...services, s.id])}
                      className={cx("flex items-center justify-between border px-3 py-2.5 text-left transition-colors",
                        on ? "border-fg2 bg-raised text-fg" : "border-line text-fg2 hover:border-line-strong")}>
                      <span><span className="block text-[14px]">{s.name}</span><span className="font-mono text-[11px] text-dim">{s.domain}</span></span>
                      <span className={cx("flex h-5 w-5 items-center justify-center border", on ? "border-mint bg-mint text-surface" : "border-line-strong")}>
                        {on && <Check className="h-3.5 w-3.5" />}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="mt-4 text-[12.5px] text-muted">{services.length} selected · fetched in the background, so you can carry on.</p>
            </>
          ) : (
            <>
              <h2 className="text-[22px] tracking-[-0.03em]">Stay protected without doing anything</h2>
              <p className="mb-6 mt-1 text-[14px] text-muted">From here on, Kavach works on its own.</p>
              <div className="grid gap-5 md:grid-cols-2">
                <div className="border-2 border-fg bg-surface p-5 text-line-strong">
                  <div className="label text-gold/90">Watchman</div>
                  <p className="mt-2 text-[14px] text-fg2">Every policy you track is re-checked automatically. Update emails that reach Kavach’s own monitoring inbox are used too, so changes on sites that block bots are still caught.</p>
                </div>
                <div className="border-2 border-fg bg-surface p-5 text-line-strong">
                  <div className="label text-gold/90">Browser extension (optional)</div>
                  <p className="mt-2 text-[14px] text-fg2">Reviews any privacy policy or terms page as you read it. Load the <span className="font-mono text-fg">extension</span> folder in Chrome; it signs in by itself while you’re signed in here.</p>
                </div>
              </div>
            </>
          )}
          <div className="mt-8"><ErrorNote error={error} /></div>
          <div className="flex items-center justify-between">
            <Button variant="ghost" icon={ArrowLeft} disabled={step === 0} onClick={() => setStep(step - 1)}>Back</Button>
            {step < 2
              ? <Button variant="primary" trailing={ArrowRight} onClick={() => setStep(step + 1)} disabled={!meta}>Continue</Button>
              : <Button variant="primary" loading={busy} trailing={ArrowRight} onClick={() => finish(false)}>Finish and open dashboard</Button>}
          </div>
        </div>
      </div>
    </div>
  );
}

export function PreferencesButton() {
  const [open, setOpen] = useState(false);
  const [meta, setMeta] = useState(null);
  const [choices, setChoices] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const show = async () => {
    setOpen(true);
    setSaved(false);
    const m = await get("/onboarding");
    setMeta(m);
    setChoices(structuredClone(m.current || m.defaults));
  };
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await post("/onboarding", { choices, services: [] });
      setSaved(true);
      setOpen(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button variant="primary" onClick={show}>{saved ? "Preferences saved" : "Edit my preferences"}</Button>
      {open && (
        <Modal eyebrow="Your preferences" title="What are you OK with?" onClose={() => setOpen(false)} wide>
          {!meta ? <Spinner /> : <PreferenceGrid meta={meta} value={choices} onChange={setChoices} />}
          <div className="mt-5"><ErrorNote error={error} /></div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={save}>Save preferences</Button>
          </div>
        </Modal>
      )}
    </>
  );
}
