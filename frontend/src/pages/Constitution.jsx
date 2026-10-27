import { Globe, Layers, Pencil, Plus, ScrollText, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { del, get, post, put } from "../api";
import { useLoad } from "../state";
import { Button, Card, Chip, Collapse, Empty, ErrorNote, Modal, PageHeader, SectionTitle, Spinner, cx, fmtTime, inputCls, label } from "../ui";
import { PreferenceGrid, PreferencesButton } from "./Onboarding";

const EFFECT = { ALLOW: ["mint", "OK"], DENY: ["ember", "Never"], REQUIRE_APPROVAL: ["sand", "Ask me"] };

// Ready-made starting points; anything not listed is denied for the group's websites.
const TEMPLATES = [
  { id: "essentials", name: "Essentials only", note: "Just enough to use the service", choices: { basic: { service: "OK" } } },
  { id: "shopping", name: "Shopping", note: "Orders, payments and delivery",
    choices: { basic: { service: "OK" }, money: { service: "OK" }, location: { service: "ASK" }, browsing: { analytics: "ASK" } } },
  { id: "streaming", name: "Streaming & media", note: "Accounts and what you watch",
    choices: { basic: { service: "OK" }, browsing: { service: "OK", analytics: "ASK", ads: "ASK" } } },
  { id: "social", name: "Social", note: "Posts, photos and friends",
    choices: { basic: { service: "OK" }, media: { service: "OK" }, contacts: { service: "ASK" }, browsing: { analytics: "ASK" } } },
  { id: "work", name: "Work", note: "Documents and messages for your job",
    choices: { basic: { service: "OK" }, media: { service: "OK" }, browsing: { service: "OK" } } },
  { id: "lockdown", name: "Deny everything", note: "Nothing is allowed; start from zero", choices: {} },
];

const lower = (t) => t.charAt(0).toLowerCase() + t.slice(1);

function flatten(choices) {
  return Object.entries(choices || {}).flatMap(([g, per]) => Object.entries(per).map(([u, a]) => ({ g, u, a })));
}

function RuleSentences({ meta, choices, onChange }) {
  const L = useMemo(() => ({
    g: Object.fromEntries(meta.data.map((d) => [d.id, d.label])),
    u: Object.fromEntries(meta.uses.map((d) => [d.id, lower(d.label)])),
  }), [meta]);
  const rows = flatten(choices);
  const [g, setG] = useState(meta.data[0].id);
  const [u, setU] = useState(meta.uses[0].id);
  const set = (gg, uu, a) => {
    const next = structuredClone(choices || {});
    if (a) next[gg] = { ...(next[gg] || {}), [uu]: a };
    else { delete next[gg]?.[uu]; if (next[gg] && !Object.keys(next[gg]).length) delete next[gg]; }
    onChange(next);
  };
  return (
    <div>
      {!rows.length ? <p className="border-2 border-dashed border-fg2 px-4 py-4 text-[14px] text-fg2">Nothing is allowed yet: every website in this group will be denied everything. Add what’s OK below.</p> : (
        <ul className="divide-y-2 divide-line border-2 border-fg">
          {rows.map(({ g: gg, u: uu, a }) => (
            <li key={`${gg}-${uu}`} className="flex flex-wrap items-center gap-3 bg-surface px-4 py-2.5">
              <span className="min-w-0 flex-1 text-[14px]"><b>{L.g[gg]}</b> <span className="text-fg2">{L.u[uu]}</span></span>
              <div className="flex">
                {["OK", "ASK"].map((x) => (
                  <button key={x} type="button" onClick={() => set(gg, uu, x)}
                    className={cx("h-8 border-2 border-fg px-3 font-mono text-[11px] font-bold uppercase -ml-[2px] first:ml-0",
                      a === x ? (x === "OK" ? "bg-mint text-surface" : "bg-sand text-surface") : "bg-surface hover:bg-raised")}>
                    {x === "OK" ? "OK" : "Ask me"}
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => set(gg, uu, null)} className="p-1 hover:text-ember" aria-label="Remove this rule (denied)"><X className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 grid items-center gap-2 sm:grid-cols-[auto_1fr_1fr_auto_auto]">
        <span className="label">Add a rule</span>
        <select className={cx(inputCls, "py-2")} value={g} onChange={(e) => setG(e.target.value)}>
          {meta.data.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
        <select className={cx(inputCls, "py-2")} value={u} onChange={(e) => setU(e.target.value)}>
          {meta.uses.map((d) => <option key={d.id} value={d.id}>{lower(d.label)}</option>)}
        </select>
        <Button size="sm" type="button" onClick={() => set(g, u, "OK")}>As OK</Button>
        <Button size="sm" type="button" onClick={() => set(g, u, "ASK")}>As Ask me</Button>
      </div>
    </div>
  );
}

function GroupEditor({ meta, group, allSites, preselected, onClose, onSaved }) {
  const [name, setName] = useState(group?.name || "");
  const [choices, setChoices] = useState(structuredClone(group?.choices || TEMPLATES[0].choices));
  const [sites, setSites] = useState(group ? group.sites.map((s) => s.domain) : preselected);
  const [extra, setExtra] = useState("");
  const [template, setTemplate] = useState(group ? null : "essentials");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toggle = (d) => setSites(sites.includes(d) ? sites.filter((x) => x !== d) : [...sites, d]);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      if (group) await put(`/rule-groups/${group.id}`, { name, choices, sites });
      else await post("/rule-groups", { name, choices, sites });
      onSaved(); onClose();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const pickable = [...new Map([...sites.map((d) => ({ domain: d, name: d })), ...allSites].map((s) => [s.domain, s])).values()];

  return (
    <Modal eyebrow={group ? "Edit group" : "New group"} title={group ? group.name : "Group some websites"} onClose={onClose} wide>
      <div className="space-y-7">
        <div>
          <div className="label mb-2 text-fg">1 · Name</div>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Shopping" autoFocus />
        </div>
        {!group && (
          <div>
            <div className="label mb-2 text-fg">2 · Start from</div>
            <div className="grid gap-2 sm:grid-cols-3">
              {TEMPLATES.map((t) => (
                <button key={t.id} type="button" onClick={() => { setTemplate(t.id); setChoices(structuredClone(t.choices)); if (!name) setName(t.id === "lockdown" ? "" : t.name); }}
                  className={cx("border-2 border-fg px-3 py-2.5 text-left transition-colors", template === t.id ? "bg-yellow shadow-[3px_3px_0_#0b0b0b]" : "bg-surface hover:bg-raised")}>
                  <div className="text-[14px] font-bold uppercase">{t.name}</div>
                  <div className="text-[12.5px] text-fg2">{t.note}</div>
                </button>
              ))}
            </div>
          </div>
        )}
        <div>
          <div className="label mb-2 text-fg">{group ? "2" : "3"} · What’s allowed <span className="text-fg2">· everything else is denied</span></div>
          <RuleSentences meta={meta} choices={choices} onChange={(c) => { setChoices(c); setTemplate(null); }} />
          <div className="mt-3">
            <Collapse label="the full grid">
              <PreferenceGrid meta={{ groups: meta.data, uses: meta.uses }} value={choices} onChange={(c) => { setChoices(c); setTemplate(null); }} fallback="NEVER" presets={false} />
            </Collapse>
          </div>
        </div>
        <div>
          <div className="label mb-2 text-fg">{group ? "3" : "4"} · Websites in this group</div>
          <div className="flex flex-wrap gap-2">
            {pickable.map((s) => (
              <label key={s.domain} className={cx("flex h-9 cursor-pointer items-center gap-2 border-2 border-fg px-3 text-[13.5px]", sites.includes(s.domain) ? "bg-yellow" : "bg-surface hover:bg-raised")}>
                <input type="checkbox" className="h-4 w-4 accent-[#0b0b0b]" checked={sites.includes(s.domain)} onChange={() => toggle(s.domain)} />{s.name}
              </label>
            ))}
            {!pickable.length && <span className="text-[13.5px] text-fg2">No websites yet. Add one:</span>}
          </div>
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); const d = extra.trim().toLowerCase(); if (d && !sites.includes(d)) setSites([...sites, d]); setExtra(""); }}>
            <input className={cx(inputCls, "py-2")} value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Another website, e.g. flipkart.com" />
            <Button size="sm" icon={Plus} disabled={!extra.trim()}>Add</Button>
          </form>
        </div>
      </div>
      <div className="mt-6"><ErrorNote error={error} /></div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={!name.trim()} onClick={save}>{group ? "Save group" : "Create group"}</Button>
      </div>
    </Modal>
  );
}

export default function Constitution() {
  const data = useLoad(() => get("/rule-groups"));
  const rules = useLoad(() => get("/consent/rules"));
  const [editing, setEditing] = useState(null); // {group} or {new: true}
  const [picked, setPicked] = useState([]);
  const [target, setTarget] = useState("");
  const [error, setError] = useState(null);
  const d = data.data;
  const reload = () => { data.reload(); rules.reload(); };
  const act = (fn) => async () => { setError(null); try { await fn(); reload(); } catch (e) { setError(e); } };
  const generalRules = (rules.data || []).filter((r) => !r.group_id);
  const all = d ? [
    ...d.general_sites.map((s) => ({ ...s, group: null })),
    ...d.groups.flatMap((g) => g.sites.map((s) => ({ ...s, group: g }))),
  ].sort((a, b) => a.name.localeCompare(b.name)) : [];
  const toggle = (dom) => setPicked(picked.includes(dom) ? picked.filter((x) => x !== dom) : [...picked, dom]);
  const move = act(async () => { await post("/rule-groups/assign-many", { domains: picked, group_id: target || null }); setPicked([]); });

  return (
    <>
      <PageHeader index={4} eyebrow="Your rules" title="Your rules, by website"
        subtitle="Every website follows your general rules from sign-up. Tick websites and put them in a group to give them their own rules: in a group you pick what’s OK or Ask me, and everything else is denied." />
      <ErrorNote error={error} />
      {!d ? <Spinner /> : (
        <div className="grid gap-6 xl:grid-cols-[1.05fr_1fr]">
          <section className="card p-6">
            <SectionTitle icon={Globe}>Your websites</SectionTitle>
            {!all.length ? <Empty icon={Globe} title="No websites yet">Check or track a website on the Websites tab and it appears here.</Empty> : (
              <>
                <ul className="divide-y-2 divide-line border-2 border-fg">
                  {all.map((s) => (
                    <li key={s.domain}>
                      <label className={cx("flex cursor-pointer items-center gap-3 px-4 py-2.5", picked.includes(s.domain) ? "bg-yellow" : "bg-surface hover:bg-raised")}>
                        <input type="checkbox" className="h-4 w-4 accent-[#0b0b0b]" checked={picked.includes(s.domain)} onChange={() => toggle(s.domain)} />
                        <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium">{s.name}</span>
                        {s.group ? <Chip tone="fg" dot={false}>{s.group.name}</Chip> : <Chip tone="muted" dot={false}>General</Chip>}
                      </label>
                    </li>
                  ))}
                </ul>
                <div className={cx("mt-4 flex flex-wrap items-center gap-2 border-2 border-fg px-4 py-3", picked.length ? "bg-yellow" : "bg-raised")}>
                  <span className="font-mono text-[12px] font-bold uppercase">{picked.length} selected</span>
                  <select className={cx(inputCls, "ml-auto w-auto py-2")} value={target} onChange={(e) => setTarget(e.target.value)} disabled={!picked.length}>
                    <option value="">General rules</option>
                    {d.groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                  <Button size="sm" disabled={!picked.length} onClick={move}>Move</Button>
                  <Button size="sm" variant="primary" icon={Plus} disabled={!picked.length} onClick={() => setEditing({ new: true })}>New group from these</Button>
                </div>
              </>
            )}
          </section>

          <div className="space-y-6">
            <section className="card p-6">
              <SectionTitle icon={ScrollText} action={<PreferencesButton />}>General rules</SectionTitle>
              <p className="text-[14px] text-fg2">Your sign-up answers ({generalRules.length} rules). Used by every website that isn’t in a group. Anything they don’t cover asks you first.</p>
            </section>
            {d.groups.map((g) => (
              <section key={g.id} className="card p-6">
                <SectionTitle icon={Layers} action={<div className="flex gap-1">
                  <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing({ group: g })}>Edit</Button>
                  <Button size="sm" variant="ghost" icon={Trash2} onClick={act(() => del(`/rule-groups/${g.id}`))}>Delete</Button>
                </div>}>{g.name}</SectionTitle>
                <div className="flex flex-wrap gap-1.5">
                  {flatten(g.choices).map(({ g: gg, u, a }) => {
                    const dl = d.data.find((x) => x.id === gg)?.label;
                    const ul = lower(d.uses.find((x) => x.id === u)?.label || "");
                    return <Chip key={`${gg}${u}`} tone={a === "OK" ? "mint" : "sand"}>{a === "OK" ? "OK" : "Ask"} · {dl} · {ul}</Chip>;
                  })}
                  <Chip tone="ember">Everything else denied</Chip>
                </div>
                <div className="mt-4 text-[13.5px] text-fg2"><b className="text-fg">{g.sites.length}</b> website{g.sites.length === 1 ? "" : "s"}: {g.sites.map((s) => s.name).join(", ") || "none yet"}</div>
              </section>
            ))}
            <button onClick={() => setEditing({ new: true })} className="card flex min-h-[120px] w-full flex-col items-center justify-center gap-1 border-dashed hover:bg-yellow">
              <Plus className="h-5 w-5" /><span className="font-mono text-[12px] font-bold uppercase">New group</span>
              <span className="text-[13px] text-fg2">Shopping, Work, Social…</span>
            </button>
          </div>
        </div>
      )}

      <div className="mt-8">
        <Collapse label="every rule">
          <div className="card mt-2">
            {rules.loading && !rules.data ? <div className="p-6"><Spinner /></div> : !rules.data?.length ? <div className="p-6"><Empty icon={ScrollText} title="No rules yet" /></div> : (
              <div className="divide-y-2 divide-line">
                {rules.data.map((r) => {
                  const [tone, word] = EFFECT[r.effect];
                  const group = d?.groups.find((g) => g.id === r.group_id);
                  return (
                    <div key={r.id} className="flex flex-wrap items-center gap-3 px-6 py-3">
                      <Chip tone={tone}>{word}</Chip>
                      <span className="min-w-0 flex-1 text-[13.5px] text-fg2">{r.data_categories.map(label).join(", ")}{r.purposes.length ? ` · ${r.purposes.map(label).join(", ")}` : ""}{r.recipients.length ? ` · ${r.recipients.join(", ")}` : ""}</span>
                      <span className="font-mono text-[10.5px] uppercase text-dim">{group ? group.name : "General"} · {fmtTime(r.created_at)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </Collapse>
      </div>
      {editing && d && (
        <GroupEditor meta={d} group={editing.group || null} allSites={all.map((s) => ({ domain: s.domain, name: s.name }))}
          preselected={editing.new ? picked : []} onClose={() => setEditing(null)} onSaved={() => { setPicked([]); reload(); }} />
      )}
    </>
  );
}
