const $ = (id) => document.getElementById(id);

async function showState() {
  const s = await settings();
  if (!s.key) {
    $("state").textContent = "Not connected. Open Kavach at the address below while signed in, and this browser connects by itself.";
    return;
  }
  const me = await call("/ext/me");
  $("state").textContent = me.error === "OFFLINE" ? `Connected as ${s.email}, but Kavach is unreachable right now.`
    : me.error ? "The connection was replaced or removed. Open Kavach while signed in to reconnect."
    : `Connected as ${me.email}.`;
}

(async () => {
  const s = await settings();
  $("server").value = s.server;
  $("excluded").value = s.excluded.join("\n");
  showState();
})();

$("save").onclick = async () => {
  const excluded = $("excluded").value.split(/\s+/).map((d) => d.trim().toLowerCase()).filter(Boolean);
  const server = $("server").value.trim() || DEFAULTS.server;
  const before = await settings();
  // A different Kavach address means a different account store: connect again from there.
  await chrome.storage.local.set({ server, excluded, ...(server !== before.server ? { key: "", email: "" } : {}) });
  await chrome.storage.session.clear();
  $("msg").textContent = "Saved.";
  showState();
};

$("disconnect").onclick = async () => {
  await chrome.storage.local.set({ key: "", email: "" });
  await chrome.storage.session.clear();
  $("msg").textContent = "Disconnected. Open Kavach to connect again.";
  showState();
};
