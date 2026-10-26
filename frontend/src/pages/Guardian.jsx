import { Ban, Bot, Check, KeyRound, Plug, Plus, Send, ShieldQuestion, Ticket, X } from "lucide-react";
import { useState } from "react";
import { get, post } from "../api";
import { useAgent, useLoad } from "../state";
import {
  ACTIONS, Badge, Button, CATEGORIES, Card, Chips, Decision, Empty, ErrorNote, Field, Json, Modal, PageHeader, PURPOSES, cx, fmtTime, inputCls, label,
} from "../ui";

function tokenStatus(t) {
  if (t.revoked_at) return ["red", "revoked"];
  if (new Date(t.expires_at) < new Date()) return ["gray", "expired"];
  if (t.use_count >= t.max_uses) return ["gray", "used up"];
  return ["green", "active"];
}

function Console({ policies, onChange }) {
  const { agent } = useAgent();
  const [req, setReq] = useState({ action: "transfer_data", destination: "maps.example.com", purpose: "navigation", data_categories: ["location"], records: 1, policy_source_id: "" });
  const [token, setToken] = useState(null);
  const [pending, setPending] = useState(null);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(null);
  const policyId = req.policy_source_id || policies?.[0]?.id || "";

  const push = (step, status, data) => setLog((l) => [{ step, status, data, at: new Date().toLocaleTimeString() }, ...l].slice(0, 12));
  const call = async (step, path, body, extra = {}) => {
    setBusy(step);
    try {
      const r = await post(path, body, { agentKey: agent.key, allowError: true, ...extra });
      push(step, r.status, r.data);
      onChange?.();
      return r;
    } finally {
      setBusy(null);
    }
  };
  const base = { action: req.action, destination: req.destination, purpose: req.purpose, data_categories: req.data_categories };
  const evaluate = () => call("evaluate", "/guardian/evaluate", { ...base, policy_source_id: policyId });
  const authorize = async (approval_id) => {
    const r = await call("authorize", "/guardian/authorize", { ...base, policy_source_id: policyId, ...(approval_id ? { approval_id } : {}) });
    if (r.status === 201) { setToken(r.data.token); setPending(null); }
    if (r.status === 202) setPending(r.data.approval_request_id);
    return r;
  };
  const execute = () => call("execute", "/gateway/execute", { ...base, record_count: Number(req.records) || 1, payload: { note: "simulated payload" } }, { consentToken: token || "" });

  if (!agent) {
    return <Empty icon={Bot} title="No agent connected">Create an agent below (or load demo data on the Overview) and click “Use in console”. The API key stays in this tab's memory only.</Empty>;
  }
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-[12.5px] text-slate-600"><Plug className="h-3.5 w-3.5 text-emerald-600" />Acting as <b>{agent.name}</b> with its API key</div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Action"><select className={inputCls} value={req.action} onChange={(e) => setReq({ ...req, action: e.target.value })}>{ACTIONS.map((a) => <option key={a}>{a}</option>)}</select></Field>
          <Field label="Purpose"><select className={inputCls} value={req.purpose} onChange={(e) => setReq({ ...req, purpose: e.target.value })}>{PURPOSES.map((a) => <option key={a}>{a}</option>)}</select></Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Destination"><input className={inputCls} value={req.destination} onChange={(e) => setReq({ ...req, destination: e.target.value })} /></Field>
          <Field label="Policy"><select className={inputCls} value={policyId} onChange={(e) => setReq({ ...req, policy_source_id: e.target.value })}>{policies?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Records"><input type="number" min="1" className={inputCls} value={req.records} onChange={(e) => setReq({ ...req, records: e.target.value })} /></Field>
        </div>
        <Field label="Data"><Chips options={CATEGORIES} value={req.data_categories} onChange={(v) => setReq({ ...req, data_categories: v })} /></Field>
        <div className="flex flex-wrap gap-2">
          <Button icon={ShieldQuestion} loading={busy === "evaluate"} onClick={evaluate}>1 · Ask Guardian</Button>
          <Button variant="primary" icon={Ticket} loading={busy === "authorize"} onClick={() => authorize()}>2 · Request token</Button>
          {pending && <Button icon={Check} onClick={() => authorize(pending)}>2b · Redeem my approval</Button>}
          <Button variant="success" icon={Send} loading={busy === "execute"} onClick={execute} disabled={!token}>3 · Execute via gateway</Button>
        </div>
        <div className="text-[12px] text-slate-500">{token ? <>Holding token <code className="rounded bg-slate-100 px-1">{token.slice(0, 16)}…</code> · execute twice to see replay protection</> : "No token yet."}</div>
      </div>
      <div className="space-y-2">
        {log.length === 0 && <p className="text-[13px] text-slate-500">Responses from the real API appear here.</p>}
        {log.map((l, i) => {
          const d = l.data || {};
          const decision = d.decision || d.error?.decision;
          return (
            <div key={i} className={cx("rise rounded-lg border p-3", i === 0 ? "border-slate-300" : "border-slate-100 opacity-80")}>
              <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
                <b className="text-slate-800">{l.step}</b><Badge>HTTP {l.status}</Badge>{decision && <Decision value={decision} />}
                {d.error?.code && <Badge tone="red">{d.error.code}</Badge>}{d.executed && <Badge tone="green">executed (simulated)</Badge>}
                <span className="ml-auto text-[11px] text-slate-400">{l.at}</span>
              </div>
              <div className="mt-1.5 text-[12.5px] text-slate-600">
                {d.error?.message || (d.reasons || d.evaluation?.reasons || []).join("; ") || (d.result ? `delivered to ${d.result.delivered_to}` : "")}
                {d.approval_request_id && <span className="mt-1 block text-amber-700">Approval requested; approve it below, then request the token again with the approval.</span>}
              </div>
              {i === 0 && <details className="mt-2"><summary className="cursor-pointer text-[12px] text-indigo-600">raw response</summary><Json value={d} /></details>}
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

  return (
    <>
      <PageHeader title="Guardian" subtitle="AI agents must ask the Guardian before any protected action. Tokens are scoped to one agent, action, destination, purpose and data set, expire in minutes, and are re-checked at the gateway." />
      <ErrorNote error={error} />
      <Card title="Agent console" subtitle="Drive a real agent against the real API: evaluate, request a token, then execute through the gateway." className="mb-6">
        <Console policies={policies.data} onChange={refresh} />
      </Card>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Pending approvals" subtitle="Requests your rules say you must decide." pad={false}>
          {!approvals.data?.filter((a) => a.status === "PENDING").length ? <div className="p-5"><Empty icon={Check} title="Nothing waiting" /></div> : (
            <div className="divide-y divide-slate-100">
              {approvals.data.filter((a) => a.status === "PENDING").map((a) => (
                <div key={a.id} className="flex items-start justify-between gap-3 px-5 py-3.5">
                  <div className="text-[13px]">
                    <div className="font-medium text-slate-900">{label(a.action)} → {a.destination}</div>
                    <div className="text-[12px] text-slate-500">{a.data_categories.join(", ")} for {label(a.purpose)} · expires {fmtTime(a.expires_at)}</div>
                    <div className="mt-1 text-[12px] text-amber-700">{a.reason}</div>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <Button size="sm" variant="success" icon={Check} onClick={() => decide(a.id, true)}>Approve</Button>
                    <Button size="sm" icon={X} onClick={() => decide(a.id, false)}>Deny</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Agents" pad={false} action={<div className="flex gap-2"><input className={cx(inputCls, "w-44 py-1")} value={name} onChange={(e) => setName(e.target.value)} /><Button size="sm" variant="primary" icon={Plus} onClick={createAgent}>Register</Button></div>}>
          {!agents.data?.length ? <div className="p-5"><Empty icon={Bot} title="No agents registered" /></div> : (
            <div className="divide-y divide-slate-100">
              {agents.data.map((a) => (
                <div key={a.id} className="flex items-center justify-between px-5 py-3 text-[13px]">
                  <div><span className="font-medium text-slate-900">{a.name}</span> {agent?.id === a.id && <Badge tone="green">in console</Badge>}<div className="text-[12px] text-slate-400">{fmtTime(a.created_at)}</div></div>
                  {a.active ? <Button size="sm" icon={Ban} onClick={() => revokeAgent(a.id)}>Revoke</Button> : <Badge tone="red">revoked</Badge>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      <Card title="Consent tokens" subtitle="Revoking stops future use only; it cannot recall data already delivered." className="mt-6" pad={false}>
        {!tokens.data?.length ? <div className="p-5"><Empty icon={KeyRound} title="No tokens issued yet" /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-slate-100 text-left text-slate-500"><th className="px-5 py-2.5 font-medium">Scope</th><th className="font-medium">Uses</th><th className="font-medium">Records</th><th className="font-medium">Expires</th><th className="font-medium">Status</th><th /></tr></thead>
              <tbody>{tokens.data.map((t) => {
                const [tone, st] = tokenStatus(t);
                return (
                  <tr key={t.id} className="border-b border-slate-50 last:border-0">
                    <td className="px-5 py-2.5"><div className="font-medium text-slate-800">{label(t.action)} → {t.destination}</div><div className="text-slate-500">{t.data_categories.join(", ")} · {label(t.purpose)}{t.approval_id ? " · approved by you" : ""}</div></td>
                    <td className="tabular-nums">{t.use_count}/{t.max_uses}</td><td className="tabular-nums">{t.records_used}/{t.max_records}</td>
                    <td>{fmtTime(t.expires_at)}</td><td><Badge tone={tone}>{st}</Badge>{t.revocation_reason && <div className="text-[11px] text-slate-400">{t.revocation_reason}</div>}</td>
                    <td className="pr-5 text-right">{st === "active" && <Button size="sm" onClick={() => revokeToken(t.id)}>Revoke</Button>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
      {newKey && (
        <Modal title="Agent registered" onClose={() => setNewKey(null)}>
          <p className="text-[13px] text-slate-600">This API key is shown once. Only its hash is stored.</p>
          <code className="mt-3 block break-all rounded-lg bg-slate-900 p-3 text-[12px] text-emerald-300">{newKey.api_key}</code>
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={() => navigator.clipboard.writeText(newKey.api_key)}>Copy</Button>
            <Button variant="primary" icon={Plug} onClick={() => { setAgent({ id: newKey.id, name: newKey.name, key: newKey.api_key }); setNewKey(null); }}>Use in console</Button>
          </div>
        </Modal>
      )}
    </>
  );
}
