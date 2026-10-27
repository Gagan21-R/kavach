import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../state";
import { Button, ErrorNote, Field, KavachMark, inputCls } from "../ui";

const STEPS = [
  ["01", "Read", "Type any website. Kavach finds its privacy policy and terms, and six agents review them with the exact sentences as evidence."],
  ["02", "Guard", "Your preferences become rules. Sites and AI agents that go against them are flagged or stopped."],
  ["03", "Watch", "Policies are re-checked on their own. When one changes, Kavach tells you what changed and what it means for you."],
];

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dotgrid min-h-full">
      <header className="mx-auto flex max-w-[1320px] items-center gap-2.5 px-4 pt-6 sm:px-6">
        <span className="flex h-10 w-10 items-center justify-center border-2 border-fg bg-[#05070c]"><KavachMark className="h-7 w-7" /></span>
        <span className="wordmark text-[15px] text-fg">KAVACH</span>
        <span className="label ml-auto hidden text-fg2 sm:block">Explainable signals, not legal advice</span>
      </header>

      <div className="mx-auto grid max-w-[1320px] items-center gap-10 px-4 pb-16 pt-6 sm:px-6 lg:grid-cols-[1.2fr_1fr] lg:gap-16">
        <section className="ink-block relative mx-auto aspect-[1200/1351] w-full max-w-[520px] overflow-hidden">
          {/* The emblem on its own black panel. */}
          <img src="/brand/kavach-lockup.webp" alt="Kavach: a golden shield with a padlock, circled by an orbit" width={1200} height={1351}
            className="rise glow size-full object-contain" />
          <span className="label absolute bottom-3 left-3 bg-yellow px-2 py-1 text-fg">Your consent, guarded</span>
        </section>

        <div className="rise" style={{ animationDelay: "120ms" }}>
          <span className="label inline-flex h-7 items-center border-2 border-gold bg-sky px-2.5 text-gold-deep">Consent intelligence · Hackman X 2026</span>
          <h1 className="h-display mt-5 text-[clamp(2.2rem,4.4vw,3.8rem)]">Nobody reads <span className="marker">the terms.</span></h1>
          <p className="mt-5 max-w-lg border-l-4 border-fg pl-4 text-[16px] leading-relaxed text-fg2">Nobody reads the terms, AI agents don’t either, and the terms change after you agree. Kavach reads them for you and keeps watching.</p>

          <form onSubmit={submit} className="card mt-8 p-7">
            <div className="text-[18px] font-bold uppercase">{mode === "login" ? "Sign in" : "Create account"}</div>
            <div className="mt-6 space-y-5">
              <Field label="Email"><input type="email" required autoComplete="username" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></Field>
              <Field label="Password" hint={mode === "register" ? "At least 12 characters." : undefined}>
                <input type="password" required autoComplete={mode === "login" ? "current-password" : "new-password"} className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
            </div>
            <div className="mt-6"><ErrorNote error={error} /></div>
            <Button variant="primary" size="lg" className="w-full" loading={busy} trailing={ArrowRight}>{mode === "login" ? "Sign in" : "Create account"}</Button>
            <p className="mt-5 text-center text-[13.5px] text-muted">
              {mode === "login" ? "New here? " : "Already have an account? "}
              <button type="button" className="font-bold text-gold underline decoration-2 underline-offset-4" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
                {mode === "login" ? "Create an account" : "Sign in"}
              </button>
            </p>
          </form>
        </div>
      </div>

      <section className="mx-auto grid max-w-[1320px] gap-5 px-4 sm:px-6 md:grid-cols-3">
        {STEPS.map(([n, t, d]) => (
          <div key={n} className="card px-6 py-7">
            <span className="label inline-flex h-7 items-center border-2 border-fg bg-yellow px-2 text-fg">{n}</span>
            <div className="mt-4 text-[1.3rem] font-bold uppercase text-fg">{t}</div>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">{d}</p>
          </div>
        ))}
      </section>
      <div className="h-16" />
    </div>
  );
}
