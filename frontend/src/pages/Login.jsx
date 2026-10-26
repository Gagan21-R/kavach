import { Eye, Gavel, ShieldCheck, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../state";
import { Button, ErrorNote, Field, inputCls } from "../ui";

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
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-slate-900 p-12 text-slate-200 lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600"><ShieldCheck className="h-5 w-5 text-white" /></div>
          <span className="font-serif text-[20px] font-semibold text-white">Kavach</span>
        </div>
        <div>
          <h1 className="font-serif text-[40px] font-semibold leading-tight text-white">Consent was designed for humans who read.</h1>
          <p className="mt-4 max-w-md text-[15px] text-slate-400">Now neither humans nor AI agents read, and policies change after you agree. Kavach reads, argues over, guards and keeps watching every “I agree”.</p>
          <div className="mt-10 grid max-w-lg gap-4">
            {[[Gavel, "The Trial", "Six agents argue each clause, cite every sentence, and an independent auditor checks the verdict."],
              [ShieldAlert, "The Trap", "Hidden instructions aimed at AI agents are caught before an agent clicks Accept."],
              [Eye, "The Watch", "Policy changes are diffed; your earlier approval stops covering materially new wording."]].map(([Icon, t, d]) => (
              <div key={t} className="flex gap-3">
                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-indigo-400" />
                <div><div className="text-[14px] font-medium text-white">{t}</div><div className="text-[13px] text-slate-400">{d}</div></div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-[12px] text-slate-500">Hackman X 2026 · Explainable signals, not legal advice.</p>
      </div>
      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5">
          <div>
            <h2 className="font-serif text-[26px] font-semibold text-slate-900">{mode === "login" ? "Sign in" : "Create your account"}</h2>
            <p className="mt-1 text-[13px] text-slate-500">{mode === "login" ? "Welcome back." : "Your rules, policies and history stay private to your account."}</p>
          </div>
          <Field label="Email"><input type="email" required autoComplete="username" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></Field>
          <Field label="Password" hint={mode === "register" ? "At least 12 characters." : undefined}>
            <input type="password" required autoComplete={mode === "login" ? "current-password" : "new-password"} className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <ErrorNote error={error} />
          <Button variant="primary" className="w-full" loading={busy}>{mode === "login" ? "Sign in" : "Create account"}</Button>
          <p className="text-center text-[13px] text-slate-500">
            {mode === "login" ? "New here? " : "Already have an account? "}
            <button type="button" className="font-medium text-indigo-600 hover:underline" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
