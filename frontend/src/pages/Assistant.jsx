import { Lock, MessageCircle, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { post } from "../api";
import { Badge, Button, Card, PageHeader, cx, inputCls } from "../ui";

const SUGGESTIONS = [
  "How does Consent Court work?",
  "Why was my agent blocked?",
  "What does the Sentinel do?",
  "Which tokens are active?",
  "What changed in my policies?",
  "How is the risk score calculated?",
  "How confident is the analysis?",
  "Where did my data go?",
  "Revoke all my tokens",
];

export default function Assistant() {
  const [msgs, setMsgs] = useState([{ from: "bot", text: "I explain how Consent Court works and what happened on your account. I'm read-only: I can't approve, revoke, change rules or send anything.", intent: "intro" }]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

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
    <>
      <PageHeader title="Assistant" subtitle="Explains the system and your own records, with references. It reads only your data and has no write access." />
      <Card pad={false}>
        <div className="flex h-[560px] flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto p-5 scroll-thin">
            {msgs.map((m, i) => (
              <div key={i} className={cx("rise flex", m.from === "me" && "justify-end")}>
                <div className={cx("max-w-[75%] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed", m.from === "me" ? "bg-indigo-600 text-white" : "border border-slate-200 bg-white text-slate-700")}>
                  <div className="whitespace-pre-wrap">{m.text}</div>
                  {m.intent === "refused_action" && <div className="mt-1.5"><Badge tone="amber"><Lock className="h-3 w-3" />read-only</Badge></div>}
                  {m.refs?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{m.refs.map((r) => <Badge key={r.id}>{r.type}: {r.label}</Badge>)}</div>}
                </div>
              </div>
            ))}
            {busy && <div className="text-[12px] text-slate-400">Thinking…</div>}
            <div ref={end} />
          </div>
          <div className="border-t border-slate-100 p-4">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-full border border-slate-200 px-3 py-1 text-[12px] text-slate-600 hover:border-indigo-300 hover:text-indigo-700">{s}</button>)}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex gap-2">
              <input className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about a verdict, a block, a token…" />
              <Button variant="primary" icon={Send} loading={busy}>Ask</Button>
            </form>
          </div>
        </div>
      </Card>
      <p className="mt-3 flex items-center gap-1.5 text-[12px] text-slate-400"><MessageCircle className="h-3.5 w-3.5" />Offline mode: answers come from deterministic retrieval over product docs and your records, not from a language model.</p>
    </>
  );
}
