import {GOOGLE_ACCESS} from "./bridge.js";
import {SERVER} from "./config.js";
const $ = id => document.getElementById(id);
$("service-host").textContent = new URL(SERVER).host;
let mcpUrl = "", chatgptUrl = "";
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
    for (const id of ["start", "google", "working", "connected", "approve", "resume", "retry-chatgpt", "done"]) $(id).hidden = id !== state.phase;
    const google = ["start", "google", "working"].includes(state.phase);
    for (const step of ["google", "chatgpt", "ready"]) {
      const selected = step === (state.phase === "done" ? "ready" : google ? "google" : "chatgpt");
      if (selected) $("step-" + step).setAttribute("aria-current", "step");
      else $("step-" + step).removeAttribute("aria-current");
    }
    $("manage").hidden = google;
    $("retry").hidden = true;
    $("invitation-row").hidden = !state.invitationRequired;
    $("invitation").required = !!state.invitationRequired;
    $("heading").textContent = state.phase === "done" ? "Your notes are ready." :
      ["resume", "approve"].includes(state.phase) ? "Ready for ChatGPT." :
      state.phase === "retry-chatgpt" ? "Keep is still connected." :
      state.phase === "connected" ? "One more step." :
      state.phase === "google" ? "Sign in with Google." :
      state.phase === "working" ? "Finishing setup." : "Connect your notes.";
    $("message").textContent = state.phase === "done" ? "Google Keep is connected to ChatGPT." :
      ["resume", "retry-chatgpt"].includes(state.phase) ? "Your Google account is saved." :
      state.phase === "start" ? "Connect your notes once. Ask about them whenever you need." :
      state.phase === "google" ? "Waiting for Google's sign-in…" :
      state.phase === "working" ? "Finishing your connection…" :
      state.phase === "approve" ? "Confirm this connection to " + state.callback + "." :
      "Add Keep Context to ChatGPT to start asking about your notes.";
    for (const id of ["account", "approve-account", "done-account"]) $(id).textContent = state.email || "";
    mcpUrl = state.mcpUrl || ""; chatgptUrl = state.chatgptUrl || "";
    $("mcp-url").value = mcpUrl;
    $("error").hidden = !state.error;
    if (state.error) showError(state.error);
  } catch (error) { showError(error.message); $("retry").hidden = false; }
}
async function act(button, action, values) {
  if (busy) return;
  busy = true; button.disabled = true; $("error").hidden = true;
  try { await send(action, values); }
  catch (error) { showError(error.message); }
  finally { busy = false; button.disabled = false; }
  if ($("error").hidden) await refresh();
}
$("connect-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy || !$("connect-form").reportValidity()) return;
  // Keep the permission request in the user's gesture, before any network await.
  busy = true; $("begin").disabled = true; $("error").hidden = true;
  try {
    if (!await chrome.permissions.request(GOOGLE_ACCESS)) throw new Error("Allow the one-time permission to connect Google Keep.");
    await send("begin", {email: $("email").value, invitation: $("invitation").value, consent: true});
    $("invitation").value = "";
  } catch (error) { showError(error.message); }
  finally { busy = false; $("begin").disabled = false; }
  if ($("error").hidden) await refresh();
});
for (const name of ["google-tab", "allow", "cancel", "restart"]) $(name).addEventListener("click", () => act($(name), name));
$("resume-button").addEventListener("click", () => act($("resume-button"), "resume"));
$("return-chatgpt").addEventListener("click", () => act($("return-chatgpt"), "retry-chatgpt"));
$("retry").addEventListener("click", refresh);
$("connect-chatgpt").addEventListener("click", async () => {
  try {
    if (chatgptUrl) await chrome.tabs.create({url: chatgptUrl});
    else { $("chatgpt-guide").hidden = false; $("copy").focus(); }
  } catch { showError("Could not open ChatGPT. Try the button again."); }
});
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(mcpUrl);
    $("copy").textContent = "Copied. Opening ChatGPT…";
    await chrome.tabs.create({url: "https://chatgpt.com/plugins"});
  } catch { $("mcp-url").focus(); $("mcp-url").select(); showError("Copy the selected address, then open ChatGPT’s Plugins page."); }
});
$("disconnect").addEventListener("click", () => {
  if (confirm("Disconnect Keep and revoke ChatGPT's access? You can sign in again later.")) {
    void act($("disconnect"), "disconnect");
  }
});
void refresh();
setInterval(refresh, 4000);
