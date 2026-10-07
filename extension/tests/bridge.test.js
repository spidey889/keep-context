import {test} from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import vm from "node:vm";
import {Bridge, allowedCallback, chatgptInstallUrl, connectionTicket, serverOrigin} from "../bridge.js";

const SERVER = "https://keep.example.test";
const TICKET = "t".repeat(43);

function storage() {
  const values = {};
  return {values, async get(key) { return {[key]: values[key]}; },
    async set(v) {Object.assign(values, v);}, async remove(k) {delete values[k];}};
}
function setup() {
  const requests = [], updates = [], created = [], tabs = new Map();
  let nextTab = 10;
  const local = storage(), session = storage();
  let cookie = null, allowed = true, progress = {status: "idle"};
  let active = {id: 4, url: SERVER + "/connect?ticket=" + TICKET};
  tabs.set(active.id, active);
  let pending = {status: "pending", email: "alice@example.test", client: "ChatGPT",
    callback: "https://chatgpt.com/connector_platform_oauth_redirect"};
  const chrome = {
    storage: {local, session}, cookies: {async get() {return cookie;}},
    permissions: {async contains() {return allowed;}, async remove() {allowed = false;}},
    tabs: {async create(values) {const tab = {id: nextTab++, ...values}; tabs.set(tab.id, tab); created.push(tab); return tab;},
      async get(id) {return tabs.get(id);}, async query() {return [active];},
      async update(id, v) {updates.push([id, v]); tabs.set(id, {...tabs.get(id), ...v});}},
    alarms: {async create() {}, async clear() {}},
    runtime: {getURL: path => "chrome-extension://fake-extension-id/" + path},
  };
  const fetch = async (url, options) => {
    requests.push({url, options});
    const path = new URL(url).pathname;
    let data = {};
    if (path === "/api/config") data = {mcp_url: SERVER + "/mcp", invitation_required: false};
    if (path === "/api/progress") data = progress;
    if (path === "/api/connect") {progress = {status: "connecting"}; data = progress;}
    if (path === "/api/pending") data = pending;
    if (path === "/api/approve") data = {redirect_url: "https://chatgpt.com/connector_platform_oauth_redirect?code=fake-code&state=fake"};
    return {ok: true, async json() {return data;}};
  };
  return {bridge: new Bridge(chrome, fetch, SERVER), chrome, requests, updates, created,
    setTab: (id, url) => tabs.set(id, {id, url}),
    setCookie: value => {cookie = value ? {value} : null;},
    setProgress: value => {progress = value;}, setActive: value => {active = value;},
    setPending: value => {pending = value;}};
}

test("ended ChatGPT links keep Google connected and provide recovery", async () => {
  const s = setup();
  const key = "k".repeat(43);
  await s.chrome.storage.local.set({deviceKey: key});
  s.setProgress({status: "connected", email: "alice@example.test"});
  for (const status of ["expired", "unavailable"]) {
    s.setPending({status});
    const state = await s.bridge.status();
    assert.equal(state.phase, "retry-chatgpt");
    assert.equal(s.chrome.storage.local.values.deviceKey, key);
    assert.ok(!JSON.stringify(state).includes(key));
  }
  s.setPending({status: "approved"});
  assert.equal((await s.bridge.status()).phase, "resume");
  s.setPending({status: "completed"});
  assert.equal((await s.bridge.status()).phase, "done");
  assert.equal(s.requests.some(r => r.url.endsWith("/api/connect")), false);
});

test("opening setup reuses only our own tab and preserves a ChatGPT-started connection", async () => {
  const s = setup();
  await s.bridge.openSetup();
  const id = s.chrome.storage.session.values.setupTabId;
  assert.equal(s.created.length, 1);
  await s.bridge.openSetup();
  assert.equal(s.created.length, 1);
  assert.deepEqual(s.updates.at(-1), [id, {active: true}]);
  s.setTab(id, "https://unrelated.example.test/");
  await s.bridge.openSetup({id: 4, url: SERVER + "/connect?ticket=" + TICKET});
  assert.equal(s.created.length, 2);
  assert.deepEqual(s.chrome.storage.session.values.chatgptFlow, {tabId: 4, ticket: TICKET});
  assert.equal(s.updates.filter(([tab]) => tab === id).length, 1);
});

