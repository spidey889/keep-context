export const GOOGLE = "https://accounts.google.com/EmbeddedSetup";
export const GOOGLE_ACCESS = {permissions: ["cookies"], origins: ["https://accounts.google.com/*"]};

export function serverOrigin(value) {
  const url = new URL(value);
  if (url.username || url.password || url.search || url.hash || !["", "/"].includes(url.pathname) ||
      (url.protocol !== "https:" && !(url.protocol === "http:" && url.hostname === "127.0.0.1"))) {
    throw new Error("This extension has an invalid server configuration.");
  }
  return url.origin;
}

export function connectionTicket(value, server) {
  try {
    const url = new URL(value);
    const ticket = url.searchParams.get("ticket");
    return url.origin === server && url.pathname === "/connect" && /^[\w-]{43}$/.test(ticket || "")
      ? ticket : null;
  } catch { return null; }
}

export function allowedCallback(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.host === "chatgpt.com" && !url.username && !url.password &&
      !url.hash && (url.pathname === "/connector_platform_oauth_redirect" ||
       /^\/connector\/oauth\/[^/]+$/.test(url.pathname));
  } catch { return false; }
}

export function chatgptInstallUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value);
    if (url.protocol === "https:" && url.host === "chatgpt.com" && !url.username &&
        !url.password && !url.search && !url.hash &&
        ["/plugins/", "/apps/", "/settings/plugins-settings/"].some(p => url.pathname.startsWith(p)) &&
        !url.pathname.includes("oauth")) return url.href;
  } catch { /* Reject untrusted configuration without echoing its contents. */ }
  throw new Error("The ChatGPT install link is invalid. Contact the host.");
}

export class Bridge {
  constructor(chrome, fetch, server, crypto = globalThis.crypto, now = () => Date.now()) {
    // Native browser fetch rejects a Bridge receiver ("Illegal invocation").
    // Keep the worker global as its receiver; Node fetch/mocks do not enforce this.
    this.chrome = chrome; this.fetch = fetch.bind(globalThis); this.server = serverOrigin(server);
    this.crypto = crypto; this.now = now; this.inFlight = false;
  }

  async request(path, body, authenticated = false) {
    const headers = {"Content-Type": "application/json"};
    if (authenticated) {
      const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
      if (!deviceKey) throw new Error("Connect Google Keep first.");
      headers.Authorization = "Bearer " + deviceKey;
    }
    let response;
    try {
      response = await this.fetch(this.server + path, {
        method: body === undefined ? "GET" : "POST", headers,
        ...(body === undefined ? {} : {body: JSON.stringify(body)}),
        cache: "no-store", credentials: "omit", redirect: "error",
        signal: AbortSignal.timeout(15000),
      });
    } catch { throw new Error("Can't reach Keep Context. Check your internet and try again."); }
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The connection service is unavailable. Try again shortly."); }
    if (!response.ok) throw new Error(data.error || "Connection could not finish. Try again.");
    return data;
  }

