// KAVACH deck, redesigned. Content is identical to KAVACH_7_Slides_Visual_Updated.pptx; only the design changes.
// Usage: node build.js <out.pptx>
// Objects named "A<step>[w]|label" are animated by animate.py (step = stagger order, w = wipe from left).
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");
const { applyTheme } = require(process.env.APPLY_THEME);

const OUT = process.argv[2];
const THEME = {
  name: "Kavach Editorial",
  headFontFace: "Georgia",
  bodyFontFace: "Segoe UI",
  colors: {
    dk1: "0B1B2B", lt1: "FFFFFF", dk2: "102536", lt2: "F3F6F8",
    accent1: "0F766E", accent2: "5EEAD4", accent3: "C2410C", accent4: "475569", accent5: "E6F2F1", accent6: "FFF4EC",
    hlink: "0F766E", folHlink: "475569",
  },
};
const H = THEME.colors;
const HAIR = "E2E8F0";
const MUTED = "64748B";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "KAVACH";
pres.author = "Team KAVACH";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "KV_COVER",
  background: { color: C.text2 },
  objects: [],
});
pres.defineSlideMaster({
  title: "KV_CONTENT",
  background: { color: C.background1 },
  margin: [0.4, 0.7, 0.4, 0.7],
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: 0.7, y: 0.42, w: 11.9, h: 0.3, fontSize: 11, bold: true, color: C.accent1, charSpacing: 1.5, margin: 0, valign: "middle" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 0.76, w: 11.9, h: 0.75, fontSize: 34, color: C.text1, fontFace: THEME.headFontFace, margin: 0, valign: "middle", align: "left" }, text: "" } },
  ],
});

// ---------- helpers ----------
async function png(svg, size) {
  const buf = await sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function icon(name, hex) {
  const Comp = lu[name];
  if (!Comp) throw new Error(`missing icon ${name}`);
  return png(ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: `#${hex}`, size: 256, strokeWidth: 1.75 })), 256);
}
const T = (s, text, o) => s.addText(text, { isTextBox: true, margin: 0, valign: "top", fontSize: 14, color: C.text1, ...o });
const R = (s, o) => s.addShape(o.round ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE, {
  rectRadius: o.round || 0, line: o.line ? { color: o.line, width: 0.75 } : { type: "none" }, ...o, fill: { color: o.fill },
});
const hline = (s, x, y, w, name, color = HAIR, width = 0.75) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color, width }, objectName: name });
const vline = (s, x, y, h, name, color = HAIR) => s.addShape(pres.shapes.LINE, { x, y, w: 0, h, line: { color, width: 0.75 }, objectName: name });
async function iconDot(s, name, x, y, d, name2, fill = "E6F2F1", stroke = H.accent1) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: `${name2} dot` });
  const p = d * 0.25;
  s.addImage({ data: await icon(name, stroke), x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, altText: "", objectName: `${name2} glyph` });
}
const footer = (s, text) => T(s, text, { x: 10.63, y: 7.0, w: 2.0, h: 0.25, fontSize: 9.5, color: MUTED, align: "right", objectName: "Footer" });
const header = (s, kicker, title) => { s.addText(kicker, { placeholder: "kicker" }); s.addText(title, { placeholder: "title" }); };
const bullets = (items, o = {}) => items.map((t, i) => ({ text: t, options: { bullet: { characterCode: "2013", indent: 18 }, breakLine: i < items.length - 1, paraSpaceAfter: 5, ...o } }));

