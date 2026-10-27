import { Inbox as InboxIcon, Mail, Send, Upload, Wand2 } from "lucide-react";
import { useRef, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Button, Card, Chip, Empty, ErrorNote, Spinner, cx, fmtTime, inputCls } from "../ui";

const DOT = { CHANGED: "bg-ember", NO_CHANGE: "bg-mint", UNKNOWN: "bg-sand" };

/**
 * Kavach's monitoring inbox: one mailbox Kavach owns is signed up to the services, and update emails that reach it
 * are read automatically. For the demo, an email can be delivered here by hand.
 */
export default function MonitoringInbox({ onDelivered }) {
  const inbox = useLoad(() => get("/inbox"));
  const file = useRef(null);
  const [policyId, setPolicyId] = useState("");
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);
  const d = inbox.data;
  const chosen = policyId || d?.tracked?.[0]?.id || "";

  const write = async () => {
    setBusy("sample"); setError(null); setNote(null);
    try { setRaw((await get(`/inbox/sample?policy_id=${chosen}`)).raw); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const deliver = async (text) => {
    setBusy("send"); setError(null); setNote(null);
    try {
      const r = await post("/inbox/upload", { raw: text });
      setNote(r.message || `Delivered: “${r.subject}”.`);
      await inbox.reload();
      onDelivered?.();
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const onFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) { const text = await f.text(); setRaw(text); deliver(text); }
  };

  return (
    <div data-reveal>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label flex items-center gap-2 text-gold/90"><InboxIcon className="h-3.5 w-3.5" />Monitoring inbox</div>
          <h3 className="h-display mt-3 text-[clamp(1.2rem,2.2vw,1.7rem)]">When a site won’t let us read it, its emails will.</h3>
        </div>
      </div>
      <div className="grid gap-5 xl:grid-cols-[1fr_1.3fr]">
        <Card title="Kavach’s inbox" meta={d ? (d.mailbox.connected ? `Read automatically every ${Math.round(d.mailbox.every_minutes / 60)} h` : "Not connected on this server yet") : undefined}>
          {!d ? <Spinner /> : (
            <>
              <div className="border-2 border-fg bg-surface flex items-center gap-3 px-4 py-3 text-line-strong">
                <Mail className="h-4 w-4 text-gold" />
                <span className="font-mono text-[13px] text-fg">{d.mailbox.address}</span>
                <span className={cx("ml-auto h-2 w-2 rounded-full", d.mailbox.connected ? "bg-mint live-dot" : "bg-dim")} />
              </div>
              <p className="mt-4 text-[14px] leading-relaxed text-fg2">
                One mailbox that Kavach owns is signed up to the services you track. When a service emails “we’re updating our terms”, Kavach re-checks the site; if the site still shows the old version or blocks bots, it builds the new version from the email. You don’t forward anything.
              </p>
              {!d.mailbox.connected && (
                <p className="mt-3 text-[12.5px] text-muted">To connect a Gmail account: turn on 2-step verification, create an app password, and set <span className="font-mono text-fg2">CC_IMAP_HOST=imap.gmail.com</span>, <span className="font-mono text-fg2">CC_IMAP_USER</span> and <span className="font-mono text-fg2">CC_IMAP_PASSWORD</span>.</p>
              )}
            </>
          )}
        </Card>

        <Card title="Deliver an email (demo)" meta="Processed exactly as if it had arrived in Kavach’s inbox">
          {!d ? <Spinner /> : !d.tracked.length ? (
            <Empty icon={Mail} title="Track a website first">The demo email is written for one of your tracked policies.</Empty>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                <select className={cx(inputCls, "w-auto min-w-[220px] flex-1")} value={chosen} onChange={(e) => setPolicyId(e.target.value)}>
                  {d.tracked.map((p) => <option key={p.id} value={p.id} className="bg-bg">{p.name}</option>)}
                </select>
                <Button icon={Wand2} loading={busy === "sample"} onClick={write}>Write a sample update</Button>
                <Button icon={Upload} onClick={() => file.current?.click()}>Upload .eml</Button>
                <input ref={file} type="file" accept=".eml,message/rfc822,text/plain" className="hidden" onChange={onFile} />
              </div>
              <textarea rows={9} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="The email appears here. You can edit it before delivering."
                className={cx(inputCls, "mt-3 font-mono text-[12px] leading-relaxed")} />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button variant="primary" icon={Send} loading={busy === "send"} disabled={raw.trim().length < 10} onClick={() => deliver(raw)}>Deliver to inbox</Button>
                {note && <span className="fade text-[13px] text-mint">{note}</span>}
              </div>
            </>
          )}
          <div className="mt-3"><ErrorNote error={error} /></div>
        </Card>
      </div>

      {d?.signals?.length > 0 && (
        <Card className="mt-5" title="Update emails received" meta="Only the sender, subject, announced changes and policy links are kept" pad={false}>
          <div className="mt-3 border-t border-line">
            {d.signals.map((s) => (
              <div key={s.id} className="border-b border-line px-6 py-4 last:border-b-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[15px] text-fg">{s.subject || "(no subject)"}</div>
                    <div className="font-mono text-[11px] text-dim">{s.service_name} · {s.from_address} · {fmtTime(s.received_at)}</div>
                  </div>
                  <Chip tone={s.authenticated ? "mint" : "muted"} dot={false}>{s.authenticated ? "Verified sender" : "Sender not verified"}</Chip>
                </div>
                <ul className="mt-2 space-y-1 text-[13.5px]">
                  {s.actions.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-fg2"><span className={cx("mt-2 h-1.5 w-1.5 shrink-0 rounded-full", DOT[a.status] || "bg-fg2")} />{a.detail}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
