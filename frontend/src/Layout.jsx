import {
  Bot, ClipboardList, Eye, FlaskConical, Gavel, GitBranch, KeyRound, LayoutDashboard, LogOut, MessageCircle,
  OctagonX, ScrollText, ShieldAlert, ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { post } from "./api";
import { useAgent, useAuth } from "./state";
import { Button, ErrorNote, Field, Modal, cx, inputCls } from "./ui";

const NAV = [
  ["Overview", "/", LayoutDashboard],
  ["Courtroom", "/courtroom", Gavel],
  ["The Trap", "/trap", ShieldAlert],
  ["Watchman", "/watchman", Eye],
  ["Constitution", "/constitution", ScrollText],
  ["Guardian", "/guardian", KeyRound],
  ["Data Flow", "/data-flow", GitBranch],
  ["Emergency", "/emergency", OctagonX],
  ["Red Team Lab", "/red-team", FlaskConical],
  ["Audit Log", "/audit", ClipboardList],
  ["Assistant", "/assistant", MessageCircle],
];

function StepUpModal() {
  const { stepUp, finishStepUp, user } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!stepUp) return null;
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await post("/auth/step-up", { password });
      setPassword("");
      setError(null);
      finishStepUp(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Confirm it's you" onClose={() => finishStepUp(false)}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-[13px] text-slate-600">This change loosens your protections, so Kavach needs you to re-enter the password for <b>{user?.email}</b>. It stays confirmed for 5 minutes.</p>
        <Field label="Password"><input autoFocus type="password" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <ErrorNote error={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={() => finishStepUp(false)}>Cancel</Button>
          <Button variant="primary" loading={busy}>Confirm</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Layout() {
  const { user, logout, frozen } = useAuth();
  const { agent } = useAgent();
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col bg-slate-900 text-slate-300">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600"><ShieldCheck className="h-4.5 w-4.5 text-white" /></div>
          <div>
            <div className="font-serif text-[17px] font-semibold text-white">Kavach</div>
            <div className="text-[11px] text-slate-400">reads · argues · guards · watches</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(([name, to, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"}
              className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition",
                isActive ? "bg-slate-800 font-medium text-white" : "hover:bg-slate-800/60 hover:text-white")}>
              <Icon className="h-4 w-4" />{name}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-800 p-4 text-[12px]">
          <div className="flex items-center gap-1.5 text-slate-400"><Bot className="h-3.5 w-3.5" />{agent ? <span className="truncate text-slate-200">Agent: {agent.name}</span> : "No agent connected"}</div>
          <div className="mt-2 truncate text-slate-300">{user?.email}</div>
          <button onClick={logout} className="mt-2 flex items-center gap-1.5 text-slate-400 hover:text-white"><LogOut className="h-3.5 w-3.5" />Sign out</button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto scroll-thin">
        {frozen && (
          <div className="flex items-center gap-2 bg-red-600 px-8 py-2 text-[13px] font-medium text-white">
            <OctagonX className="h-4 w-4" /> Emergency Stop is active. Every protected agent action is frozen.
            <NavLink to="/emergency" className="ml-auto underline">Open Emergency Center</NavLink>
          </div>
        )}
        <div className="mx-auto max-w-7xl px-8 py-8"><Outlet /></div>
        <footer className="px-8 pb-6 text-center text-[11.5px] text-slate-400">Explainable signals, not legal advice. All demo companies are fictional; agent actions are simulated.</footer>
      </main>
      <StepUpModal />
    </div>
  );
}
