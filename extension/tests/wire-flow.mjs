// Protocol integration with a fake browser facade and real TCP server. No browser is launched.
import assert from "node:assert/strict";
import {Bridge} from "../bridge.js";
const server = process.argv[2];
const stores = () => {
  const data = {};
  return {async get(key) {return {[key]: data[key]};}, async set(values) {Object.assign(data, values);},
    async remove(key) {delete data[key];}};
};
let currentTab = {id: 1, url: "https://accounts.google.com/signin"}, cookie;
const chrome = {
  storage: {local: stores(), session: stores()},
  permissions: {async contains() {return true;}, async remove() {}},
  cookies: {async get() {return cookie;}},
  tabs: {async create() {return {id: 1};}, async get() {return currentTab;},
    async query() {return [currentTab];}, async update(id, values) {currentTab = {id, ...values};}},
  alarms: {async create() {}, async clear() {}},
};
const bridge = new Bridge(chrome, fetch, server);
await bridge.begin({email: "fake-user@example.test", consent: true});
cookie = {value: "oauth2_4/fake-only"};
await bridge.finish();
for (let i = 0; i < 100; i++) {
  const state = await bridge.status();
  if (state.phase === "connected") break;
  assert.equal(state.phase, "working");
  await new Promise(resolve => setTimeout(resolve, 20));
}
assert.equal((await bridge.status()).phase, "connected");
async function request(path, options) {
  const response = await fetch(server + path, options);
  assert.ok(response.ok);
  return response.json();
}
const callback = "https://chatgpt.com/connector_platform_oauth_redirect";
const client = await request("/register", {method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({client_name: "Wire flow", redirect_uris: [callback],
    grant_types: ["authorization_code", "refresh_token"], response_types: ["code"],
    token_endpoint_auth_method: "none"})});
const verifier = "v".repeat(64);
const hashed = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
const challenge = btoa(String.fromCharCode(...hashed)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
const query = new URLSearchParams({client_id: client.client_id, redirect_uri: callback,
  response_type: "code", scope: "keep:read", resource: server + "/mcp", state: "fake-state",
  code_challenge: challenge, code_challenge_method: "S256"});
const response = await fetch(server + "/authorize?" + query, {redirect: "manual"});
assert.equal(response.status, 302);
currentTab = {id: 3, url: response.headers.get("location")};
assert.equal((await bridge.status()).phase, "approve");
const nativeFetch = bridge.fetch;
let loseReply = true;
bridge.fetch = async (...args) => {
  const result = await nativeFetch(...args);
  if (String(args[0]).endsWith("/api/approve") && loseReply) {
    loseReply = false;
    throw new Error("Simulated lost response after the real server accepted approval");
  }
  return result;
};
await assert.rejects(() => bridge.decide("allow"), /reach Keep Context/);
assert.equal((await bridge.status()).phase, "resume");
await bridge.decideFlow(currentTab, "allow");
const redirect = new URL(currentTab.url);
assert.equal(redirect.searchParams.get("state"), "fake-state");
const tokens = await request("/token", {method: "POST", body: new URLSearchParams({
  grant_type: "authorization_code", client_id: client.client_id, code_verifier: verifier,
  code: redirect.searchParams.get("code"), redirect_uri: callback, resource: server + "/mcp"})});
const headers = {"Content-Type": "application/json", Accept: "application/json, text/event-stream",
  Authorization: "Bearer " + tokens.access_token};
let id = 0;
async function rpc(method, params) {
  return request("/mcp", {method: "POST", headers, body: JSON.stringify({jsonrpc: "2.0", id: ++id, method, params})});
}
await rpc("initialize", {protocolVersion: "2025-11-25", capabilities: {}, clientInfo: {name: "wire", version: "1"}});
assert.equal((await rpc("tools/list", {})).result.tools.length, 5);
for (const [name, args] of [["search", {query: "Garden"}], ["fetch", {id: "demo-trip"}],
  ["list_recent_notes", {}], ["list_labels", {}], ["find_tasks", {}]]) {
  const result = await rpc("tools/call", {name, arguments: args});
  assert.ok(!result.result.isError && result.result.structuredContent);
  assert.ok(!JSON.stringify(result).includes("fake-master"));
}
await bridge.disconnect();
assert.equal((await fetch(server + "/mcp", {method: "POST", headers, body: "{}"})).status, 401);
console.log("Extension bridge/TCP enrollment, approval, PKCE, five MCP tools and disconnect passed.");
