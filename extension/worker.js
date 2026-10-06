import {Bridge} from "./bridge.js";
import {SERVER} from "./config.js";

const bridge = new Bridge(chrome, fetch, SERVER);
let ready = Promise.all([
  chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"}),
  chrome.storage.session.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"}),
]);

function newBrowserSession() {
  // Serialize lifecycle cleanup before popup messages. Do not run it on every
  // worker wake: that could race the user's new optional-permission grant.
  ready = ready.then(() => bridge.browserRestart());
  void ready.catch(() => {});
}
chrome.runtime.onStartup.addListener(newBrowserSession);
chrome.runtime.onInstalled.addListener(newBrowserSession);

const cookieChanged = change => { void ready.then(() => bridge.changed(change)).catch(() => {}); };
function watchGoogleCookie() {
  // Optional APIs can be absent until their permission is granted. Register again
  // after the user's grant and on worker restart; Chrome de-duplicates listeners.
  chrome.cookies?.onChanged?.addListener(cookieChanged);
}
chrome.permissions.onAdded.addListener(watchGoogleCookie);
watchGoogleCookie();
chrome.alarms.onAlarm.addListener(alarm => {
  if (["connection-progress", "connection-expiry"].includes(alarm.name)) {
    void ready.then(() => bridge.status()).catch(() => {});
  }
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL("popup.html")) return false;
  const calls = {
    status: () => bridge.status(), begin: () => bridge.begin(message), finish: () => bridge.finish(),
    allow: () => bridge.decide("allow"), cancel: () => bridge.decide("cancel"),
    disconnect: () => bridge.disconnect(), restart: () => bridge.restart(),
  };
  if (!calls[message.action]) return false;
  void ready.then(calls[message.action]).then(reply).catch(error => reply({error: error.message}));
  return true;
});
