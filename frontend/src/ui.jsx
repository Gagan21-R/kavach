import { ArrowUpRight, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export const cx = (...c) => c.filter(Boolean).join(" ");

// ---------- type & structure ----------

export function Eyebrow({ index, children, className }) {
  return (
    <div className={cx("flex items-center gap-2", className)}>
      {index != null && <span className="label inline-flex h-7 items-center border-2 border-fg bg-yellow px-2 text-fg">{String(index).padStart(2, "0")}</span>}
      <span className="label inline-flex h-7 items-center border-2 border-gold bg-sky px-2.5 text-gold-deep">{children}</span>
    </div>
  );
}

/** The Kavach mark: shield, padlock and orbit, drawn from the emblem so it stays crisp at any size. */
export function KavachMark({ className = "h-7 w-7", plate = false }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="kv-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f7dc9a" /><stop offset="1" stopColor="#c38d35" />
        </linearGradient>
      </defs>
      {plate && <rect width="64" height="64" rx="14" fill="#05070c" />}
      <path d="M32 7 51 13.5V30Q51 47 32 57 13 47 13 30V13.5Z" fill="#14110b" />
      <path d="M32 7 51 13.5V30Q51 47 32 57Z" fill="#473618" />
      <path d="M32 7 51 13.5V30Q51 47 32 57 13 47 13 30V13.5Z" fill="none" stroke="url(#kv-gold)" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M27 29.5V26a5 5 0 0 1 10 0v3.5" fill="none" stroke="url(#kv-gold)" strokeWidth="2.5" />
      <rect x="24" y="29" width="16" height="13" rx="2.6" fill="url(#kv-gold)" />
      <circle cx="32" cy="34.3" r="1.7" fill="#05070c" />
      <path d="M31.2 35h1.6l.4 4h-2.4z" fill="#05070c" />
      <ellipse cx="32" cy="34" rx="27" ry="8.5" transform="rotate(-16 32 34)" fill="none" stroke="url(#kv-gold)" strokeWidth="1.4" />
      <circle cx="6" cy="41.4" r="2.6" fill="url(#kv-gold)" />
      <circle cx="15.3" cy="45" r="2" fill="url(#kv-gold)" />
      <circle cx="55.6" cy="24.2" r="2.6" fill="url(#kv-gold)" />
    </svg>
  );
}

export function PageHeader({ index, eyebrow, title, subtitle, children }) {
  return (
    <header data-reveal className="mb-10 flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-3xl">
        <Eyebrow index={index}>{eyebrow}</Eyebrow>
        <h2 className="h-page mt-4">{title}</h2>
        {subtitle && <p className="mt-4 max-w-2xl border-l-4 border-fg pl-4 text-[16px] leading-relaxed text-fg2">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

export function Card({ title, meta, action, children, className, pad = true, ...rest }) {
  return (
    <section className={cx("card", className)} {...rest}>
      {(title || action || meta) && (
        <header className="flex items-start justify-between gap-4 px-6 pt-5">
          <div className="min-w-0">
            {title && <h3 className="text-[16px] font-bold uppercase tracking-[-0.01em] text-fg">{title}</h3>}
            {meta && <p className="mt-1 text-[13px] text-muted">{meta}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? "p-6" : ""}>{children}</div>
    </section>
  );
}

export function Divider({ label }) {
  return (
    <div className="my-10 flex items-center gap-4">
      <span className="label text-dim">{label || "* * *"}</span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

// ---------- controls ----------

const BTN = {
  primary: "bg-yellow text-fg border-fg shadow-[3px_3px_0_#0b0b0b] hover:-translate-x-px hover:-translate-y-px hover:shadow-[4px_4px_0_#0b0b0b] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
  secondary: "bg-surface text-fg border-fg shadow-[3px_3px_0_#0b0b0b] hover:-translate-x-px hover:-translate-y-px hover:shadow-[4px_4px_0_#0b0b0b] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
  ghost: "bg-transparent text-fg2 border-transparent hover:text-fg hover:border-fg",
  danger: "bg-ember text-surface border-fg shadow-[3px_3px_0_#0b0b0b] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
  quiet: "bg-raised text-fg border-fg hover:bg-yellow",
};

export function Button({ variant = "secondary", size = "md", loading, icon: Icon, trailing: Trailing, children, className, ...props }) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx(
        "inline-flex select-none items-center justify-center gap-2 rounded-none border-2 font-mono font-bold uppercase tracking-[0.04em] transition-[transform,box-shadow,background-color,color] duration-100 disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none",
        size === "sm" ? "h-8 px-3 text-[10.5px]" : size === "lg" ? "h-12 px-6 text-[12px]" : "h-10 px-4 text-[11px]",
        BTN[variant], className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon && <Icon className="h-4 w-4" strokeWidth={1.6} />}
      {children}
      {Trailing && <Trailing className="h-4 w-4" strokeWidth={1.6} />}
    </button>
  );
}

const TONE = {
  mint: { dot: "bg-mint", text: "text-mint", border: "border-mint bg-mint/10" },
  ember: { dot: "bg-ember", text: "text-ember", border: "border-ember bg-ember/10" },
  sand: { dot: "bg-sand", text: "text-sand", border: "border-sand bg-sand/10" },
  fg: { dot: "bg-fg", text: "text-fg", border: "border-fg bg-surface" },
  muted: { dot: "bg-muted", text: "text-fg2", border: "border-fg2 bg-raised" },
};

export function Chip({ tone = "muted", dot = true, live, children, className }) {
  const t = TONE[tone] || TONE.muted;
  return (
    <span className={cx("inline-flex h-6 max-w-full items-center gap-1.5 whitespace-nowrap rounded-none border-[1.5px] px-2 font-mono text-[10.5px] font-bold uppercase tracking-[0.04em]", t.border, t.text, className)}>
      {dot && <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", t.dot, live && "live-dot")} />}
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}

export const DECISION_TONE = { ALLOW: "mint", PASS: "mint", BLOCK: "ember", FAIL: "ember", REVIEW: "sand", ABSTAIN: "sand" };
export function Decision({ value, className }) {
  if (!value) return <span className="font-mono text-[11px] text-dim">—</span>;
  return <Chip tone={DECISION_TONE[value] || "muted"} className={className}>{value}</Chip>;
}

export const RISK_TONE = { high: "ember", medium: "sand", low: "fg", none: "mint", unknown: "muted" };
export const CLASS_TONE = { FORMATTING_ONLY: "mint", WORDING_NO_MATERIAL_CHANGE: "fg", AMBIGUOUS: "sand", POTENTIALLY_MATERIAL: "ember" };

export function Toggle({ options, value, onChange }) {
  return (
    <div className="inline-flex border-2 border-fg p-0.5">
      {options.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={cx("h-7 px-3 font-mono text-[11px] uppercase transition-colors", value === v ? "bg-fg text-surface" : "text-fg2 hover:text-fg")}>
          {l}
        </button>
      ))}
    </div>
  );
}

// ---------- data display ----------

export function KpiGrid({ items, cols = 2, className }) {
  return (
    <div className={cx("card hairgrid grid gap-px overflow-hidden", cols === 3 ? "grid-cols-2 sm:grid-cols-3" : cols === 4 ? "grid-cols-2 lg:grid-cols-4" : "grid-cols-2", className)}>
      {items.map((k) => (
        <div key={k.label} className="bg-surface p-5">
          <div className="label">{k.label}</div>
          <div className={cx("num mt-3 text-[36px] leading-none", k.tone === "ember" ? "text-ember" : k.tone === "mint" ? "text-mint" : k.tone === "sand" ? "text-sand" : "text-fg")}>
            {k.value}{k.unit && <span className="ml-1 text-[15px] tracking-normal text-muted">{k.unit}</span>}
          </div>
          {k.hint && <div className="mt-2 text-[13px] text-muted">{k.hint}</div>}
        </div>
      ))}
    </div>
  );
}

export function Ring({ value, max = 100, size = 112, label, sub, tone = "mint" }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, (value ?? 0) / max));
  const color = tone === "ember" ? "#d22f2f" : tone === "sand" ? "#b8650a" : tone === "gold" ? "#2b3af0" : "#138a4b";
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#d8d1bf" strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6"
          strokeLinecap="butt" strokeDasharray={c} strokeDashoffset={c * (1 - pct)} style={{ transition: "stroke-dashoffset 900ms cubic-bezier(.2,.7,.2,1)" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-[28px] leading-none">{label ?? value}</span>
        {sub && <span className="mt-1 font-mono text-[9.5px] uppercase text-muted">{sub}</span>}
      </div>
    </div>
  );
}

export function Bar({ value, max = 100, tone = "mint" }) {
  const color = tone === "ember" ? "bg-ember" : tone === "sand" ? "bg-sand" : tone === "fg" ? "bg-fg2" : "bg-mint";
  return (
    <div className="h-[3px] w-full bg-line">
      <div className={cx("h-[3px]", color)} style={{ width: `${Math.max(0, Math.min(100, (value / max) * 100))}%`, transition: "width 700ms cubic-bezier(.2,.7,.2,1)" }} />
    </div>
  );
}

export function ListRow({ title, meta, right, onClick, active, href }) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp onClick={onClick} className={cx("group flex w-full items-center gap-6 border-b border-line py-5 text-left transition-colors last:border-0",
      onClick && "cursor-pointer")}>
      <div className="min-w-0 flex-1">
        <div className={cx("truncate text-[22px] tracking-[-0.03em] transition-colors", active ? "text-fg" : "text-muted group-hover:text-fg")}>{title}</div>
        {meta && <div className="mt-1 truncate text-[13px] text-muted">{meta}</div>}
      </div>
      {right}
      {(onClick || href) && <ArrowUpRight className={cx("h-5 w-5 shrink-0 transition-colors", active ? "text-gold" : "text-dim group-hover:text-gold")} strokeWidth={1.5} />}
    </Comp>
  );
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center border-2 border-dashed border-fg2 px-6 py-12 text-center">
      {Icon && <Icon className="mb-3 h-6 w-6 text-dim" strokeWidth={1.4} />}
      <div className="text-[15px] text-fg">{title}</div>
      {children && <div className="mt-1.5 max-w-md text-[13px] text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <div className="fade mb-4 flex items-start gap-3 border-2 border-ember bg-ember/10 px-4 py-3 text-[13px] text-fg">
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ember" />
      <span>{error.code && <span className="mr-2 font-mono text-[11px] uppercase text-ember">{error.code}</span>}{error.message}</span>
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return <div className="label flex items-center gap-2 py-10 text-muted"><Loader2 className="h-3.5 w-3.5 animate-spin" />{label}</div>;
}

export function Modal({ title, eyebrow, onClose, children, wide }) {
  // Portalled to <body> so it always sits above the sticky header.
  return createPortal(
    <div className="fade fixed inset-0 z-50 flex items-center justify-center bg-[#0b0b0b]/45 p-4" onMouseDown={onClose}>
      <div className={cx("card rise max-h-[90vh] w-full overflow-auto scroll-thin", wide ? "max-w-4xl" : "max-w-md")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b-2 border-fg bg-yellow px-6 py-4">
          <div>
            {eyebrow && <div className="label mb-1 text-fg2">{eyebrow}</div>}
            <h3 className="text-[18px] font-bold uppercase tracking-[-0.01em]">{title}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 text-fg hover:bg-surface hover:bg-raised hover:text-fg" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function Field({ label: text, hint, children }) {
  return (
    <label className="block">
      <span className="label mb-2 block">{text}</span>
      {children}
      {hint && <span className="mt-1.5 block text-[12px] text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-none border-2 border-fg bg-surface px-4 py-3 text-[14.5px] text-fg placeholder:text-dim outline-none transition-shadow focus:shadow-[3px_3px_0_#2b3af0]";

export function Chips({ options, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button type="button" key={o} onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}
            className={cx("h-7 rounded-none border-2 px-2.5 font-mono text-[11px] font-bold uppercase transition-colors",
              on ? "border-fg bg-yellow text-fg" : "border-fg2 text-fg2 hover:border-fg hover:text-fg")}>
            {o.replaceAll("_", " ")}
          </button>
        );
      })}
    </div>
  );
}

export function Json({ value }) {
  return <pre className="max-h-80 overflow-auto border-2 border-fg bg-bg p-4 font-mono text-[11.5px] leading-relaxed text-fg2 scroll-thin">{JSON.stringify(value, null, 2)}</pre>;
}

export function Collapse({ label: text, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="label text-gold underline decoration-2 underline-offset-4 hover:text-fg">{open ? "Hide" : "Show"} {text}</button>
      {open && <div className="fade mt-3">{children}</div>}
    </div>
  );
}

export const fmtTime = (t) => (t ? new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—");
export const fmtClock = (t) => (t ? new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "—");
export const label = (s) => (s || "").replaceAll("_", " ");

export const CATEGORIES = ["location", "contacts", "biometrics", "email", "name", "phone", "health", "financial", "government_id", "browsing_history", "device_id", "photos", "messages", "preferences"];
export const PURPOSES = ["service_delivery", "navigation", "account_management", "advertising", "marketing", "analytics", "personalization", "ai_training", "research", "third_party_sharing", "legal_compliance", "security"];
export const ACTIONS = ["transfer_data", "accept_terms", "submit_form", "create_account", "send_message"];

// Opens the tab that holds a section (or a whole tab) and scrolls to it; the layout does the work.
export function goTo(id, smooth = true) {
  window.dispatchEvent(new CustomEvent("kavach:goto", { detail: { id, smooth } }));
}

/** Adds .is-in to every [data-reveal] inside the returned ref the first time it scrolls into view. */
export function useReveals(key) {
  const ref = useRef(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return undefined;
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
    }), { rootMargin: "0px 0px -8% 0px" });
    const watch = () => root.querySelectorAll("[data-reveal]:not(.is-in)").forEach((el) => io.observe(el));
    watch();
    const mo = new MutationObserver(watch);
    mo.observe(root, { childList: true, subtree: true });
    return () => { mo.disconnect(); io.disconnect(); };
  }, [key]); // re-attach when the keyed root is replaced (e.g. a tab switch)
  return ref;
}

/** "QUICK ACTIONS"-style heading: a yellow tile with an icon, then a bold uppercase title. */
export function SectionTitle({ icon: Icon, children, action }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        {Icon && <span className="flex h-9 w-9 items-center justify-center border-2 border-fg bg-yellow"><Icon className="h-4 w-4" strokeWidth={2} /></span>}
        <h3 className="text-[17px] font-bold uppercase tracking-[-0.01em] text-fg">{children}</h3>
      </div>
      {action}
    </div>
  );
}
