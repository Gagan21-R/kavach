import { Ban, Bot, Check, KeyRound, Plug, Plus, Send, ShieldQuestion, Ticket, X } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useAgent, useLoad } from "../state";
import {
  ACTIONS, Button, CATEGORIES, Card, Chip, Chips, Collapse, Decision, Empty, ErrorNote, Field, Json, Modal, PageHeader, PURPOSES, cx, fmtClock, fmtTime, inputCls, label,
} from "../ui";

function tokenStatus(t) {
  if (t.revoked_at) return ["ember", "revoked"];
  if (new Date(t.expires_at) < new Date()) return ["muted", "expired"];
  if (t.use_count >= t.max_uses) return ["muted", "used up"];
  return ["mint", "active"];
}

function Console({ policies, onChange }) {
  const { agent } = useAgent();
  const [req, setReq] = useState({ action: "transfer_data", destination: "maps.example.com", purpose: "navigation", data_categories: ["location"], records: 1, policy_source_id: "" });
  const [token, setToken] = useState(null);
  const [pending, setPending] = useState(null);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(null);
  const [open, setOpen] = useState(null);
  const policyId = req.policy_source_id || policies?.[0]?.id || "";

  const call = async (step, method, path, body, extra = {}) => {
    setBusy(step);
    try {
      const r = await post(path, body, { agentKey: agent.key, allowError: true, ...extra });
      setLog((l) => [{ step, path, status: r.status, data: r.data, at: new Date() }, ...l].slice(0, 14));
      onChange?.();
      return r;
    } finally { setBusy(null); }
  };
  const base = { action: req.action, destination: req.destination, purpose: req.purpose, data_categories: req.data_categories };
  const evaluate = () => call("evaluate", "POST", "/guardian/evaluate", { ...base, policy_source_id: policyId });
  const authorize = async (approval_id) => {
    const r = await call("authorize", "POST", "/guardian/authorize", { ...base, policy_source_id: policyId, ...(approval_id ? { approval_id } : {}) });
    if (r.status === 201) { setToken(r.data.token); setPending(null); }
    if (r.status === 202) setPending(r.data.approval_request_id);
  };
  const execute = () => call("execute", "POST", "/gateway/execute", { ...base, record_count: Number(req.records) || 1, payload: { note: "simulated payload" } }, { consentToken: token || "" });

  if (!agent) return <div className="p-6"><Empty icon={Bot} title="No agent connected">Register an agent below and choose “Use in console”. Its key stays in this tab's memory only.</Empty></div>;
  return (
    <div className="grid lg:grid-cols-[400px_1fr]">
      <div className="space-y-4 border-b border-line p-6 lg:border-b-0 lg:border-r">
        <div className="label flex items-center gap-2 text-fg"><Plug className="h-3.5 w-3.5 text-mint" />Acting as {agent.name}</div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Action"><select className={inputCls} value={req.action} onChange={(e) => setReq({ ...req, action: e.target.value })}>{ACTIONS.map((a) => <option key={a}>{a}</option>)}</select></Field>
          <Field label="Purpose"><select className={inputCls} value={req.purpose} onChange={(e) => setReq({ ...req, purpose: e.target.value })}>{PURPOSES.map((a) => <option key={a}>{a}</option>)}</select></Field>
          <Field label="Destination"><input className={inputCls} value={req.destination} onChange={(e) => setReq({ ...req, destination: e.target.value })} /></Field>
          <Field label="Policy"><select className={inputCls} value={policyId} onChange={(e) => setReq({ ...req, policy_source_id: e.target.value })}>{policies?.map((p) => <option key={p.id} value={p.id}>{p.name} v{p.current_version}</option>)}</select></Field>
        </div>
        <Field label="Data"><Chips options={CATEGORIES} value={req.data_categories} onChange={(v) => setReq({ ...req, data_categories: v })} /></Field>
        <Field label="Records"><input type="number" min="1" className={cx(inputCls, "w-28")} value={req.records} onChange={(e) => setReq({ ...req, records: e.target.value })} /></Field>
        <div className="grid gap-2 border-t border-line pt-4">
          <Button icon={ShieldQuestion} loading={busy === "evaluate"} onClick={evaluate} className="justify-start">01 · Ask the Guardian</Button>
          <Button variant="primary" icon={Ticket} loading={busy === "authorize"} onClick={() => authorize()} className="justify-start">02 · Request a token</Button>
          {pending && <Button icon={Check} onClick={() => authorize(pending)} className="justify-start">02b · Redeem my approval</Button>}
          <Button icon={Send} loading={busy === "execute"} onClick={execute} disabled={!token} className="justify-start">03 · Execute via gateway</Button>
        </div>
        <div className="font-mono text-[11px] uppercase text-dim">{token ? <>Holding {token.slice(0, 14)}… · execute twice to see replay protection</> : "No token held"}</div>
      </div>
      <div className="min-h-[420px] bg-bg/60 p-6 font-mono text-[12px]">
        {log.length === 0 && <span className="text-dim">$ responses from the real API stream here</span>}
        {log.map((l, i) => {
          const d = l.data || {};
          const decision = d.decision || d.error?.decision;
          const msg = d.error?.message || (d.reasons || d.evaluation?.reasons || []).join("; ") || (d.result ? `delivered to ${d.result.delivered_to} · simulated` : "");
          return (
            <div key={l.at.getTime() + i} className={cx("rise border-b border-line py-3 last:border-0", i > 0 && "opacity-70")}>
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-dim">{fmtClock(l.at)}</span>
                <span className="text-fg">POST {l.path}</span>
                <span className={l.status < 300 ? "text-mint" : l.status < 500 ? "text-ember" : "text-sand"}>{l.status}</span>
                {decision && <Decision value={decision} />}
                {d.error?.code && <span className="uppercase text-ember">{d.error.code}</span>}
                <button onClick={() => setOpen(open === i ? null : i)} className="ml-auto uppercase text-dim hover:text-fg">{open === i ? "hide" : "raw"}</button>
              </div>
              {msg && <div className="mt-1.5 pl-[70px] text-fg2">{msg}</div>}
              {d.approval_request_id && <div className="mt-1.5 pl-[70px] text-sand">approval requested · approve below, then redeem</div>}
              {open === i && <div className="mt-3"><Json value={d} /></div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Guardian() {
  const { agent, setAgent } = useAgent();
  const agents = useLoad(() => get("/agents"));
  const tokens = useLoad(() => get("/guardian/tokens"));
  const approvals = useLoad(() => get("/guardian/approvals"));
  const policies = useLoad(() => get("/policies"));
  const [newKey, setNewKey] = useState(null);
  const [name, setName] = useState("my-browser-agent");
  const [error, setError] = useState(null);
  const refresh = () => { tokens.reload(); approvals.reload(); };
  const wrap = (fn) => async (...a) => { setError(null); try { await fn(...a); } catch (e) { setError(e); } };
  const createAgent = wrap(async () => { const r = await post("/agents", { name }); setNewKey(r); agents.reload(); });
  const revokeAgent = wrap(async (id) => { await post(`/agents/${id}/revoke`); if (agent?.id === id) setAgent(null); agents.reload(); tokens.reload(); });
  const revokeToken = wrap(async (id) => { await post("/guardian/revoke", { token_id: id, reason: "revoked from dashboard" }); tokens.reload(); });
  const decide = wrap(async (id, ok) => { await post(`/guardian/approvals/${id}/${ok ? "approve" : "deny"}`); approvals.reload(); });
  const pendingList = approvals.data?.filter((a) => a.status === "PENDING") || [];

  return (
    <>
      <PageHeader index={5} eyebrow="AI agents" title="Your AI agents"
        subtitle="Agents ask Kavach before they share your data, accept terms or sign you up, and Kavach answers from your rules on its own. Here you only decide what your rules leave to you, and see or cancel what agents may do." />
      <ErrorNote error={error} />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Waiting for your decision" meta={pendingList.length ? `${pendingList.length} request${pendingList.length === 1 ? "" : "s"}` : "Requests your rules say you decide"} pad={false}>
          {!pendingList.length ? <div className="p-6"><Empty icon={Check} title="Nothing waiting">When an agent asks for something your rules mark “Ask me”, it appears here.</Empty></div> : (
            <div className="mt-3 border-t border-line">
              {pendingList.map((a) => (
                <div key={a.id} className="flex items-start gap-4 border-b border-line px-6 py-4 last:border-0">
                  <div className="flex-1">
                    <div className="text-[16px] tracking-[-0.02em]">{label(a.action)} → {a.destination}</div>
                    <div className="mt-0.5 font-mono text-[11px] uppercase text-dim">{a.data_categories.join(", ")} · {label(a.purpose)} · until {fmtClock(a.expires_at)}</div>
                    <div className="mt-1.5 text-[13px] text-sand">{a.reason}</div>
                  </div>
                  <Button size="sm" variant="primary" icon={Check} onClick={() => decide(a.id, true)}>Approve</Button>
                  <Button size="sm" icon={X} onClick={() => decide(a.id, false)}>Deny</Button>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Connected agents" pad={false} action={<div className="flex gap-2"><input className={cx(inputCls, "h-8 w-44 py-1 text-[13px]")} value={name} onChange={(e) => setName(e.target.value)} /><Button size="sm" variant="primary" icon={Plus} onClick={createAgent}>Register</Button></div>}>
          {!agents.data?.length ? <div className="p-6"><Empty icon={Bot} title="No agents registered" /></div> : (
            <div className="mt-3 border-t border-line">
              {agents.data.map((a) => (
                <div key={a.id} className="flex items-center gap-4 border-b border-line px-6 py-3.5 last:border-0">
                  <div className="flex-1"><div className="text-[15px]">{a.name}</div><div className="font-mono text-[11px] uppercase text-dim">{fmtTime(a.created_at)}</div></div>
                  {agent?.id === a.id && <Chip tone="mint" live>In simulator</Chip>}
                  {a.active ? <Button size="sm" variant="ghost" icon={Ban} onClick={() => revokeAgent(a.id)}>Revoke</Button> : <Chip tone="ember">Revoked</Chip>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Permissions given to agents" meta="Short-lived, single-purpose. Cancelling stops future use; it can’t recall data already delivered" className="mt-5" pad={false}>
        {!tokens.data?.length ? <div className="p-6"><Empty icon={KeyRound} title="No permissions yet" /></div> : (
          <div className="mt-3 overflow-x-auto border-t border-line scroll-thin">
            <table className="w-full text-[13px]">
              <thead><tr className="border-b border-line text-left">{["Scope", "Uses", "Records", "Expires", "Status", ""].map((h) => <th key={h} className="label px-6 py-3 font-normal text-muted first:pl-6">{h}</th>)}</tr></thead>
              <tbody>{tokens.data.map((t) => {
                const [tone, st] = tokenStatus(t);
                return (
                  <tr key={t.id} className="border-b border-line last:border-0 hover:bg-raised/40">
                    <td className="px-6 py-3.5"><div className="text-fg">{label(t.action)} → {t.destination}</div><div className="font-mono text-[11px] uppercase text-dim">{t.data_categories.join(", ")} · {label(t.purpose)}{t.approval_id ? " · approved by you" : ""}</div></td>
                    <td className="num px-6 font-mono">{t.use_count}/{t.max_uses}</td>
                    <td className="num px-6 font-mono">{t.records_used}/{t.max_records}</td>
                    <td className="px-6 font-mono text-[12px] text-fg2">{fmtTime(t.expires_at)}</td>
                    <td className="px-6"><Chip tone={tone}>{st}</Chip>{t.revocation_reason && <div className="mt-1 font-mono text-[10.5px] text-dim">{t.revocation_reason}</div>}</td>
                    <td className="px-6 text-right">{st === "active" && <Button size="sm" onClick={() => revokeToken(t.id)}>Revoke</Button>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="mt-5">
        <Collapse label="the agent simulator (demo)">
          <Card pad={false} className="overflow-hidden"><Console policies={policies.data} onChange={refresh} /></Card>
        </Collapse>
      </div>
      {newKey && (
        <Modal eyebrow="Shown once · only its hash is stored" title="Agent registered" onClose={() => setNewKey(null)}>
          <code className="block break-all border-2 border-fg bg-bg p-4 font-mono text-[12px] text-mint">{newKey.api_key}</code>
          <div className="mt-5 flex justify-end gap-2">
            <Button onClick={() => navigator.clipboard.writeText(newKey.api_key)}>Copy</Button>
            <Button variant="primary" icon={Plug} onClick={() => { setAgent({ id: newKey.id, name: newKey.name, key: newKey.api_key }); setNewKey(null); }}>Use in simulator</Button>
          </div>
        </Modal>
      )}
    </>
  );
}
