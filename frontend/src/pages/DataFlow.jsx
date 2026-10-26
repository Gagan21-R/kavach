import { GitBranch, Plus, Radar, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { get, post } from "../api";
import { useLoad } from "../state";
import { Badge, Button, CATEGORIES, Card, Chips, Decision, Empty, ErrorNote, Field, PageHeader, Spinner, cx, fmtTime, inputCls, label } from "../ui";

const W = 190, H = 64, GX = 150, GY = 22;

function Graph({ assets, selected, onSelect }) {
  const layout = useMemo(() => {
    const byId = Object.fromEntries(assets.map((a) => [a.id, a]));
    const depth = {};
    const d = (id, seen = new Set()) => {
      if (depth[id] != null) return depth[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const parents = byId[id]?.derived_from || [];
      depth[id] = parents.length ? Math.max(...parents.map((p) => d(p, seen))) + 1 : 0;
      return depth[id];
    };
    assets.forEach((a) => d(a.id));
    const cols = {};
    assets.forEach((a) => { (cols[depth[a.id]] ||= []).push(a); });
    const pos = {};
    Object.entries(cols).forEach(([c, list]) => list.forEach((a, i) => { pos[a.id] = { x: 10 + Number(c) * (W + GX), y: 10 + i * (H + GY) }; }));
    const width = 20 + (Math.max(0, ...Object.keys(cols).map(Number)) + 1) * (W + GX);
    const height = 20 + Math.max(...Object.values(cols).map((l) => l.length)) * (H + GY);
    return { pos, width, height };
  }, [assets]);
  const sensitive = new Set(["location", "contacts", "biometrics", "health", "financial", "government_id", "photos", "messages"]);
  return (
    <div className="overflow-x-auto scroll-thin">
      <svg width={layout.width} height={layout.height} className="min-w-full">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#94a3b8" /></marker></defs>
        {assets.flatMap((a) => a.derived_from.map((p) => {
          const s = layout.pos[p], t = layout.pos[a.id];
          if (!s || !t) return null;
          const x1 = s.x + W, y1 = s.y + H / 2, x2 = t.x - 4, y2 = t.y + H / 2, mx = (x1 + x2) / 2;
          return (
            <g key={`${p}-${a.id}`}>
              <path d={`M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`} fill="none" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arr)" />
              <text x={mx} y={(y1 + y2) / 2 - 6} textAnchor="middle" className="fill-slate-500 text-[10px]">{a.transformation.length > 26 ? `${a.transformation.slice(0, 25)}…` : a.transformation}</text>
            </g>
          );
        }))}
        {assets.map((a) => {
          const p = layout.pos[a.id];
          const inherited = a.effective_categories.filter((c) => !a.categories.includes(c));
          const hot = a.effective_categories.some((c) => sensitive.has(c));
          return (
            <g key={a.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer" onClick={() => onSelect(a.id)}>
              <rect width={W} height={H} rx="10" className={cx(selected === a.id ? "fill-indigo-50 stroke-indigo-500" : hot ? "fill-white stroke-red-300" : "fill-white stroke-slate-300")} strokeWidth={selected === a.id ? 2 : 1} />
              <text x="12" y="22" className="fill-slate-900 text-[12.5px] font-semibold">{a.label.slice(0, 24)}</text>
              <text x="12" y="40" className="fill-slate-500 text-[10.5px]">{a.categories.join(", ") || "no own labels"}</text>
              {inherited.length > 0 && <text x="12" y="55" className="fill-red-600 text-[10.5px]">inherits: {inherited.join(", ")}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function DataFlow() {
  const assets = useLoad(() => get("/data-flow/assets"));
  const events = useLoad(() => get("/data-flow/events"));
  const coverage = useLoad(() => get("/data-flow/coverage"));
  const [sel, setSel] = useState(null);
  const [lineage, setLineage] = useState(null);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ label: "", categories: [], source: "", derived_from: [], transformation: "" });
  const [error, setError] = useState(null);
  const [check, setCheck] = useState({ destination: "ads.example.net", purpose: "advertising" });
  const [checkRes, setCheckRes] = useState(null);

  const select = async (id) => {
    setSel(id);
    setCheckRes(null);
    try { setLineage(await get(`/data-flow/lineage/${id}`)); } catch (e) { setError(e); }
  };
  const create = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await post("/data-flow/assets", form);
      setForm({ label: "", categories: [], source: "", derived_from: [], transformation: "" });
      assets.reload();
    } catch (err) { setError(err); }
  };
  const dryRun = async () => {
    setError(null);
    try {
      const a = assets.data.find((x) => x.id === sel);
      setCheckRes(await post("/data-flow/evaluate", { asset_id: sel, action: "transfer_data", destination: check.destination, purpose: check.purpose, declared_categories: a.categories }));
    } catch (e) { setError(e); }
  };

  const filtered = (events.data || []).filter((f) => !q || JSON.stringify(f).toLowerCase().includes(q.toLowerCase()));
  const blocked = (events.data || []).filter((f) => f.decision === "BLOCK").length;
  return (
    <>
      <PageHeader title="Data Flow Observatory" subtitle="Where your data went, what it was derived from, and which rule applied. Derived data keeps the restrictions of its sources: a neighbourhood inferred from GPS is still location data." />
      <ErrorNote error={error} />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Lineage" subtitle="Click an asset to see its flows and test where it may go." className="xl:col-span-2">
          {assets.loading && !assets.data ? <Spinner /> : !assets.data?.length ? <Empty icon={GitBranch} title="No labelled data yet">Load demo data or register an asset on the right.</Empty> : <Graph assets={assets.data} selected={sel} onSelect={select} />}
          {lineage && (
            <div className="mt-4 grid gap-4 border-t border-slate-100 pt-4 md:grid-cols-2">
              <div>
                <h4 className="mb-2 text-[13px] font-semibold text-slate-800">Would it be allowed?</h4>
                <div className="grid grid-cols-2 gap-2">
                  <input className={inputCls} value={check.destination} onChange={(e) => setCheck({ ...check, destination: e.target.value })} />
                  <select className={inputCls} value={check.purpose} onChange={(e) => setCheck({ ...check, purpose: e.target.value })}>
                    {["navigation", "advertising", "analytics", "ai_training", "service_delivery", "personalization"].map((p) => <option key={p}>{p}</option>)}
                  </select>
                </div>
                <Button size="sm" className="mt-2" icon={Radar} onClick={dryRun}>Dry run</Button>
                {checkRes && (
                  <div className="rise mt-2 rounded-lg border border-slate-200 p-2.5 text-[12.5px]">
                    <Decision value={checkRes.decision} /> <span className="ml-1 text-slate-600">carries {checkRes.effective_categories.join(", ")}</span>
                    <ul className="mt-1 text-slate-600">{checkRes.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
                  </div>
                )}
              </div>
              <div>
                <h4 className="mb-2 text-[13px] font-semibold text-slate-800">Flows touching this lineage</h4>
                {lineage.flows.length === 0 ? <p className="text-[12.5px] text-slate-500">None yet. Send this asset through the gateway with its asset id.</p> : lineage.flows.map((f) => (
                  <div key={f.id} className="mb-1.5 text-[12.5px]"><Decision value={f.decision} /> <span className="text-slate-700">{f.destination}</span> <span className="text-slate-400">{f.code || f.outcome}</span></div>
                ))}
              </div>
            </div>
          )}
        </Card>
        <Card title="Register data">
          <form onSubmit={create} className="space-y-3">
            <Field label="Label"><input required className={inputCls} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Weekly commute summary" /></Field>
            <Field label="Own categories"><Chips options={CATEGORIES} value={form.categories} onChange={(v) => setForm({ ...form, categories: v })} /></Field>
            {assets.data?.length > 0 && <Field label="Derived from"><Chips options={assets.data.map((a) => a.label)} value={form.derived_from.map((id) => assets.data.find((a) => a.id === id)?.label)} onChange={(v) => setForm({ ...form, derived_from: assets.data.filter((a) => v.includes(a.label)).map((a) => a.id) })} /></Field>}
            {form.derived_from.length > 0 && <Field label="Transformation"><input required className={inputCls} value={form.transformation} onChange={(e) => setForm({ ...form, transformation: e.target.value })} placeholder="aggregate by week" /></Field>}
            <Button variant="primary" icon={Plus}>Register</Button>
          </form>
        </Card>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card title={`Flow timeline · ${blocked} blocked`} className="xl:col-span-2" pad={false}
          action={<div className="relative"><Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" /><input className={cx(inputCls, "w-52 py-1 pl-8")} placeholder="Search flows" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
          {!filtered.length ? <div className="p-5"><Empty icon={Radar} title="No flows recorded">Run the agent console on the Guardian page.</Empty></div> : (
            <div className="max-h-[420px] overflow-auto scroll-thin">
              <table className="w-full text-[12.5px]">
                <thead className="sticky top-0 bg-white"><tr className="border-b border-slate-100 text-left text-slate-500"><th className="px-5 py-2.5 font-medium">When</th><th className="font-medium">Flow</th><th className="font-medium">Data</th><th className="font-medium">Decision</th><th className="pr-5 font-medium">Why</th></tr></thead>
                <tbody>{filtered.map((f) => (
                  <tr key={f.id} className="border-b border-slate-50 align-top last:border-0">
                    <td className="whitespace-nowrap px-5 py-2.5 text-slate-500">{fmtTime(f.created_at)}</td>
                    <td className="py-2.5"><div className="text-slate-800">{label(f.action)} → {f.destination}</div><div className="text-slate-400">{label(f.purpose)}</div></td>
                    <td className="py-2.5">{f.effective_categories.join(", ")}{f.effective_categories.length > f.declared_categories.length && <div className="text-red-600">declared: {f.declared_categories.join(", ") || "none"}</div>}</td>
                    <td className="py-2.5"><Decision value={f.decision} /><div className="mt-0.5 text-[11px] text-slate-400">{label(f.outcome)}</div></td>
                    <td className="max-w-xs py-2.5 pr-5 text-slate-600">{f.code && <b className="mr-1 text-slate-800">{f.code}</b>}{f.reason}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Monitoring boundary" subtitle="What Kavach can and cannot see.">
          {coverage.data && (
            <div className="space-y-3 text-[12.5px]">
              <div><Badge tone="green">Instrumented</Badge><ul className="mt-1.5 space-y-1 text-slate-600">{coverage.data.instrumented.map((x) => <li key={x}>• {x}</li>)}</ul></div>
              <div><Badge tone="red">Outside the boundary</Badge><ul className="mt-1.5 space-y-1 text-slate-600">{coverage.data.not_instrumented.map((x) => <li key={x}>• {x}</li>)}</ul></div>
              <p className="rounded-lg bg-amber-50 p-2.5 text-amber-900">{coverage.data.note}</p>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
