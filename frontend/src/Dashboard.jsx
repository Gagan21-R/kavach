import { ChevronDown, Globe, House, ScrollText } from "lucide-react";
import { Component, useState } from "react";
import { useOutletContext } from "react-router-dom";
import Audit from "./pages/Audit";
import Constitution from "./pages/Constitution";
import CourtroomLite from "./pages/CourtroomLite";
import Emergency from "./pages/Emergency";
import Guardian from "./pages/Guardian";
import Overview from "./pages/Overview";
import TestHistory from "./pages/TestHistory";
import Watchman from "./pages/Watchman";
import Websites from "./pages/Websites";
import { PageHeader, cx, useReveals } from "./ui";

function Agents() {
  return (
    <>
      <Guardian />
      <div className="mt-16"><Emergency /></div>
    </>
  );
}

// Specialist views for when you want to see exactly how a decision was made; closed until opened.
const TOOLS = [
  { id: "test-history", title: "Test history", text: "Every Red Team and automated test run, with a postmortem report for each.", C: TestHistory },
  { id: "courtroom", title: "Courtroom", text: "Paste any policy text and put it through the six agents. Nothing is tracked.", C: CourtroomLite },
  { id: "audit", title: "Audit log", text: "Every decision Kavach made, on a tamper-evident record.", C: Audit },
];

function MoreTools() {
  const [open, setOpen] = useState(() => {
    const h = window.location.hash.slice(1);
    return TOOLS.some((t) => t.id === h) ? h : null;
  });
  return (
    <>
      <PageHeader eyebrow="More tools" title="Under the hood" subtitle="For when you want to see exactly how a decision was made." />
      <div className="card">
        {TOOLS.map(({ id, title, text, C }) => (
          <div key={id} id={id} className="scroll-mt-[150px] border-b-2 border-fg last:border-b-0">
            <button onClick={() => setOpen(open === id ? null : id)} className={cx("group flex w-full items-center gap-5 px-6 py-5 text-left", open === id ? "bg-yellow" : "hover:bg-raised")}>
              <div className="min-w-0 flex-1">
                <div className="text-[16px] font-bold uppercase text-fg">{title}</div>
                <div className="mt-0.5 text-[14px] text-fg2">{text}</div>
              </div>
              <ChevronDown className={cx("h-5 w-5 transition-transform", open === id && "rotate-180")} />
            </button>
            {open === id && <div className="fade border-t-2 border-fg px-4 py-8 md:px-8"><SectionBoundary><C /></SectionBoundary></div>}
          </div>
        ))}
      </div>
    </>
  );
}

/** Three main tabs. Each holds the sections that belong together. */
export const TABS = [
  { id: "home", label: "Home", icon: House, sections: [{ id: "overview", C: Overview }] },
  { id: "websites", label: "Websites", icon: Globe, sections: [{ id: "websites-review", C: Websites }, { id: "watchman", C: Watchman }] },
  { id: "rules", label: "Rules & agents", icon: ScrollText, sections: [{ id: "your-rules", C: Constitution }, { id: "agents", C: Agents }, { id: "more", C: MoreTools }] },
];

// Section ids (and old addresses) to the tab that shows them.
const EXTRA = {
  overview: "home", watchman: "websites", inbox: "websites", email: "websites", library: "websites", browser: "websites", sites: "websites",
  "websites-review": "websites", "your-rules": "rules", constitution: "rules", agents: "rules", guardian: "rules",
  emergency: "rules", "emergency-stop": "rules", more: "rules", courtroom: "rules", audit: "rules", "test-history": "rules", tests: "rules",
};
export function tabOf(id) {
  if (!id) return null;
  if (TABS.some((t) => t.id === id)) return id;
  return EXTRA[id] || null;
}

class SectionBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div className="card px-6 py-5 text-[14px] text-fg2">
          This section hit a problem and was paused so the rest of the page keeps working.
          <button className="ml-3 underline underline-offset-4" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Dashboard() {
  const { tab } = useOutletContext();
  const current = TABS.find((t) => t.id === tab) || TABS[0];
  const ref = useReveals(current.id);
  return (
    <div ref={ref} key={current.id} className="fade">
      {current.sections.map(({ id, C }, i) => (
        <section key={id} id={id} className={i ? "mt-20 scroll-mt-[150px] border-t-2 border-fg pt-16" : "scroll-mt-[150px]"}>
          <SectionBoundary><C /></SectionBoundary>
        </section>
      ))}
    </div>
  );
}
