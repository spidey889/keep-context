import {Bridge, connectionTicket} from "./bridge.js";
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
chrome.runtime.onInstalled.addListener(details => {
  newBrowserSession();
  // Installation is the user's first step. Updates must not open surprise tabs.
  if (details.reason === "install") void ready.then(() => bridge.openSetup()).catch(() => {});
});
chrome.action.onClicked.addListener(tab => {
  void ready.then(() => bridge.openSetup(tab)).catch(() => {});
});

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
  if (sender.id !== chrome.runtime.id) return false;
  const popup = sender.url === chrome.runtime.getURL("popup.html");
  const page = sender.frameId === 0 && Number.isInteger(sender.tab?.id) &&
    connectionTicket(sender.url, bridge.server);
  if (!popup && !page) return false;
  // Chrome supplies sender.tab/url. Never accept a page-supplied tab, ticket,
  // account or redirect. Content scripts cannot read TRUSTED_CONTEXTS storage.
  const tab = page ? {id: sender.tab.id, url: sender.url} : null;
  const calls = popup ? {
    status: () => bridge.status(), begin: () => bridge.begin(message), finish: () => bridge.finish(),
    "google-tab": () => bridge.showGoogle(),
    allow: () => bridge.decide("allow"), cancel: () => bridge.decide("cancel"),
    disconnect: () => bridge.disconnect(), restart: () => bridge.restart(),
    "retry-chatgpt": () => bridge.decide("retry"), resume: () => bridge.decide("allow"),
  } : {
    "flow-status": () => bridge.flowStatus(tab), "flow-setup": () => bridge.flowSetup(tab),
    "flow-allow": () => bridge.decideFlow(tab, "allow"),
    "flow-cancel": () => bridge.decideFlow(tab, "cancel"),
    "flow-retry": () => bridge.decideFlow(tab, "retry"),
  };
  if (!calls[message.action]) return false;
  void ready.then(calls[message.action]).then(reply).catch(error => reply({error: error.message}));
  return true;
});
