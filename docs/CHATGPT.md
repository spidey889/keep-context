# ChatGPT and deployment

## Temporary connection

After `connect`, install cloudflared and run `uv run keep-context serve --tunnel`. This launches a Cloudflare Quick Tunnel, obtains its public HTTPS URL, then starts the OAuth-protected MCP service on `127.0.0.1:8000`. No Google credentials go to the tunnel process. Cloudflare terminates TLS and forwards traffic, so it is part of the connection's trust boundary.

The MCP transport uses stateless Streamable HTTP with JSON responses. This avoids the long-lived SSE transport, which [Quick Tunnels do not support](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). Quick Tunnels have no uptime guarantee and change hostname each run. Use a stable tunnel/proxy for ongoing use.

1. In ChatGPT on the web, open **Plugins**, then **Add custom MCP server**.
2. Name it **Keep Context**. Enter the printed HTTPS URL including `/mcp`.
3. Choose **OAuth**; choose **DCR/dynamic client registration** if the interface asks. Do not choose CIMD: this server advertises DCR. No pre-created client ID/secret is needed.
4. Follow the authorization link. Enter only your separate Keep Context connection password and approve read access.
5. Install/select the plugin using `@` in a new chat. Ask “Search my notes for weekend trip,” then “Read that note,” and “What do I still need to do?”

Current OpenAI documentation describes this as a custom MCP plugin. Older accounts/interfaces may call it an app or connector and expose developer mode under settings. Workspace permissions or account availability can prevent adding custom servers. Follow the account's current interface and [official connection instructions](https://developers.openai.com/api/docs/guides/custom-mcp-server).

The server exposes the conventional `search(query)` and `fetch(id)` result shapes, plus three purpose-specific read tools. Responses include JSON text and structured content. Each tool declares `readOnlyHint`, `destructiveHint=false`, and OAuth scope metadata. All HTTP MCP requests, including initialization/tool discovery, require a valid bearer token. The public `/health` endpoint exposes no account or note information.

## Stable endpoint

Run a stable HTTPS tunnel or reverse proxy forwarding to `http://127.0.0.1:8000`, preserving the public Host header and routing all paths, including OAuth discovery/authorization/token routes. Then:

```sh
uv run keep-context serve --public-url https://keep.example.com
```

Do not append `/mcp` to `--public-url`. Add it only to the URL entered in ChatGPT. HTTPS is mandatory except for loopback development. The default bind address is always loopback. On a VPS, run the proxy and this process together; the OS user/secret manager must provide credentials. This MVP runs as one process/worker. It is not designed for serverless request handlers or multiple replicas.

Persist `.keep-context/oauth.enc` across restarts (or set `--state-file /private/state/oauth.enc`). The file contains encrypted OAuth clients/access/refresh tokens, not notes or Google credentials. Its encryption key is derived from the master token in the vault. Keep the same Google token and public URL to preserve connections. Changing either requires `--reset-access` and a fresh ChatGPT connection. A process restart discards unfinished consent flows/authorization codes; completed connections survive.

Only the documented ChatGPT callback patterns at `https://chatgpt.com` are accepted by default. If ChatGPT displays a different verified callback, explicitly allow that exact URI with `--redirect-uri`. Never disable the allowlist broadly.

For MCP Inspector with OAuth, add its exact callback, for example:

```sh
uv run keep-context serve --public-url http://127.0.0.1:8000 --redirect-uri http://localhost:6274/oauth/callback
```

Use the callback actually shown by your Inspector version. OAuth discovery advertises PKCE S256, dynamic registration, authorization-code and refresh grants, revocation, and the protected resource `PUBLIC_ORIGIN/mcp`. The scope is `keep:read`. Request this resource in both authorization and token exchange. [OpenAI authentication contract](https://developers.openai.com/plugins/build/auth).

## Local stdio clients

Stdio trusts the local client process and uses the same Google vault account. It does not expose a network listener or use the HTTP connection password. Example client configuration; replace `/absolute/path/keep-context` with your clone's real path:

```json
{
  "mcpServers": {
    "keep-context": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/keep-context", "run", "keep-context", "serve", "--transport", "stdio"]
    }
  }
}
```

For Windows JSON paths, use forward slashes, e.g. `C:/Users/vinit/Desktop/keep-context`. Credentials never belong in this client configuration. The stdout stream is reserved for MCP protocol messages.

## Troubleshooting

- **Google authentication rejected:** rerun local `connect`; do not enter Google credentials into the MCP consent form.
- **401 from `/mcp`:** expected without OAuth. Let the client follow the `WWW-Authenticate` resource metadata challenge.
- **400 invalid target:** the URL/resource differs from `PUBLIC_ORIGIN/mcp`, or token exchange omitted `resource`.
- **400 invalid host / origin:** the proxy must preserve the configured public host. Use the exact configured HTTPS URL.
- **Tunnel fails:** cloudflared must be on PATH and able to reach Cloudflare. An existing Cloudflare config can conflict with Quick Tunnels; use a separately configured stable tunnel rather than modifying unrelated settings.
- **New temporary URL:** recreate the ChatGPT plugin connection; tokens are audience-bound to the old host.
- **Consent expired:** the connection password does not expire. The sign-in request lasts five minutes; expiry returns an OAuth failure to ChatGPT. Start a fresh connection there. Unknown links from a server restart explain returning to ChatGPT. Google setup remains saved; do not repeat `connect`.
- **Incorrect connection password:** retry in the same form. The input stays blank and no password is echoed. After five failed attempts in a minute, wait one minute or choose Cancel.
- **Cancel connection:** the consent form returns an OAuth cancellation with the original client state to ChatGPT so the client can finish its waiting flow.
- **Connect keeps spinning after an old failed flow:** close the abandoned authorization tab and refresh ChatGPT. If the old attempt remains stuck, uninstall and reinstall the existing private Keep Context plugin once to start a fresh connection with the same server URL. This affects the ChatGPT installation, not the Google credentials saved locally. If it persists, stop repeated retries and diagnose where discovery, authorization, callback or token exchange stops; do not expose request query strings, passwords or token values in logs/screenshots.
- **Rate limited:** wait and retry. Google 429 responses fail promptly instead of retrying forever. Failed password attempts are limited to five per minute for this owner server.
