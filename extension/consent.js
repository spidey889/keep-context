// Runs only on the configured service's /connect page, in Chrome's isolated
// world. The worker validates the exact sender URL and performs authenticated
// requests; this page receives no management key, Google token or OAuth code.
(() => {
  const $ = id => document.getElementById(id);
  if (!$('flow-panel')) return;
  let busy = false, next = "refresh";
  const primary = $("flow-primary"), cancel = $("flow-cancel");
  async function send(action) {
    const state = await chrome.runtime.sendMessage({action});
    if (!state || state.error) throw new Error(state?.error || "Reopen Keep Context and try again.");
    return state;
  }
  function error(message) {
    $("flow-error").textContent = message;
    $("flow-error").hidden = false;
    primary.textContent = "Try again";
    next = "refresh";
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const state = await send("flow-status");
      $("flow-fallback").hidden = true;
      $("flow-panel").hidden = false;
      $("flow-error").hidden = true;
      $("flow-account").textContent = state.email || "";
      cancel.hidden = state.phase !== "approve";
      primary.hidden = state.phase === "working";
      const choices = {
        start: ["Connect Google Keep once, then approve ChatGPT here.", "Connect Google Keep", "flow-setup"],
        google: ["Finish Google's sign-in. We'll bring you back automatically.", "Open connection progress", "flow-setup"],
        working: ["Checking your Google Keep connection…", "", "refresh"],
        approve: ["Allow ChatGPT to search and read this account's notes? It cannot edit or delete notes.", "Allow ChatGPT", "flow-allow"],
        resume: ["Your approval was saved. Finish returning to ChatGPT.", "Finish ChatGPT connection", "flow-allow"],
        "retry-chatgpt": ["Google Keep is still connected. This ChatGPT request ended; return and click Connect again. No Google sign-in needed.", "Return to ChatGPT", "flow-retry"],
        done: ["ChatGPT is connected. You can now ask about your notes.", "Open ChatGPT", "flow-allow"],
      };
      const [message, label, action] = choices[state.phase] || choices.start;
      $("flow-message").textContent = message + (state.phase === "approve" ?
        " Connection destination: " + state.callback + "." : "");
      primary.textContent = label;
      next = action;
    } catch (failure) {
      $("flow-panel").hidden = false;
      error(failure.message);
    } finally { busy = false; }
  }
  async function act(event, action) {
    // Page scripts cannot approve via element.click()/dispatchEvent().
    if (!event.isTrusted || busy) return;
    if (action === "refresh") return refresh();
    busy = true; primary.disabled = true; cancel.disabled = true;
    try {
      await send(action);
      $("flow-message").textContent = action === "flow-setup" ?
        "Continue in the Keep Context tab. This page will keep your place." : "Returning to ChatGPT…";
    } catch (failure) { error(failure.message); }
    finally { busy = false; primary.disabled = false; cancel.disabled = false; }
  }
  primary.addEventListener("click", event => { void act(event, next); });
  cancel.addEventListener("click", event => { void act(event, "flow-cancel"); });
  void refresh();
  setInterval(() => { void refresh(); }, 4000);
})();