test("sign-in automatically finishes when its cookie event was missed and returns once", async () => {
  const s = setup();
  await s.bridge.openSetup();
  const app = s.chrome.storage.session.values.setupTabId;
  await s.bridge.begin({email: "alice@example.test", consent: true});
  assert.equal((await s.bridge.status()).phase, "google");
  s.setCookie("oauth2_4/fresh-only-fake");
  assert.equal((await s.bridge.status()).phase, "working");
  assert.deepEqual(s.updates.at(-1), [app, {active: true}]);
  assert.equal(s.chrome.storage.session.values.login.submitted, true);
  assert.equal(await s.chrome.permissions.contains(), false);
  await s.bridge.status(); await s.bridge.status();
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 1);
  assert.equal(s.updates.length, 1);
  assert.equal(JSON.stringify(s.chrome.storage).includes("fresh-only-fake"), false);
});

test("automatic return prefers the original consent page without approving it", async () => {
  const s = setup();
  await s.bridge.openSetup({id: 4, url: SERVER + "/connect?ticket=" + TICKET});
  await s.bridge.begin({email: "alice@example.test", consent: true});
  s.setCookie("oauth2_4/fresh-fake");
  await s.bridge.status();
  assert.deepEqual(s.updates.at(-1), [4, {active: true}]);
  assert.equal(s.requests.some(r => r.url.endsWith("/api/approve")), false);
  s.setProgress({status: "connected", email: "alice@example.test"});
  assert.equal((await s.bridge.status()).phase, "approve");
});

test("cookie events recover a lost accepted response without exchanging twice", async () => {
  const s = setup();
  await s.bridge.openSetup();
  await s.bridge.begin({email: "alice@example.test", consent: true});
  s.setCookie("oauth2_4/fresh-fake");
  const fetch = s.bridge.fetch;
  s.bridge.fetch = async (...args) => {
    const reply = await fetch(...args);
    if (String(args[0]).endsWith("/api/connect")) throw new Error("Lost accepted response");
    return reply;
  };
  const change = {removed: false, cookie: {name: "oauth_token", domain: "accounts.google.com"}};
  await s.bridge.changed(change);
  await s.bridge.changed(change);
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 1);
  assert.equal(s.chrome.storage.session.values.login.submitted, true);
  assert.equal(s.updates.length, 1);
  assert.equal(await s.chrome.permissions.contains(), false);
});

test("return never focuses repurposed setup/consent tabs", async () => {
  const s = setup();
  await s.bridge.openSetup({id: 4, url: SERVER + "/connect?ticket=" + TICKET});
  const id = s.chrome.storage.session.values.setupTabId;
  await s.bridge.begin({email: "alice@example.test", consent: true});
  s.setTab(id, "https://unrelated.example.test/"); s.setTab(4, "https://unrelated.example.test/");
  s.setCookie("oauth2_4/fresh-fake");
  await s.bridge.status();
  assert.equal(s.updates.length, 0);
});

test("installed ChatGPT links are validated and only an issued grant shows ready", async () => {
  const listing = "https://chatgpt.com/plugins/keep-context-example";
  assert.equal(chatgptInstallUrl(listing), listing);
  for (const url of ["https://chatgpt.com.evil.test/plugins/a", "javascript:alert(1)",
    "https://chatgpt.com/plugins/a?token=fake", "https://chatgpt.com/connector/oauth/a",
    "https://user@chatgpt.com/plugins/a", "http://chatgpt.com/plugins/a"]) assert.throws(() => chatgptInstallUrl(url));
  const s = setup();
  s.setActive({id: 99, url: "https://unrelated.example.test/"});
  await s.chrome.storage.local.set({deviceKey: "k".repeat(43)});
  s.setProgress({status: "connected", email: "alice@example.test", chatgpt_connected: false});
  assert.equal((await s.bridge.status()).phase, "connected");
  s.setProgress({status: "connected", email: "alice@example.test", chatgpt_connected: true});
  assert.equal((await s.bridge.status()).phase, "done");
});

