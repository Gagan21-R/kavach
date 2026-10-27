import { ArrowUp, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { post } from "./api";
import { cx } from "./ui";

export const SUGGESTIONS = [
  "How does Kavach work?",
  "Why was my agent blocked?",
  "What does the Sentinel do?",
  "Which tokens are active?",
  "What changed in my policies?",
  "How is the risk score calculated?",
  "How confident is the analysis?",
  "Where did my data go?",
  "Revoke all my tokens",
];

// Read-only explainer chat, used both in the drawer and on the full Assistant page.
export default function AssistantPanel({ compact }) {
  const [msgs, setMsgs] = useState([{ from: "bot", text: "I explain how Kavach works and what happened on your account. I'm read-only: I can't approve, revoke, change rules or send anything.", intent: "intro" }]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const ask = async (q) => {
    const message = (q ?? text).trim();
    if (!message) return;
    setText("");
    setMsgs((m) => [...m, { from: "me", text: message }]);
    setBusy(true);
    try {
      const r = await post("/chat/explain", { message });
      setMsgs((m) => [...m, { from: "bot", text: r.answer, intent: r.intent, refs: r.references }]);
    } catch (e) {
      setMsgs((m) => [...m, { from: "bot", text: e.message, intent: "error" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6 scroll-thin">
        {msgs.map((m, i) => (
          <div key={i} className="rise">
            <div className="label mb-1.5 flex items-center gap-2 text-muted">
              <span className={cx("h-1.5 w-1.5 rounded-full", m.from === "me" ? "bg-fg2" : "bg-ember")} />
              {m.from === "me" ? "You" : "Kavach"}
              {m.intent === "refused_action" && <span className="ml-1 inline-flex items-center gap-1 text-sand"><Lock className="h-3 w-3" />read-only</span>}
            </div>
            <div className={cx("whitespace-pre-wrap text-[14px] leading-relaxed", m.from === "me" ? "text-fg" : "text-fg2")}>{m.text}</div>
            {m.refs?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {m.refs.map((r) => <span key={r.id} className=" border-2 border-fg px-1.5 py-0.5 font-mono text-[10.5px] uppercase text-muted">{r.type} · {r.label}</span>)}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="label caret text-muted">Kavach is reading your records</div>}
        <div ref={end} />
      </div>
      <div className="border-t border-line px-6 py-4">
        <div className={cx("mb-3 flex gap-1.5", compact ? "overflow-x-auto pb-1 scroll-thin" : "flex-wrap")}>
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} className="h-7 shrink-0 border-2 border-fg px-2.5 text-[12px] text-fg2 transition-colors hover:border-fg2 hover:text-fg">{s}</button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex items-center gap-2 border-2 border-fg bg-bg pl-3 focus-within:border-fg2">
          <input className="h-11 flex-1 bg-transparent text-[14px] outline-none placeholder:text-dim" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about a verdict, a block, a token…" />
          <button disabled={!text.trim() || busy} className="m-1 flex h-9 w-9 items-center justify-center bg-paper text-surface disabled:opacity-30" aria-label="Ask"><ArrowUp className="h-4 w-4" /></button>
        </form>
        <p className="label mt-3 text-[10.5px] text-dim">Offline mode · deterministic retrieval over docs and your records</p>
      </div>
    </div>
  );
}