  async hash(value) {
    const bytes = await this.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, "0")).join("");
  }

  async newKey() {
    const bytes = this.crypto.getRandomValues(new Uint8Array(32));
    const key = btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_")
      .replaceAll("=", "");
    await this.chrome.storage.local.set({deviceKey: key});
    return key;
  }

  async openSetup(source = null) {
    const ticket = connectionTicket(source?.url, this.server);
    if (ticket) await this.chrome.storage.session.set({chatgptFlow: {tabId: source.id, ticket}});
    const {setupTabId} = await this.chrome.storage.session.get("setupTabId");
    const saved = Number.isInteger(setupTabId)
      ? await this.chrome.tabs.get(setupTabId).catch(() => null) : null;
    const url = this.chrome.runtime.getURL("popup.html");
    if (saved?.url === url) await this.chrome.tabs.update(saved.id, {active: true});
    else {
      const tab = await this.chrome.tabs.create({url});
      await this.chrome.storage.session.set({setupTabId: tab.id});
    }
    return {phase: "start"};
  }

  async returnAfterSignIn(login) {
    if (!login || login.returned) return;
    // Focus only our own setup or the exact saved consent page, never an arbitrary
    // active tab. Google can keep spinning after its cookie has already arrived.
    const {chatgptFlow} = await this.chrome.storage.session.get("chatgptFlow");
    const source = chatgptFlow && await this.chrome.tabs.get(chatgptFlow.tabId).catch(() => null);
    if (source && connectionTicket(source.url, this.server) === chatgptFlow.ticket) {
      await this.chrome.tabs.update(source.id, {active: true});
    } else {
      const setup = Number.isInteger(login.setupTabId)
        ? await this.chrome.tabs.get(login.setupTabId).catch(() => null) : null;
      if (!setup || setup.url !== this.chrome.runtime.getURL("popup.html")) return;
      await this.chrome.tabs.update(setup.id, {active: true});
    }
    const {login: current} = await this.chrome.storage.session.get("login");
    if (current?.started === login.started) {
      await this.chrome.storage.session.set({login: {...current, returned: true}});
    }
  }

  async begin({email, invitation = "", consent}) {
    if (consent !== true) throw new Error("Approve the connection permission first.");
    email = String(email || "").trim();
    if (!/^[^\s@]+@[^\s@]+$/.test(email) || email.length > 254) {
      throw new Error("Enter the Google email you want to connect.");
    }
    if (!(await this.chrome.permissions.contains(GOOGLE_ACCESS))) {
      throw new Error("Allow the one-time Google sign-in permission.");
    }
    try {
      await this.request("/api/config");
      const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
      if (!deviceKey) await this.newKey();
      const old = await this.chrome.cookies.get({url: GOOGLE, name: "oauth_token"});
      const {setupTabId} = await this.chrome.storage.session.get("setupTabId");
      const tab = await this.chrome.tabs.create({url: GOOGLE});
      await this.chrome.storage.session.set({login: {
        email, invitation, tabId: tab.id, started: this.now(), baseline: await this.hash(old?.value || ""),
        ...(Number.isInteger(setupTabId) ? {setupTabId} : {}),
      }});
      // The worker may be asleep when the ten-minute connection window ends.
      await this.chrome.alarms.create("connection-expiry", {delayInMinutes: 10});
      return {phase: "google"};
    } catch {
      // A grant can precede a network/browser failure. Release it even if setup
      // never reached the session/alarm checkpoint; preserve the management key.
      await Promise.allSettled([
        this.chrome.permissions.remove(GOOGLE_ACCESS),
        this.chrome.storage.session.remove("login"),
        this.chrome.alarms.clear("connection-expiry"),
      ]);
      throw new Error("Couldn't start Google sign-in. Check your connection and try again.");
    }
  }

  async browserRestart() {
    // Chrome clears session storage on profile restart and extension updates.
    // Optional grants can survive, so clean them without depending on the host.
    await this.chrome.permissions.remove(GOOGLE_ACCESS);
    await this.chrome.storage.session.remove("login");
    await this.chrome.alarms.clear("connection-expiry");
    const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
    if (deviceKey) await this.chrome.alarms.create("connection-progress", {periodInMinutes: 0.5});
  }

  async finish() {
    if (this.inFlight) return {phase: "working"};
    const {login} = await this.chrome.storage.session.get("login");
    if (login?.submitted) return {phase: "working"};
    if (!login || this.now() - login.started >= 10 * 60 * 1000) {
      throw new Error("Start Google sign-in again. Your connection window has expired.");
    }
    const tab = await this.chrome.tabs.get(login.tabId).catch(() => null);
    if (!tab?.url || new URL(tab.url).origin !== "https://accounts.google.com") {
      throw new Error("Google sign-in was closed. Choose Start over to try again.");
    }
    const cookie = await this.chrome.cookies.get({url: GOOGLE, name: "oauth_token"});
    if (!cookie || !/^oauth2_\d+\/\S+$/.test(cookie.value) ||
        await this.hash(cookie.value) === login.baseline) {
      throw new Error("Finish signing in with Google first. A loading screen after I agree is okay.");
    }
    this.inFlight = true;
    try {
      const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
      await this.request("/api/connect", {email: login.email, cookie: cookie.value,
        device_key: deviceKey, invitation: login.invitation});
      await this.chrome.storage.session.set({login: {...login, submitted: true, invitation: ""}});
      // Drop cookie/host privileges immediately; Keep credentials stay on the encrypted host.
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.alarms.clear("connection-expiry");
      await this.chrome.alarms.create("connection-progress", {periodInMinutes: 0.5});
      await this.returnAfterSignIn(login);
      return {phase: "working"};
    } finally { this.inFlight = false; }
  }

  async changed(change) {
    if (change.removed || change.cookie.name !== "oauth_token" ||
        change.cookie.domain.replace(/^\./, "") !== "accounts.google.com") return;
    const {login} = await this.chrome.storage.session.get("login");
    if (!login || login.submitted) return;
    // Check server progress first: a lost POST reply may already have consumed
    // the cookie. Events and polling must share the same recovery path.
    try { await this.status(); }
    catch { /* Polling recovers missed events/lost replies; never log Google data. */ }
  }

  async activeFlow() {
    const [tab] = await this.chrome.tabs.query({active: true, currentWindow: true});
    const ticket = connectionTicket(tab?.url, this.server);
    if (ticket) return {tab, ticket};
    const {chatgptFlow} = await this.chrome.storage.session.get("chatgptFlow");
    if (!chatgptFlow) return null;
    const saved = await this.chrome.tabs.get(chatgptFlow.tabId).catch(() => null);
    if (connectionTicket(saved?.url, this.server) === chatgptFlow.ticket) {
      return {tab: saved, ticket: chatgptFlow.ticket};
    }
    await this.chrome.storage.session.remove("chatgptFlow");
    return null;
  }

  async readFlow(flow, email, mcpUrl) {
    const details = await this.request("/api/pending", {ticket: flow.ticket}, true);
    const base = {email, mcpUrl};
    if (details.status === "completed") return {...base, phase: "done"};
    if (details.status === "approved") return {...base, phase: "resume"};
    if (["expired", "unavailable"].includes(details.status)) {
      return {...base, phase: "retry-chatgpt",
        message: "Google Keep is still connected. Return to ChatGPT and click Connect again."};
    }
    return {...base, phase: "approve", client: details.client,
      callback: new URL(details.callback).host};
  }

  async flowStatus(tab) {
    const ticket = connectionTicket(tab?.url, this.server);
    if (!ticket) throw new Error("Open the connection page from ChatGPT.");
    return this.status({tab, ticket});
  }

  async flowSetup(tab) {
    const ticket = connectionTicket(tab?.url, this.server);
    if (!ticket) throw new Error("Open the connection page from ChatGPT.");
    return this.openSetup(tab);
  }

  async status(providedFlow = null) {
    let {login} = await this.chrome.storage.session.get("login");
    const expired = login && !login.submitted && this.now() - login.started >= 10 * 60 * 1000;
    // Release expired cookie privileges even if the service is currently offline.
    if (expired) {
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.storage.session.remove("login");
      await this.chrome.alarms.clear("connection-expiry");
      login = null;
    }
    const config = await this.request("/api/config");
    const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
    if (!deviceKey) return {phase: "start", invitationRequired: config.invitation_required};
    const state = await this.request("/api/progress", undefined, true);
    if (state.status === "connected") {
      await this.chrome.storage.session.remove("login");
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.alarms.clear("connection-progress");
      await this.chrome.alarms.clear("connection-expiry");
      await this.returnAfterSignIn(login);
      const flow = providedFlow || await this.activeFlow();
      if (flow) return this.readFlow(flow, state.email, config.mcp_url);
      return {phase: state.chatgpt_connected ? "done" : "connected", email: state.email,
        mcpUrl: config.mcp_url, chatgptUrl: chatgptInstallUrl(config.chatgpt_url)};
    }
    if (state.status === "connecting") {
      // The server may have accepted setup even when the POST response was lost.
      if (login) await this.chrome.storage.session.set({login: {...login, submitted: true, invitation: ""}});
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.alarms.clear("connection-expiry");
      await this.chrome.alarms.create("connection-progress", {periodInMinutes: 0.5});
      await this.returnAfterSignIn(login);
      return {phase: "working"};
    }
    if (state.status === "failed") {
      await this.chrome.alarms.clear("connection-progress");
      await this.chrome.alarms.clear("connection-expiry");
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.storage.session.remove("login");
      return {phase: "start", error: state.error, invitationRequired: config.invitation_required};
    }
    if (login?.submitted) {
      // Unverified jobs are intentionally ephemeral. A server restart must not
      // leave the popup spinning or try a now-consumed cookie a second time.
      await this.chrome.storage.session.remove("login");
      await this.chrome.permissions.remove(GOOGLE_ACCESS);
      await this.chrome.alarms.clear("connection-progress");
      await this.chrome.alarms.clear("connection-expiry");
      return {phase: "start", invitationRequired: config.invitation_required,
        error: "Setup was interrupted. Sign in with Google again."};
    }
    if (login && await this.chrome.permissions.contains(GOOGLE_ACCESS)) {
      // Read server progress before considering a cookie: an accepted POST with
      // a lost reply must never trigger a second exchange of the one-use token.
      try { return await this.finish(); }
      catch (error) {
        if (!error.message.startsWith("Finish signing in")) {
          return {phase: "google", error: error.message};
        }
      }
    }
    return {phase: login ? "google" : "start", invitationRequired: config.invitation_required,
      ...(expired ? {error: "Sign-in timed out. Sign in with Google again."} : {})};
  }

  async restart() {
    if (this.inFlight) return {phase: "working"};
    const {deviceKey} = await this.chrome.storage.local.get("deviceKey");
    if (deviceKey) {
      const state = await this.request("/api/progress", undefined, true);
      if (["connecting", "connected"].includes(state.status)) return this.status();
    }
    // Only an unsubmitted/failed sign-in is abandoned. Never discard a saved account.
    await this.chrome.storage.session.remove("login");
    await this.chrome.permissions.remove(GOOGLE_ACCESS);
    await this.chrome.alarms.clear("connection-expiry");
    await this.chrome.alarms.clear("connection-progress");
    return {phase: "start"};
  }

  async showGoogle() {
    const {login} = await this.chrome.storage.session.get("login");
    const tab = login && await this.chrome.tabs.get(login.tabId).catch(() => null);
    if (!tab?.url || new URL(tab.url).origin !== "https://accounts.google.com" ||
        this.now() - login.started >= 10 * 60 * 1000) {
      throw new Error("Google sign-in closed or timed out. Choose Start over.");
    }
    await this.chrome.tabs.update(tab.id, {active: true});
    return {phase: "google"};
  }

  async decide(action) {
    const flow = await this.activeFlow();
    if (!flow) throw new Error("Open the fresh connection tab from ChatGPT first.");
    return this.decideFlow(flow.tab, action);
  }

  async decideFlow(tab, action) {
    if (!["allow", "cancel", "retry"].includes(action)) throw new Error("Choose Allow, Cancel or Retry.");
    const ticket = connectionTicket(tab?.url, this.server);
    if (!ticket) throw new Error("Open the connection page from ChatGPT first.");
    const response = await this.request("/api/approve", {ticket, action}, true);
    const target = response.status === "completed" ? "https://chatgpt.com/plugins" : response.redirect_url;
    if (!allowedCallback(target) && !(target === "https://chatgpt.com/plugins" &&
        (action === "retry" || response.status === "completed"))) {
      throw new Error("The return address was rejected.");
    }
    await this.chrome.tabs.update(tab.id, {url: target, active: true});
    await this.chrome.storage.session.remove("chatgptFlow");
    return {phase: response.status === "completed" ? "done" : "connected"};
  }

  async disconnect() {
    await this.request("/api/disconnect", {}, true);
    await this.chrome.storage.local.remove("deviceKey");
    await this.chrome.storage.session.remove("login");
    await this.chrome.permissions.remove(GOOGLE_ACCESS);
    await this.chrome.alarms.clear("connection-progress");
    await this.chrome.alarms.clear("connection-expiry");
    return {phase: "start"};
  }
}