test("setup in a separate tab retains the exact ChatGPT flow and rejects a changed tab", async () => {
  const s = setup();
  const source = {id: 42, url: SERVER + "/connect?ticket=" + TICKET};
  await s.bridge.flowSetup(source);
  assert.deepEqual(s.chrome.storage.session.values.chatgptFlow, {tabId: 42, ticket: TICKET});
  s.setActive({id: 2, url: s.chrome.runtime.getURL("popup.html")});
  s.chrome.tabs.get = async () => source;
  await s.chrome.storage.local.set({deviceKey: "k".repeat(43)});
  s.setProgress({status: "connected", email: "alice@example.test"});
  assert.equal((await s.bridge.status()).phase, "approve");
  s.chrome.tabs.get = async () => ({id: 42, url: "https://unrelated.example.test/"});
  assert.equal((await s.bridge.status()).phase, "connected");
  assert.equal(s.chrome.storage.session.values.chatgptFlow, undefined);
  await assert.rejects(() => s.bridge.flowSetup({id: 42, url: "https://evil.example.test/"}));
});

test("only configured origins and ChatGPT callbacks are accepted", () => {
  assert.equal(serverOrigin(SERVER), SERVER);
  for (const url of ["http://evil.test", SERVER + "/path", "https://user:pw@keep.test", SERVER + "?x=1"]) {
    assert.throws(() => serverOrigin(url));
  }
  assert.equal(connectionTicket(SERVER + "/connect?ticket=" + TICKET, SERVER), TICKET);
  assert.equal(connectionTicket("https://evil.test/connect?ticket=" + TICKET, SERVER), null);
  assert.equal(allowedCallback("https://chatgpt.com/connector/oauth/xyz?code=a"), true);
  for (const url of ["https://chatgpt.com.evil.test/connector/oauth/a", "javascript:alert(1)",
    "http://chatgpt.com/connector/oauth/a", "https://chatgpt.com/wrong"]) assert.equal(allowedCallback(url), false);
});

test("service preflight preserves the browser fetch receiver", async () => {
  const s = setup();
  let calls = 0;
  const browserFetch = async function (url, options) {
    // Native browser fetch requires its Window/Worker receiver; Node fetch does not.
    if (this !== globalThis) throw new TypeError("Illegal invocation");
    calls++;
    assert.equal(url, SERVER + "/api/config");
    assert.equal(options.credentials, "omit");
    return {ok: true, async json() {return {mcp_url: SERVER + "/mcp"};}};
  };
  const bridge = new Bridge(s.chrome, browserFetch, SERVER);
  assert.deepEqual(await bridge.request("/api/config"), {mcp_url: SERVER + "/mcp"});
  assert.equal(calls, 1);
});

test("onboarding sends only a fresh explicitly approved Google token and never stores it", async () => {
  const s = setup();
  s.setCookie("oauth2_4/old-fake-value");
  await assert.rejects(() => s.bridge.begin({email: "alice@example.test", consent: false}), /Approve/);
  await s.bridge.begin({email: "alice@example.test", consent: true});
  await assert.rejects(() => s.bridge.finish(), /Finish signing in/);
  s.setCookie("oauth2_4/fresh-fake-value");
  assert.deepEqual(await s.bridge.finish(), {phase: "working"});
  const call = s.requests.find(r => r.url.endsWith("/api/connect"));
  const body = JSON.parse(call.options.body);
  assert.equal(body.cookie, "oauth2_4/fresh-fake-value");
  assert.equal(body.device_key.length, 43);
  assert.equal(call.options.credentials, "omit");
  assert.equal(call.options.redirect, "error");
  assert.equal(JSON.stringify(s.chrome.storage).includes("fresh-fake-value"), false);
  assert.equal(JSON.stringify(s.chrome.storage).includes("old-fake-value"), false);
  s.setProgress({status: "connecting"});
  assert.deepEqual(await s.bridge.status(), {phase: "working"});
});

