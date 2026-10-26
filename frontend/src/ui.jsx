import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, X, XCircle } from "lucide-react";
import { useState } from "react";

export const cx = (...c) => c.filter(Boolean).join(" ");

export function Card({ title, subtitle, action, children, className, pad = true }) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-[28px] font-semibold leading-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-[14px] text-slate-500">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

const BTN = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 border-indigo-600",
  secondary: "bg-white text-slate-700 hover:bg-slate-50 border-slate-300",
  danger: "bg-red-600 text-white hover:bg-red-700 border-red-600",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100 border-transparent",
  success: "bg-emerald-600 text-white hover:bg-emerald-700 border-emerald-600",
};

export function Button({ variant = "secondary", size = "md", loading, icon: Icon, children, className, ...props }) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3.5 py-2 text-[13px]",
        BTN[variant], className,
      )}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : Icon && <Icon className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

const TONES = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  blue: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  gray: "bg-slate-100 text-slate-600 ring-slate-200",
  purple: "bg-violet-50 text-violet-700 ring-violet-200",
};

export function Badge({ tone = "gray", children, className }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-medium ring-1 ring-inset", TONES[tone], className)}>{children}</span>;
}

const DECISION = {
  ALLOW: ["green", CheckCircle2], BLOCK: ["red", XCircle], REVIEW: ["amber", CircleHelp],
  PASS: ["green", CheckCircle2], FAIL: ["red", XCircle], ABSTAIN: ["amber", CircleHelp],
};

export function Decision({ value, className }) {
  if (!value) return <Badge>—</Badge>;
  const [tone, Icon] = DECISION[value] || ["gray", CircleHelp];
  return <Badge tone={tone} className={className}><Icon className="h-3 w-3" />{value}</Badge>;
}

export const RISK_TONE = { high: "red", medium: "amber", low: "blue", none: "green", unknown: "gray" };
export const CLASS_TONE = { FORMATTING_ONLY: "green", WORDING_NO_MATERIAL_CHANGE: "blue", AMBIGUOUS: "amber", POTENTIALLY_MATERIAL: "red" };

export function Stat({ label, value, hint, tone, icon: Icon }) {
  const color = { red: "text-red-600", green: "text-emerald-600", amber: "text-amber-600", blue: "text-indigo-600" }[tone] || "text-slate-900";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between text-[12.5px] text-slate-500">
        {label}
        {Icon && <Icon className="h-4 w-4 text-slate-400" />}
      </div>
      <div className={cx("mt-1 text-[26px] font-semibold tabular-nums", color)}>{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-slate-400">{hint}</div>}
    </div>
  );
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 px-6 py-10 text-center">
      {Icon && <Icon className="mb-2 h-6 w-6 text-slate-400" />}
      <div className="text-[14px] font-medium text-slate-700">{title}</div>
      {children && <div className="mt-1 max-w-md text-[13px] text-slate-500">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{error.code ? <b className="mr-1 font-semibold">{error.code}</b> : null}{error.message}</span>
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return <div className="flex items-center gap-2 py-8 text-[13px] text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />{label}…</div>;
}

export function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onMouseDown={onClose}>
      <div className={cx("max-h-[90vh] w-full overflow-auto rounded-xl bg-white shadow-xl scroll-thin", wide ? "max-w-3xl" : "max-w-md")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12.5px] font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-slate-400">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-[13px] outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100";

export function Chips({ options, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button type="button" key={o} onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}
            className={cx("rounded-md border px-2 py-1 text-[12px] transition", on ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300")}>
            {o.replaceAll("_", " ")}
          </button>
        );
      })}
    </div>
  );
}

export function Json({ value }) {
  return <pre className="max-h-80 overflow-auto rounded-lg bg-slate-900 p-3 text-[11.5px] leading-relaxed text-slate-100 scroll-thin">{JSON.stringify(value, null, 2)}</pre>;
}

export function Collapse({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="text-[12.5px] font-medium text-indigo-600 hover:underline">{open ? "Hide" : "Show"} {label}</button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

export const fmtTime = (t) => (t ? new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—");
export const label = (s) => (s || "").replaceAll("_", " ");

export const CATEGORIES = ["location", "contacts", "biometrics", "email", "name", "phone", "health", "financial", "government_id", "browsing_history", "device_id", "photos", "messages", "preferences"];
export const PURPOSES = ["service_delivery", "navigation", "account_management", "advertising", "marketing", "analytics", "personalization", "ai_training", "research", "third_party_sharing", "legal_compliance", "security"];
export const ACTIONS = ["transfer_data", "accept_terms", "submit_form", "create_account", "send_message"];
export const POLICY_CATEGORIES = ["location", "contacts", "biometrics", "third_party_sharing", "retention", "deletion", "advertising", "ai_training"];
