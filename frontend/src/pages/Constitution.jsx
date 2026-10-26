import { FlaskConical, History, Plus, ScrollText, Trash2 } from "lucide-react";
import { useState } from "react";
import { del, get, post } from "../api";
import { useLoad } from "../state";
import {
  ACTIONS, Badge, Button, CATEGORIES, Card, Chips, Decision, Empty, ErrorNote, Field, Modal, PageHeader, PURPOSES, Spinner, cx, fmtTime, inputCls, label,
} from "../ui";

const EFFECT_TONE = { ALLOW: "green", DENY: "red", REQUIRE_APPROVAL: "amber" };
const blank = { effect: "DENY", data_categories: [], purposes: [], recipients: "", actions: [], description: "", expires_at: "" };

function RuleForm({ onSaved }) {
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/consent/rules", {
        effect: f.effect, data_categories: f.data_categories, purposes: f.purposes, actions: f.actions, description: f.description,
        recipients: f.recipients.split(",").map((s) => s.trim()).filter(Boolean),
        expires_at: f.expires_at ? new Date(f.expires_at).toISOString() : null,
      });
      setF(blank);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save} className="space-y-4">
      <Field label="Effect">
        <div className="grid grid-cols-3 gap-2">
          {["ALLOW", "REQUIRE_APPROVAL", "DENY"].map((e) => (
            <button type="button" key={e} onClick={() => setF({ ...f, effect: e })}
              className={cx("rounded-lg border px-2 py-2 text-[12.5px] font-medium", f.effect === e ? { ALLOW: "border-emerald-500 bg-emerald-50 text-emerald-700", DENY: "border-red-500 bg-red-50 text-red-700", REQUIRE_APPROVAL: "border-amber-500 bg-amber-50 text-amber-800" }[e] : "border-slate-200 text-slate-600")}>
              {label(e)}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Data categories" hint="Pick at least one, or * for all data."><Chips options={["*", ...CATEGORIES]} value={f.data_categories} onChange={(v) => setF({ ...f, data_categories: v })} /></Field>
      <Field label="Purposes" hint="Leave empty to apply to any purpose."><Chips options={PURPOSES} value={f.purposes} onChange={(v) => setF({ ...f, purposes: v })} /></Field>
      <Field label="Actions" hint="Leave empty to apply to any protected action."><Chips options={ACTIONS} value={f.actions} onChange={(v) => setF({ ...f, actions: v })} /></Field>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Recipients" hint="Comma-separated hosts; *.example.com covers subdomains."><input className={inputCls} value={f.recipients} onChange={(e) => setF({ ...f, recipients: e.target.value })} placeholder="maps.example.com" /></Field>
        <Field label="Expires (optional)"><input type="datetime-local" className={inputCls} value={f.expires_at} onChange={(e) => setF({ ...f, expires_at: e.target.value })} /></Field>
      </div>
      <Field label="Note to yourself"><input className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Maps may use my location for directions" /></Field>
      <ErrorNote error={error} />
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-slate-500">{f.effect === "ALLOW" ? "Allowing loosens protection: you'll confirm your password." : "Tightening never asks for your password."}</span>
        <Button variant="primary" icon={Plus} loading={busy} disabled={!f.data_categories.length}>Add rule</Button>
      </div>
    </form>
  );
}

function Tester() {
  const [t, setT] = useState({ action: "transfer_data", destination: "maps.example.com", purpose: "navigation", data_categories: ["location"] });
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const run = async () => {
    setError(null);
    try { setRes(await post("/consent/check", t)); } catch (e) { setError(e); setRes(null); }
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Action"><select className={inputCls} value={t.action} onChange={(e) => setT({ ...t, action: e.target.value })}>{ACTIONS.map((a) => <option key={a}>{a}</option>)}</select></Field>
        <Field label="Purpose"><select className={inputCls} value={t.purpose} onChange={(e) => setT({ ...t, purpose: e.target.value })}>{PURPOSES.map((a) => <option key={a}>{a}</option>)}</select></Field>
      </div>
      <Field label="Destination"><input className={inputCls} value={t.destination} onChange={(e) => setT({ ...t, destination: e.target.value })} /></Field>
      <Field label="Data"><Chips options={CATEGORIES} value={t.data_categories} onChange={(v) => setT({ ...t, data_categories: v })} /></Field>
      <Button icon={FlaskConical} onClick={run} disabled={!t.data_categories.length}>Check against my rules</Button>
      <ErrorNote error={error} />
      {res && (
        <div className="rise rounded-lg border border-slate-200 p-3">
          <div className="flex items-center gap-2"><Decision value={res.decision} />{res.approvable && <span className="text-[12px] text-slate-500">you could approve it</span>}</div>
          <ul className="mt-2 space-y-1 text-[12.5px] text-slate-600">{res.outcomes.map((o) => <li key={o.category}>• <b className="text-slate-800">{o.category}</b>: {o.reason}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

export default function Constitution() {
  const rules = useLoad(() => get("/consent/rules"));
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);
  const revoke = async (id) => {
    setError(null);
    try { await del(`/consent/rules/${id}`); rules.reload(); } catch (e) { setError(e); }
  };
  return (
    <>
      <PageHeader title="Personal Consent Constitution" subtitle="Your own rules, enforced by code, not by a model. A DENY always wins, even over a narrower ALLOW. Anything no rule covers needs your approval." />
      <div className="grid gap-6 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <Card title="Your rules" subtitle="Edits create a new version; old versions are kept." pad={false}>
            <ErrorNote error={error} />
            {rules.loading ? <div className="p-5"><Spinner /></div> : !rules.data?.length ? <div className="p-5"><Empty icon={ScrollText} title="No rules yet">Until you add rules, every protected agent action needs your approval.</Empty></div> : (
              <div className="divide-y divide-slate-100">
                {rules.data.map((r) => (
                  <div key={r.id} className="flex items-start justify-between gap-3 px-5 py-3.5">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={EFFECT_TONE[r.effect]}>{label(r.effect)}</Badge>
                        {r.data_categories.map((c) => <Badge key={c} tone="purple">{c}</Badge>)}
                        {r.purposes.length ? <span className="text-[12px] text-slate-500">for {r.purposes.map(label).join(", ")}</span> : <span className="text-[12px] text-slate-400">any purpose</span>}
                      </div>
                      <div className="mt-1 text-[12px] text-slate-500">
                        {r.recipients.length ? `to ${r.recipients.join(", ")}` : "any recipient"} · {r.actions.length ? r.actions.map(label).join(", ") : "any action"}
                        {r.expires_at && ` · expires ${fmtTime(r.expires_at)}`} · v{r.constitution_version}
                      </div>
                      {r.description && <div className="mt-1 text-[12.5px] italic text-slate-600">“{r.description}”</div>}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button size="sm" variant="ghost" icon={History} onClick={async () => setHistory(await get(`/consent/rules/${r.id}/history`))} aria-label="History" />
                      <Button size="sm" variant="ghost" icon={Trash2} onClick={() => revoke(r.id)} aria-label="Revoke" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Test an action" subtitle="Dry run against your rules only. Nothing is issued." className="mt-6"><Tester /></Card>
        </div>
        <div className="xl:col-span-2">
          <Card title="Add a rule"><RuleForm onSaved={rules.reload} /></Card>
        </div>
      </div>
      {history && (
        <Modal title="Rule history" onClose={() => setHistory(null)}>
          <ol className="space-y-2">{history.map((h) => (
            <li key={h.id} className="rounded-lg border border-slate-200 p-2.5 text-[12.5px]">
              <div className="flex items-center gap-1.5"><Badge tone={EFFECT_TONE[h.effect]}>{label(h.effect)}</Badge><span className="text-slate-500">v{h.constitution_version} · {fmtTime(h.created_at)}</span>{!h.active && <Badge>inactive</Badge>}</div>
              <div className="mt-1 text-slate-600">{h.data_categories.join(", ")} {h.purposes.length ? `for ${h.purposes.join(", ")}` : ""}</div>
            </li>
          ))}</ol>
        </Modal>
      )}
    </>
  );
}