test("reopened popup restores connection progress and approval never returns a secret", async () => {
  const s = setup();
  await s.chrome.storage.local.set({deviceKey: "a".repeat(43)});
  s.setProgress({status: "connected", email: "alice@example.test"});
  const status = await s.bridge.status();
  assert.equal(status.phase, "approve");
  assert.equal(status.email, "alice@example.test");
  assert.equal(JSON.stringify(status).includes("a".repeat(43)), false);
  await s.bridge.decide("allow");
  assert.equal(s.updates.length, 1);
  assert.equal(new URL(s.updates[0][1].url).host, "chatgpt.com");
});

test("cookie events outside an active sign-in are ignored", async () => {
  const s = setup();
  for (const domain of ["accounts.google.com", "evil.test"]) {
    await s.bridge.changed({removed: false, cookie: {name: "oauth_token", domain, value: "fake"}});
  }
  assert.equal(s.requests.length, 0);
  await s.bridge.begin({email: "alice@example.test", consent: true});
  s.setCookie("oauth2_4/fake-new");
  await s.bridge.changed({removed: false, cookie: {name: "oauth_token", domain: "accounts.google.com"}});
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 1);
  await s.bridge.changed({removed: false, cookie: {name: "oauth_token", domain: "accounts.google.com"}});
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 1);
});

test("failed connections keep the retry safe and disconnect revokes before local cleanup", async () => {
  const s = setup();
  await s.chrome.storage.local.set({deviceKey: "b".repeat(43)});
  s.setProgress({status: "failed", error: "Sign in again."});
  assert.equal((await s.bridge.status()).phase, "start");
  assert.equal(s.chrome.storage.local.values.deviceKey, "b".repeat(43));
  await s.bridge.disconnect();
  assert.equal(s.chrome.storage.local.values.deviceKey, undefined);
  assert.equal(s.requests.find(r => r.url.endsWith("/api/disconnect")).options.headers.Authorization,
    "Bearer " + "b".repeat(43));
});

test("approval on an unrelated tab cannot call the server", async () => {
  const s = setup(); s.setActive({id: 1, url: "https://evil.test/connect?ticket=" + TICKET});
  await assert.rejects(() => s.bridge.decide("allow"), /fresh connection tab/);
  assert.equal(s.requests.length, 0);
});

test("network errors never echo raw upstream details", async () => {
  const s = setup();
  s.bridge.fetch = async () => {throw new Error("sensitive-token-fake-only");};
  await assert.rejects(() => s.bridge.status(), error => !error.message.includes("sensitive-token"));
});

test("expired sign-in drops Google permission even while the host is offline", async () => {
  const s = setup();
  await s.bridge.begin({email: "alice@example.test", consent: true});
  const login = s.chrome.storage.session.values.login;
  s.bridge.now = () => login.started + 10 * 60 * 1000;
  s.bridge.fetch = async () => {throw new Error("offline");};
  await assert.rejects(() => s.bridge.status(), /reach Keep Context/);
  assert.equal(s.chrome.storage.session.values.login, undefined);
  assert.equal(await s.chrome.permissions.contains(), false);
  // The expiry path never tries to read/submit the old Google cookie.
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 0);
});

test("a lost setup response recovers without another Google sign-in or cookie read", async () => {
  const s = setup();
  await s.bridge.begin({email: "alice@example.test", invitation: "fake-invite", consent: true});
  s.setProgress({status: "connecting"});
  assert.equal((await s.bridge.status()).phase, "working");
  assert.equal(s.chrome.storage.session.values.login.invitation, "");
  assert.equal(await s.chrome.permissions.contains(), false);
  s.chrome.cookies.get = async () => {throw new Error("Cookie access should be gone");};
  assert.equal((await s.bridge.finish()).phase, "working");
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 0);
});

