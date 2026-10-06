import {test} from "node:test";
import assert from "node:assert/strict";
import {Bridge, allowedCallback, connectionTicket, serverOrigin} from "../bridge.js";

const SERVER = "https://keep.example.test";
const TICKET = "t".repeat(43);

function storage() {
  const values = {};
  return {values, async get(key) { return {[key]: values[key]}; },
    async set(v) {Object.assign(values, v);}, async remove(k) {delete values[k];}};
}
function setup() {
  const requests = [], updates = [];
  const local = storage(), session = storage();
  let cookie = null, allowed = true, progress = {status: "idle"};
  let active = {id: 4, url: SERVER + "/connect?ticket=" + TICKET};
  const chrome = {
    storage: {local, session}, cookies: {async get() {return cookie;}},
    permissions: {async contains() {return allowed;}, async remove() {allowed = false;}},
    tabs: {async create() {return {id: 2};}, async get() {return {url: "https://accounts.google.com/v3/signin"};},
      async query() {return [active];}, async update(id, v) {updates.push([id, v]);}},
    alarms: {async create() {}, async clear() {}},
  };
  const fetch = async (url, options) => {
    requests.push({url, options});
    const path = new URL(url).pathname;
    let data = {};
    if (path === "/api/config") data = {mcp_url: SERVER + "/mcp", invitation_required: false};
    if (path === "/api/progress") data = progress;
    if (path === "/api/pending") data = {email: "alice@example.test", client: "ChatGPT",
      callback: "https://chatgpt.com/connector_platform_oauth_redirect"};
    if (path === "/api/approve") data = {redirect_url: "https://chatgpt.com/connector_platform_oauth_redirect?code=fake-code&state=fake"};
    return {ok: true, async json() {return data;}};
  };
  return {bridge: new Bridge(chrome, fetch, SERVER), chrome, requests, updates,
    setCookie: value => {cookie = value ? {value} : null;},
    setProgress: value => {progress = value;}, setActive: value => {active = value;}};
}

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
  } finally {
    globalThis.chrome = savedChrome;
    globalThis.fetch = savedFetch;
  }
});