// Shield emblem for the cover: three nested outlines and a solid core, drawn as SVG.
function emblemSvg() {
  const shield = (s) => {
    const c = 512, w = 360 * s, top = 512 - 400 * s;
    const l = c - w / 2, r = c + w / 2, mid = 512 + 40 * s, bot = 512 + 430 * s;
    return `M${c} ${top} L${r} ${top + 120 * s} V${mid} C${r} ${mid + 200 * s} ${c + 120 * s} ${bot - 60 * s} ${c} ${bot} C${c - 120 * s} ${bot - 60 * s} ${l} ${mid + 200 * s} ${l} ${mid} V${top + 120 * s} Z`;
  };
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
    <path d="${shield(1.12)}" fill="none" stroke="#5EEAD4" stroke-opacity="0.16" stroke-width="3"/>
    <path d="${shield(0.92)}" fill="none" stroke="#5EEAD4" stroke-opacity="0.32" stroke-width="3"/>
    <path d="${shield(0.72)}" fill="none" stroke="#5EEAD4" stroke-opacity="0.6" stroke-width="3"/>
    <path d="${shield(0.52)}" fill="#0F766E"/>
    <path d="M440 560 L500 620 L610 496" fill="none" stroke="#FFFFFF" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

async function build() {
  // ===================== 1. Cover =====================
  let s = pres.addSlide({ masterName: "KV_COVER" });
  s.addImage({ data: await png(emblemSvg(), 1400), x: 7.9, y: 0.95, w: 5.4, h: 5.4, altText: "KAVACH shield emblem", objectName: "A0|Emblem" });
  T(s, "AI • PRIVACY • TRUST", { x: 0.85, y: 1.45, w: 6, h: 0.3, fontSize: 12, bold: true, color: C.accent2, charSpacing: 3, objectName: "A1|Kicker" });
  T(s, "KAVACH", { x: 0.85, y: 1.85, w: 7, h: 1.3, fontSize: 80, color: C.background1, fontFace: THEME.headFontFace, charSpacing: 6, valign: "middle", objectName: "A2|Wordmark" });
  T(s, "Consent Intelligence & Protection for AI Agents", { x: 0.85, y: 3.25, w: 7, h: 0.5, fontSize: 24, color: C.background1, objectName: "A3|Subtitle" });
  T(s, "A consent firewall that helps people understand policies, set personal boundaries, and control how AI agents access or share data.",
    { x: 0.85, y: 3.92, w: 7.0, h: 0.95, fontSize: 16, color: "9FB3C4", lineSpacingMultiple: 1.15, objectName: "A4|Description" });
  hline(s, 0.85, 5.35, 6.5, "A5w|Divider", "2A4156", 0.75);
  T(s, "Project presentation  |  Consent Court 2.0", { x: 0.85, y: 5.52, w: 6.5, h: 0.3, fontSize: 12, color: "9FB3C4", objectName: "A6|Meta" });
  T(s, "Informed consent. Enforced boundaries. Human control.", { x: 0.85, y: 5.88, w: 6.5, h: 0.35, fontSize: 14, bold: true, color: C.accent2, objectName: "A6|Tagline" });
  T(s, "01/07", { x: 11.63, y: 7.0, w: 1.0, h: 0.25, fontSize: 9.5, color: "6E8496", align: "right", objectName: "Page" });

  // ===================== 2. Why KAVACH Is Needed =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "THE CONSENT PROBLEM", "Why KAVACH Is Needed");
  const problems = [
    ["01", "Policies are hard to understand", "Long legal text hides how data is collected, retained, shared, or used for AI training."],
    ["02", "Consent can become outdated", "A policy may change after a user accepts it, introducing new recipients or purposes."],
    ["03", "AI agents add new risks", "Agents can encounter prompt injection, misleading pages, or conflicting instructions."],
  ];
  problems.forEach(([n, h, b], i) => {
    const x = 0.7 + i * 4.1;
    if (i) vline(s, x - 0.2, 1.85, 2.25, `A${i + 1}|Divider ${i}`);
    T(s, n, { x, y: 1.8, w: 1.2, h: 0.55, fontSize: 30, color: C.accent1, fontFace: THEME.headFontFace, objectName: `A${i + 1}|Problem ${n} number` });
    T(s, h, { x, y: 2.45, w: 3.7, h: 0.55, fontSize: 17, bold: true, objectName: `A${i + 1}|Problem ${n} title` });
    T(s, b, { x, y: 2.95, w: 3.55, h: 0.95, fontSize: 14, color: C.accent4, lineSpacingMultiple: 1.1, objectName: `A${i + 1}|Problem ${n} body` });
  });
  R(s, { x: 0.7, y: 4.38, w: 11.93, h: 1.05, fill: C.accent5, round: 0.08, objectName: "A4|Goal panel" });
  T(s, "KAVACH’s goal", { x: 1.05, y: 4.55, w: 4, h: 0.25, fontSize: 12, bold: true, color: C.accent1, objectName: "A4|Goal label" });
  T(s, "Create an auditable consent firewall between an AI agent and protected data transfers.",
    { x: 1.05, y: 4.82, w: 11.3, h: 0.45, fontSize: 20, fontFace: THEME.headFontFace, objectName: "A4|Goal statement" });
  T(s, "Core principles", { x: 0.7, y: 5.72, w: 4, h: 0.25, fontSize: 12, bold: true, color: MUTED, objectName: "A5|Principles label" });
  const principles = ["Explicit user rules", "Evidence-backed decisions", "Least privilege", "Review when uncertain", "Preserve incident evidence"];
  for (let i = 0; i < 5; i++) {
    const x = 0.7 + i * 2.42;
    s.addImage({ data: await icon("LuCheck", H.accent1), x, y: 6.1, w: 0.24, h: 0.24, altText: "", objectName: `A${6 + i}|Principle ${i + 1} mark` });
    T(s, principles[i], { x: x + 0.34, y: 6.06, w: 1.95, h: 0.6, fontSize: 14, objectName: `A${6 + i}|Principle ${i + 1}` });
  }
  footer(s, "KAVACH  •  2/7");

  // ===================== 3. Key Features =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "PERSONALIZED PRIVACY AND ONGOING PROTECTION", "Key Features");
  const features = [
    ["LuUserRound", "Personal Consultant", "Helps users set personal boundaries and understand low-risk choices; explains trade-offs in plain language."],
    ["LuOctagonX", "Emergency Stop", "Freezes protected gateway actions and revokes permissions when warranted; preserves evidence for investigation."],
    ["LuScale", "Independent Outside Judge", "An independent auditor checks the model’s findings, evidence, and possible bias."],
    ["LuKeyRound", "Token Issuing Gateway", "Issues short-lived, scoped tokens; checks validity, destination, purpose, policy version and limits before allowing transfer."],
    ["LuMessagesSquare", "Explanation Chatbot + Graphs", "Explains decisions and displays data-flow lineage, risk signals, and changes in an understandable format."],
    ["LuFlaskConical", "Synthetic Red-Team Lab", "Tests fake scenarios—prompt injection, conflicting findings, stale tokens and policy changes—without exposing real data."],
    ["LuRadar", "Continuous Data-Tracking / Ad Blocking", "Tracks supported data flows and highlights unexpected tracking or advertising-related data sharing where detectable."],
  ];
  const top3 = 1.7, row = 0.6;
  hline(s, 0.7, top3, 11.93, "A1w|Rule top");
  for (let i = 0; i < features.length; i++) {
    const [ic, h, b] = features[i];
    const y = top3 + i * row;
    await iconDot(s, ic, 0.7, y + 0.12, 0.4, `A${i + 1}|Feature ${i + 1}`);
    T(s, h, { x: 1.3, y: y + 0.1, w: 3.2, h: row - 0.14, fontSize: 15, bold: true, valign: "middle", objectName: `A${i + 1}|Feature ${i + 1} title` });
    T(s, b, { x: 4.75, y: y + 0.08, w: 7.85, h: row - 0.12, fontSize: 13.5, color: C.accent4, valign: "middle", objectName: `A${i + 1}|Feature ${i + 1} body` });
    hline(s, 0.7, y + row, 11.93, `A${i + 1}|Rule ${i + 1}`);
  }
  const by = top3 + 7 * row + 0.2;
  R(s, { x: 0.7, y: by, w: 11.93, h: 0.62, fill: C.accent6, round: 0.08, objectName: "A9|Boundary panel" });
  s.addImage({ data: await icon("LuTriangleAlert", H.accent3), x: 0.95, y: by + 0.18, w: 0.26, h: 0.26, altText: "", objectName: "A9|Boundary glyph" });
  T(s, [
    { text: "Important boundary   ", options: { bold: true, color: C.accent3 } },
    { text: "KAVACH can only observe instrumented flows; it cannot guarantee detection of all tracking or retrieve data already stolen by an attacker.", options: { color: C.text1 } },
  ], { x: 1.35, y: by, w: 11.1, h: 0.62, fontSize: 13.5, valign: "middle", objectName: "A9|Boundary text" });
  footer(s, "KAVACH  •  3/7");

  // ===================== 4. Authentication & Personal Consent =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "SECURE IDENTITY • EXPLICIT APPROVAL • USER-DEFINED RULES", "Authentication & Personal Consent");
  const steps = [
    ["1", "Authenticate the user", ["Verify identity before sensitive actions", "Use passkeys / WebAuthn or secure step-up authentication", "Voice alone is not enough"]],
    ["2", "Set personal boundaries", ["ALLOW: specific data, purpose and recipient", "DENY: explicit prohibition", "ASK / REVIEW: unclear or sensitive requests"]],
    ["3", "Authorize each action", ["Check current policy and consent version", "Confirm destination, purpose and data scope", "Require explicit confirmation for real provider actions"]],
  ];
  hline(s, 1.0, 2.12, 8.2, "A1w|Step track", "B9D7D3", 1.25);
  steps.forEach(([n, h, items], i) => {
    const x = 0.7 + i * 4.1;
    s.addShape(pres.shapes.OVAL, { x, y: 1.82, w: 0.6, h: 0.6, fill: { color: C.accent1 }, line: { color: C.background1, width: 3 }, objectName: `A${i + 2}|Step ${n} dot` });
    T(s, n, { x, y: 1.82, w: 0.6, h: 0.6, fontSize: 18, color: C.background1, fontFace: THEME.headFontFace, align: "center", valign: "middle", objectName: `A${i + 2}|Step ${n} numeral` });
    T(s, h, { x, y: 2.62, w: 3.7, h: 0.4, fontSize: 18, bold: true, objectName: `A${i + 2}|Step ${n} title` });
    T(s, bullets(items), { x, y: 3.1, w: 3.55, h: 1.45, fontSize: 14, color: C.accent4, objectName: `A${i + 2}|Step ${n} list` });
  });
  T(s, "Decision precedence", { x: 0.7, y: 4.85, w: 4, h: 0.25, fontSize: 12, bold: true, color: MUTED, objectName: "A5|Precedence label" });
  const prec = [["USER DENY", C.accent3, C.background1], ["REVIEW / BLOCK if uncertain", C.text2, C.background1], ["Model recommendation", C.background2, C.accent4]];
  prec.forEach(([t, fill, ink], i) => {
    const x = 0.7 + i * 4.215;
    R(s, { x, y: 5.2, w: 3.5, h: 0.72, fill, round: 0.08, objectName: `A${6 + i}|Precedence ${i + 1}` });
    T(s, t, { x: x + 0.3, y: 5.2, w: 2.9, h: 0.72, fontSize: 15, bold: true, color: ink, valign: "middle", charSpacing: i === 0 ? 2 : 0, objectName: `A${6 + i}|Precedence ${i + 1} text` });
    if (i < 2) s.addShape(pres.shapes.CHEVRON, { x: x + 3.68, y: 5.43, w: 0.2, h: 0.26, fill: { color: "94A3B8" }, line: { type: "none" }, objectName: `A${6 + i}|Precedence arrow ${i + 1}` });
  });
  s.addImage({ data: await icon("LuLock", H.accent1), x: 0.7, y: 6.32, w: 0.28, h: 0.28, altText: "", objectName: "A9|Guardian glyph" });
  T(s, "Only the trusted server-side Guardian can grant or revoke permissions; an AI model cannot override user rules.",
    { x: 1.12, y: 6.28, w: 11.4, h: 0.38, fontSize: 15, valign: "middle", objectName: "A9|Guardian statement" });
  footer(s, "KAVACH  •  4/7");

  // ===================== 5. Multi-Agent Workflow =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "EVIDENCE-LED DECISIONS WITH CONFLICT HANDLING", "Multi-Agent Workflow");
  const node = async (step, ic, name, desc, x, y, w, h, dark) => {
    R(s, { x, y, w, h, fill: dark ? C.text2 : C.background2, round: 0.1, objectName: `A${step}|${name} card` });
    await iconDot(s, ic, x + 0.22, y + 0.2, 0.48, `A${step}|${name}`, dark ? "1E3A4F" : "FFFFFF", dark ? H.accent2 : H.accent1);
    T(s, name, { x: x + 0.22, y: y + 0.78, w: w - 0.44, h: 0.32, fontSize: 16, bold: true, color: dark ? C.background1 : C.text1, objectName: `A${step}|${name} name` });
    T(s, desc, { x: x + 0.22, y: y + 1.1, w: w - 0.44, h: h - 1.18, fontSize: 13.5, color: dark ? "B6C6D3" : C.accent4, objectName: `A${step}|${name} desc` });
  };
  const arrow = (step, x, y, w, both, name) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: "94A3B8", width: 1.25, endArrowType: "triangle", beginArrowType: both ? "triangle" : undefined }, objectName: `A${step}w|${name}` });
  const tw = 2.7, tg = (11.93 - 4 * 2.7) / 3, ty = 1.78, th = 1.6;
  const tx = (i) => 0.7 + i * (tw + tg);
  const agentsTop = [
    ["LuShieldCheck", "Sentinel", "Sanitizes policy text and flags hidden instructions."],
    ["LuGavel", "Prosecutor", "Raises evidence-backed risk concerns."],
    ["LuShield", "Defense", "Checks justifications and potential benefits."],
    ["LuFileSearch", "Evidence Clerk", "Verifies exact text spans and citations."],
  ];
  for (let i = 0; i < 4; i++) {
    await node(1 + i * 2, agentsTop[i][0], agentsTop[i][1], agentsTop[i][2], tx(i), ty, tw, th);
    if (i < 3) arrow(2 + i * 2, tx(i) + tw + 0.07, ty + th / 2, tg - 0.14, i === 1, `Arrow ${i + 1}`);
  }
  const bw = (11.93 - 2 * 0.34) / 3, bg = 0.34, byy = 4.02, bh = 1.62;
  const bx = (i) => 0.7 + i * (bw + bg);
  // Evidence Clerk -> Independent Auditor (elbow)
  const ecx = tx(3) + tw / 2, aux = bx(1) + bw / 2, elbowY = (ty + th + byy) / 2;
  s.addShape(pres.shapes.LINE, { x: ecx, y: ty + th + 0.06, w: 0, h: elbowY - (ty + th + 0.06), line: { color: "94A3B8", width: 1.25 }, objectName: "A8|Elbow down" });
  s.addShape(pres.shapes.LINE, { x: aux, y: elbowY, w: ecx - aux, h: 0, line: { color: "94A3B8", width: 1.25 }, objectName: "A8|Elbow across" });
  s.addShape(pres.shapes.LINE, { x: aux, y: elbowY, w: 0, h: byy - 0.06 - elbowY, line: { color: "94A3B8", width: 1.25, endArrowType: "triangle" }, objectName: "A8|Elbow into auditor" });
  await node(9, "LuEye", "Watchman", "Detects semantic changes across policy versions.", bx(0), byy, bw, bh);
  await node(9, "LuScanEye", "Independent Auditor", "Blindly checks evidence, agreement, disagreement and bias.", bx(1), byy, bw, bh);
  arrow(10, bx(1) + bw + 0.07, byy + bh / 2, bg - 0.14, false, "Arrow to guardian");
  await node(11, "LuLockKeyhole", "Guardian Gateway", "Enforces deterministic rules and scoped capabilities.", bx(2), byy, bw, bh, true);
  // Watchman sends changed policies back to the Sentinel
  s.addShape(pres.shapes.LINE, { x: tx(0) + 1.35, y: ty + th + 0.06, w: 0, h: byy - (ty + th) - 0.12, line: { color: "94A3B8", width: 1.25, dashType: "dash", beginArrowType: "triangle" }, objectName: "A12|Watchman loop" });
  R(s, { x: 0.7, y: 5.98, w: 11.93, h: 0.6, fill: C.accent6, round: 0.08, objectName: "A13|Conflict panel" });
  s.addImage({ data: await icon("LuTriangleAlert", H.accent3), x: 0.95, y: 6.15, w: 0.26, h: 0.26, altText: "", objectName: "A13|Conflict glyph" });
  T(s, [
    { text: "Conflict rule: ", options: { bold: true, color: C.accent3 } },
    { text: "contradictory high-impact findings or missing evidence → REVIEW/BLOCK, never silent ALLOW.", options: { color: C.text1 } },
  ], { x: 1.35, y: 5.98, w: 11.1, h: 0.6, fontSize: 14, valign: "middle", objectName: "A13|Conflict text" });
  footer(s, "KAVACH  •  5/7");

  // ===================== 6. Monitoring, Data Tracking & Emergency Stop =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "AFTER CONSENT: KEEP WATCHING", "Monitoring, Data Tracking & Emergency Stop");
  const cols = [
    ["LuFileDiff", "Semantic Policy Search", ["Compare new and previous versions", "Detect changed wording with the same meaning", "Flag new recipients, longer retention or AI training", "Fetch failure = UNKNOWN, not “no change”"]],
    ["LuWorkflow", "Data-Flow Tracking", ["Log source, purpose, destination and decision", "Visualize lineage with graphs", "Flag unexpected supported transfers", "Identify detectable tracking / ad-sharing patterns"]],
    ["LuSiren", "Emergency Response", ["Freeze protected operations", "Revoke tokens and isolate affected workers", "Preserve forensic evidence", "Restore from verified backups"]],
  ];
  for (let i = 0; i < 3; i++) {
    const [ic, h, items] = cols[i];
    const x = 0.7 + i * 4.1;
    if (i) vline(s, x - 0.2, 1.85, 3.0, `A${i + 1}|Divider ${i}`);
    await iconDot(s, ic, x, 1.8, 0.58, `A${i + 1}|${h}`);
    T(s, h, { x, y: 2.55, w: 3.6, h: 0.4, fontSize: 18, bold: true, objectName: `A${i + 1}|${h} title` });
    T(s, bullets(items), { x, y: 3.02, w: 3.55, h: 1.75, fontSize: 14, color: C.accent4, objectName: `A${i + 1}|${h} list` });
  }
  T(s, "Example incident flow", { x: 0.7, y: 5.12, w: 4, h: 0.25, fontSize: 12, bold: true, color: MUTED, objectName: "A4|Flow label" });
  const stages = [["DETECT", "0F766E"], ["FREEZE", "0E5E5A"], ["INVESTIGATE", "124A57"], ["RECOVER", "102536"]];
  stages.forEach(([t, fill], i) => {
    const x = 0.7 + i * 2.95;
    s.addShape(i === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, { x, y: 5.45, w: 3.08, h: 0.52, fill: { color: fill }, line: { type: "none" }, objectName: `A${5 + i}w|Stage ${t}` });
    T(s, t, { x: x + (i === 0 ? 0.25 : 0.45), y: 5.45, w: 2.3, h: 0.52, fontSize: 13, bold: true, color: C.background1, charSpacing: 3, valign: "middle", align: i === 0 ? "left" : "left", objectName: `A${5 + i}|Stage ${t} label` });
  });
  R(s, { x: 0.7, y: 6.25, w: 11.93, h: 0.56, fill: C.accent6, round: 0.08, objectName: "A9|Safety panel" });
  s.addImage({ data: await icon("LuInfo", H.accent3), x: 0.95, y: 6.4, w: 0.26, h: 0.26, altText: "", objectName: "A9|Safety glyph" });
  T(s, [
    { text: "Safety note: ", options: { bold: true, color: C.accent3 } },
    { text: "stopping future transfers cannot guarantee retrieval or deletion of data already copied outside the system.", options: { color: C.text1 } },
  ], { x: 1.35, y: 6.25, w: 11.1, h: 0.56, fontSize: 14, valign: "middle", objectName: "A9|Safety text" });
  footer(s, "KAVACH  •  6/7");

  // ===================== 7. Architecture, Testing & Expected Impact =====================
  s = pres.addSlide({ masterName: "KV_CONTENT" });
  header(s, "A PRACTICAL PATH TO A WORKING PROTOTYPE", "Architecture, Testing & Expected Impact");
  T(s, "Proposed technology", { x: 0.7, y: 1.75, w: 3.7, h: 0.35, fontSize: 17, bold: true, objectName: "A1|Tech title" });
  const stack = [["Frontend", "React + Tailwind"], ["Backend", "Python FastAPI"], ["Agents", "LangGraph / deterministic orchestration"], ["Storage", "PostgreSQL"], ["Deployment", "Render + scheduled Watchman"]];
  let sy = 2.22;
  stack.forEach(([k, v], i) => {
    const h = `${k}: ${v}`.length > 30 ? 0.58 : 0.4;
    R(s, { x: 0.7, y: sy, w: 3.7, h, fill: i % 2 ? "EEF3F6" : C.background2, round: 0.05, objectName: `A${2 + i}|Stack ${k}` });
    T(s, [{ text: `${k}: `, options: { bold: true, color: C.accent1 } }, { text: v, options: { color: C.text1 } }],
      { x: 0.88, y: sy, w: 3.4, h, fontSize: 13, valign: "middle", objectName: `A${2 + i}|Stack ${k} text` });
    sy += h + 0.05;
  });
  vline(s, 4.6, 1.8, 2.95, "A7|Divider 1");
  vline(s, 8.7, 1.8, 2.95, "A7|Divider 2");
  const lists = [
    ["Validation plan", "LuCircleCheck", 4.8, ["Synthetic policy and prompt-injection tests", "Conflicting agent findings", "Expired / replayed / wrong-destination tokens", "Cross-user access and gateway-bypass tests", "Backup recovery and audit checks"]],
    ["Expected value", "LuArrowUpRight", 8.9, ["More understandable consent", "User rules enforced at the gateway", "Early alerts on policy changes", "Auditable decisions and incident response", "A reusable Guardian API for AI agents"]],
  ];
  for (let L = 0; L < 2; L++) {
    const [title, ic, x, items] = lists[L];
    T(s, title, { x, y: 1.75, w: 3.7, h: 0.35, fontSize: 17, bold: true, objectName: `A${8 + L}|${title} title` });
    let ly = 2.22;
    for (let i = 0; i < items.length; i++) {
      const lines = items[i].length > 34 ? 2 : 1;
      s.addImage({ data: await icon(ic, H.accent1), x, y: ly + 0.04, w: 0.2, h: 0.2, altText: "", objectName: `A${8 + L}|${title} mark ${i + 1}` });
      T(s, items[i], { x: x + 0.32, y: ly, w: 3.4, h: lines * 0.24, fontSize: 13.5, color: C.accent4, objectName: `A${8 + L}|${title} item ${i + 1}` });
      ly += lines * 0.24 + 0.14;
    }
  }
  T(s, "Implementation priorities", { x: 0.7, y: 5.0, w: 4, h: 0.25, fontSize: 12, bold: true, color: MUTED, objectName: "A10|Priorities label" });
  hline(s, 0.85, 5.45, 11.6, "A10w|Priority track", "B9D7D3", 1.25);
  const phases = [["P0", "Authentication + rules + Guardian"], ["P1", "Audit + tracking + Watchman"], ["P2", "Chatbot + graphs + integrations"]];
  phases.forEach(([p, t], i) => {
    const x = 0.7 + i * 4.1;
    s.addShape(pres.shapes.OVAL, { x: x + 0.06, y: 5.33, w: 0.24, h: 0.24, fill: { color: i === 0 ? C.accent1 : C.background1 }, line: { color: C.accent1, width: 2 }, objectName: `A${11 + i}|Phase ${p} dot` });
    T(s, [{ text: `${p}  `, options: { bold: true, color: C.accent1, fontSize: 15 } }, { text: t, options: { color: C.text1 } }],
      { x, y: 5.64, w: 3.9, h: 0.32, fontSize: 14, objectName: `A${11 + i}|Phase ${p} text` });
  });
  R(s, { x: 0.7, y: 6.18, w: 11.93, h: 0.68, fill: C.text2, round: 0.08, objectName: "A14|Closing panel" });
  T(s, "KAVACH — Consent should stay informed, current, and under human control.",
    { x: 1.05, y: 6.18, w: 9.2, h: 0.68, fontSize: 19, color: C.background1, fontFace: THEME.headFontFace, valign: "middle", objectName: "A14|Closing statement" });
  T(s, "Thank you", { x: 10.35, y: 6.18, w: 2.0, h: 0.68, fontSize: 16, bold: true, color: C.accent2, align: "right", valign: "middle", objectName: "A15|Thank you" });
  footer(s, "KAVACH  •  7/7");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
}
build().catch((e) => { console.error(e); process.exit(1); });