test("start over recovers an abandoned sign-in but preserves a submitted connection", async () => {
  const s = setup();
  await s.bridge.begin({email: "alice@example.test", consent: true});
  const key = s.chrome.storage.local.values.deviceKey;
  assert.equal((await s.bridge.restart()).phase, "start");
  assert.equal(s.chrome.storage.session.values.login, undefined);
  assert.equal(s.chrome.storage.local.values.deviceKey, key);
  assert.equal(await s.chrome.permissions.contains(), false);
  s.setProgress({status: "connecting"});
  assert.equal((await s.bridge.restart()).phase, "working");
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/disconnect")).length, 0);
});

test("server restart during unverified setup offers a fresh sign-in instead of spinning", async () => {
  const s = setup();
  await s.bridge.begin({email: "alice@example.test", consent: true});
  s.setCookie("oauth2_4/fake-new");
  await s.bridge.finish();
  s.setProgress({status: "idle"});
  const state = await s.bridge.status();
  assert.equal(state.phase, "start");
  assert.match(state.error, /interrupted/);
  assert.equal(s.chrome.storage.session.values.login, undefined);
  assert.equal(s.requests.filter(r => r.url.endsWith("/api/connect")).length, 1);
});

test("failure before Google sign-in releases permission without losing the browser key", async () => {
  const s = setup();
  await s.chrome.storage.local.set({deviceKey: "c".repeat(43)});
  s.bridge.fetch = async () => {throw new Error("offline-fake-only");};
  await assert.rejects(() => s.bridge.begin({email: "alice@example.test", consent: true}));
  assert.equal(await s.chrome.permissions.contains(), false);
  assert.equal(s.chrome.storage.session.values.login, undefined);
  assert.equal(s.chrome.storage.local.values.deviceKey, "c".repeat(43));
});

test("partial browser setup failure releases permission and temporary session data", async () => {
  const s = setup();
  s.chrome.alarms.create = async () => {throw new Error("browser-api-failure-fake-only");};
  await assert.rejects(() => s.bridge.begin({email: "alice@example.test", consent: true}));
  assert.equal(await s.chrome.permissions.contains(), false);
  assert.equal(s.chrome.storage.session.values.login, undefined);
});

test("browser restart clears sign-in permission offline and preserves a verified account", async () => {
  const s = setup();
  const key = "d".repeat(43);
  await s.chrome.storage.local.set({deviceKey: key});
  await s.chrome.storage.session.set({login: {email: "alice@example.test", invitation: "fake"}});
  s.bridge.fetch = async () => {throw new Error("offline-fake-only");};
  await s.bridge.browserRestart();
  assert.equal(await s.chrome.permissions.contains(), false);
  assert.equal(s.chrome.storage.session.values.login, undefined);
  assert.equal(s.chrome.storage.local.values.deviceKey, key);
  assert.equal(s.requests.length, 0);
});

