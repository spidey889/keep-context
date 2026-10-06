import {GOOGLE_ACCESS} from "./bridge.js";
import {SERVER} from "./config.js";
const $ = id => document.getElementById(id);
$("service-host").textContent = new URL(SERVER).host;
let mcpUrl = "";
let busy = false;

function showError(message) { $("error").textContent = message; $("error").hidden = false; }
async function send(action, values = {}) {
  const response = await chrome.runtime.sendMessage({action, ...values});
  if (response.error && !response.phase) throw new Error(response.error);
  return response;
}
async function refresh() {
  if (busy) return;
  try {
    const state = await send("status");
    const phase = state.phase === "done" ? "connected" : state.phase;
    for (const id of ["start", "google", "working", "connected", "approve", "resume", "retry-chatgpt"]) $(id).hidden = id !== phase;
    $("retry").hidden = true;
    $("invitation-row").hidden = !state.invitationRequired;
    $("invitation").required = !!state.invitationRequired;
    $("heading").textContent = state.phase === "done" ? "ChatGPT is connected." :
      ["resume", "approve"].includes(state.phase) ? "Ready for ChatGPT." :
      state.phase === "retry-chatgpt" ? "Keep is still connected." :
      state.phase === "connected" ? "Keep is connected." : "Your notes. Connected.";
    $("message").textContent = state.phase === "done" ? "You can now ask ChatGPT about your notes." :
      ["resume", "retry-chatgpt"].includes(state.phase) ? "Your Google account is saved." :
      state.phase === "start" ? "Sign in once. Find your notes in ChatGPT." :
      state.phase === "google" ? "Sign in in the Google tab you just opened." :
      state.phase === "working" ? "Finishing your connection…" :
      state.phase === "approve" ? "Confirm this connection to " + state.callback + "." :
      "Next, connect ChatGPT to your notes.";
    $("account").textContent = state.email || "";
    $("approve-account").textContent = state.email || "";
    mcpUrl = state.mcpUrl || "";
    $("error").hidden = !state.error;
    if (state.error) showError(state.error);
  } catch (error) { showError(error.message); $("retry").hidden = false; }
}
async function act(button, action, values) {
  busy = true; button.disabled = true; $("error").hidden = true;
  try { await send(action, values); }
  catch (error) { showError(error.message); }
  finally { busy = false; button.disabled = false; }
  if ($("error").hidden) await refresh();
}
$("connect-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!$("connect-form").reportValidity()) return;
  const granted = await chrome.permissions.request(GOOGLE_ACCESS);
  if (!granted) return showError("Allow the one-time permission to connect Google Keep.");
  await act($("begin"), "begin", {email: $("email").value, invitation: $("invitation").value,
    consent: $("consent").checked});
  $("invitation").value = "";
});
for (const name of ["finish", "allow", "cancel", "restart"]) $(name).addEventListener("click", () => act($(name), name));
$("resume-button").addEventListener("click", () => act($("resume-button"), "resume"));
$("return-chatgpt").addEventListener("click", () => act($("return-chatgpt"), "retry-chatgpt"));
$("retry").addEventListener("click", refresh);
$("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(mcpUrl); $("copy").textContent = "Copied ✓"; }
  catch { showError("Couldn't copy. Reopen this popup and try again."); }
});
$("disconnect").addEventListener("click", () => {
  if (confirm("Disconnect Keep and revoke ChatGPT's access? You can sign in again later.")) {
    void act($("disconnect"), "disconnect");
  }
});
void refresh();
setInterval(refresh, 4000);