test("real worker lifecycle wiring cleans offline grants before popup recovery", async () => {
  const s = setup();
  const key = "e".repeat(43);
  await s.chrome.storage.local.set({deviceKey: key});
  s.setProgress({status: "connected", email: "alice@example.test"});
  s.setActive({id: 1, url: "https://unrelated.example.test/"});
  const event = () => ({listeners: [], addListener(fn) {this.listeners.push(fn);}});
  s.chrome.runtime = {id: "fake-extension-id", getURL: path => "chrome-extension://fake-extension-id/" + path,
    onStartup: event(), onInstalled: event(), onMessage: event()};
  s.chrome.permissions.onAdded = event();
  s.chrome.action = {onClicked: event()};
  s.chrome.alarms.onAlarm = event();
  s.chrome.cookies.onChanged = event();
  s.chrome.storage.local.setAccessLevel = s.chrome.storage.session.setAccessLevel = async () => {};
  const savedChrome = globalThis.chrome, savedFetch = globalThis.fetch;
  let online = false;
  globalThis.chrome = s.chrome;
  globalThis.fetch = async (...args) => {
    if (!online) throw new Error("offline-fake-only");
    return s.bridge.fetch(...args);
  };
  try {
    await import("../worker.js?lifecycle-test");
    const send = () => new Promise(resolve => {
      const accepted = s.chrome.runtime.onMessage.listeners[0]({action: "status"},
        {id: s.chrome.runtime.id, url: s.chrome.runtime.getURL("popup.html")}, resolve);
      assert.equal(accepted, true);
    });
    s.chrome.runtime.onStartup.listeners[0]();
    assert.match((await send()).error, /reach Keep Context/);
    assert.equal(await s.chrome.permissions.contains(), false);
    assert.equal(s.chrome.storage.local.values.deviceKey, key);
    online = true;
    const state = await send();
    assert.equal(state.phase, "connected");
    assert.equal(JSON.stringify(state).includes(key), false);
    assert.equal(s.requests.some(r => r.url.endsWith("/api/connect")), false);
    // An extension update/reload must clean the same stale permission state.
    assert.equal(s.chrome.runtime.onInstalled.listeners.length, 1);
    s.chrome.runtime.onInstalled.listeners[0]({reason: "update"});
    await send();
    assert.equal(s.created.length, 0);
    s.chrome.runtime.onInstalled.listeners[0]({reason: "install"});
    await send();
    assert.equal(s.created.length, 1);
    assert.equal(s.created[0].url, s.chrome.runtime.getURL("popup.html"));
    s.chrome.action.onClicked.listeners[0]({id: 1, url: "https://unrelated.example.test/"});
    await send();
    assert.equal(s.created.length, 1);
  } finally {
    globalThis.chrome = savedChrome;
    globalThis.fetch = savedFetch;
  }
});

test("inline approval accepts only the service's top-level sender and never returns secrets", async () => {
  const s = setup();
  const key = "z".repeat(43);
  await s.chrome.storage.local.set({deviceKey: key});
  s.setProgress({status: "connected", email: "alice@example.test"});
  const event = () => ({listeners: [], addListener(fn) {this.listeners.push(fn);}});
  s.chrome.runtime = {id: "fake-extension-id", getURL: path => "chrome-extension://fake-extension-id/" + path,
    onStartup: event(), onInstalled: event(), onMessage: event()};
  s.chrome.permissions.onAdded = event(); s.chrome.alarms.onAlarm = event();
  s.chrome.action = {onClicked: event()};
  s.chrome.cookies.onChanged = event();
  s.chrome.storage.local.setAccessLevel = s.chrome.storage.session.setAccessLevel = async () => {};
  const savedChrome = globalThis.chrome, savedFetch = globalThis.fetch;
  globalThis.chrome = s.chrome; globalThis.fetch = s.bridge.fetch;
  try {
    await import("../worker.js?inline-test");
    const {SERVER: workerServer} = await import("../config.js");
    const listener = s.chrome.runtime.onMessage.listeners[0];
    const sender = {id: s.chrome.runtime.id, frameId: 0, tab: {id: 9},
      url: workerServer + "/connect?ticket=" + TICKET};
    for (const wrong of [{...sender, frameId: 1}, {...sender, id: "other-extension"},
      {...sender, url: "https://evil.example.test/connect?ticket=" + TICKET}]) {
      assert.equal(listener({action: "flow-allow"}, wrong, () => assert.fail("wrong sender replied")), false);
    }
    assert.equal(listener({action: "begin", email: "spoof@example.test"}, sender, () => {}), false);
    const send = action => new Promise(resolve => {
      assert.equal(listener({action, ticket: "spoofed", tab: {id: 77}}, sender, resolve), true);
    });
    assert.equal((await send("flow-status")).phase, "approve");
    const result = await send("flow-allow");
    assert.equal(result.phase, "connected");
    assert.equal(s.updates[0][0], 9);
    const approved = s.requests.find(r => r.url.endsWith("/api/approve"));
    assert.equal(JSON.parse(approved.options.body).ticket, TICKET);
    assert.equal(JSON.stringify(result).includes("fake-code"), false);
    assert.equal(JSON.stringify(result).includes(key), false);
  } finally { globalThis.chrome = savedChrome; globalThis.fetch = savedFetch; }
});

test("connection page renders inline approval and ignores synthetic clicks", async () => {
  const elements = {};
  for (const id of ["flow-panel", "flow-primary", "flow-cancel", "flow-fallback",
    "flow-message", "flow-account", "flow-error"]) {
    elements[id] = {hidden: true, listeners: {}, addEventListener(name, listener) {this.listeners[name] = listener;}};
  }
  const actions = [];
  let phase = "approve", poll;
  const settle = async () => {for (let i = 0; i < 4; i++) await new Promise(setImmediate);};
  const source = await readFile(new URL("../consent.js", import.meta.url), "utf8");
  vm.runInNewContext(source, {
    document: {getElementById: id => elements[id]},
    chrome: {runtime: {async sendMessage(message) {
      actions.push(message.action);
      return {phase, email: "alice@example.test", callback: "chatgpt.com"};
    }}}, setInterval: callback => {poll = callback;},
  });
  await settle();
  assert.equal(elements["flow-primary"].textContent, "Allow ChatGPT");
  assert.equal(elements["flow-account"].textContent, "alice@example.test");
  elements["flow-primary"].listeners.click({isTrusted: false});
  await settle();
  assert.deepEqual(actions, ["flow-status"]);
  elements["flow-primary"].listeners.click({isTrusted: true});
  await settle();
  assert.deepEqual(actions, ["flow-status", "flow-allow"]);
  phase = "retry-chatgpt"; poll(); await settle();
  assert.equal(elements["flow-primary"].textContent, "Return to ChatGPT");
  assert.match(elements["flow-message"].textContent, /No Google sign-in needed/);
});

test("setup page guides missing install links and requires one explicit Google action", async () => {
  const html = await readFile(new URL("../popup.html", import.meta.url), "utf8");
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(([, id]) => [id, {
    hidden: true, listeners: {}, value: "", addEventListener(name, fn) {this.listeners[name] = fn;},
    setAttribute() {}, removeAttribute() {}, focus() {}, select() {}, reportValidity() {return true;},
  }]));
  const sent = [], opened = [];
  let phase = "connected", chatgptUrl = "", poll, permit, permissionCalls = 0;
  const settle = async () => {for (let i = 0; i < 4; i++) await new Promise(setImmediate);};
  const source = (await readFile(new URL("../popup.js", import.meta.url), "utf8")).replace(/^import .*;\r?\n/gm, "");
  vm.runInNewContext(source, {
    SERVER, URL, GOOGLE_ACCESS: {}, confirm: () => true,
    document: {getElementById: id => elements[id]}, navigator: {clipboard: {async writeText() {}}},
    chrome: {runtime: {async sendMessage(message) {sent.push(message); return {phase, chatgptUrl, mcpUrl: SERVER + "/mcp"};}},
      tabs: {async create(values) {opened.push(values);}},
      permissions: {request() {permissionCalls++; return new Promise(resolve => {permit = resolve;});}}},
    setInterval: callback => {poll = callback;},
  });
  await settle();
  assert.equal(elements.connected.hidden, false);
  await elements["connect-chatgpt"].listeners.click();
  assert.equal(elements["chatgpt-guide"].hidden, false);
  assert.equal(opened.length, 0);
  chatgptUrl = "https://chatgpt.com/plugins/keep-context-example";
  await poll();
  await elements["connect-chatgpt"].listeners.click();
  assert.deepEqual(opened[0].url, chatgptUrl);
  phase = "start"; await poll();
  elements.email.value = "alice@example.test";
  const event = {preventDefault() {}};
  const first = elements["connect-form"].listeners.submit(event);
  await elements["connect-form"].listeners.submit(event);
  assert.equal(permissionCalls, 1);
  assert.equal(sent.filter(m => m.action === "begin").length, 0);
  permit(true); await first;
  assert.equal(sent.filter(m => m.action === "begin").length, 1);
  assert.equal(sent.find(m => m.action === "begin").consent, true);
  phase = "done"; await poll();
  assert.equal(elements.done.hidden, false);
  assert.equal(elements.connected.hidden, true);
  assert.equal(elements.heading.textContent, "Your notes are ready.");
});
