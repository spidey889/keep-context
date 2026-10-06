# Current architecture and behavior

Keep Context is a read-only Google Keep MCP server. Local `serve` is single-owner; the separately opted-in hosted pilot isolates owners using authenticated SDK token subjects. Python 3.11+, `gkeepapi==0.17.1`, `gpsoauth==2.0.0`, and official `mcp` SDK >=1.30,<2. `uv.lock` pins the tested dependency set.

## Request path

`ChatGPT → HTTPS proxy/tunnel → SDK OAuth authorization → /mcp → five read tools → serialized KeepBackend snapshot → gkeepapi → Google's private Keep sync API`.

Stdio uses the same five tools but trusts the local MCP client process. No OpenAI API key or model calls are made by this project. Local `serve` has one Google account for the process and must not be shared as multi-user hosting.

## Hosted consumer pilot

`keep-context-hosted` is a separate entrypoint. It does not read the local vault or use the owner-password form. A Manifest V3 extension has a fixed service origin, extension-only local management key, optional Google cookie permission, and no external messaging. One isolated content script runs only on that service's consent page, never Google/Keep pages. Explicit consent/email precede manually completed Google sign-in. Only a ten-minute EmbeddedSetup session reads the single transient cookie; a hash baseline rejects old cookies. Submission immediately removes Google permission. Google secrets never enter extension storage/popup messages. Optional cookie listeners register when permission exists. Packaging replaces the source extension's loopback configuration with one trusted origin.

The extension saves its random management key before submitting setup. Google verification runs in a bounded background job, returning immediately to avoid MV3 fetch deadlines. Authenticated progress polling recovers lost responses/closed popups. Jobs are ephemeral; credentials are saved only after verified Keep access. Upstream exceptions stay suppressed. Enrollment defaults to invitations, with explicit open enrollment. Capacity is 50 accounts, 20 cached readers, one concurrent enrollment and 12 attempts/minute globally. One process owns the registry; an OS lock rejects a second CLI writer.

An expiry alarm removes Google permission after ten minutes, even when service requests fail. Start over clears abandoned sign-in state while preserving a server-accepted job/account. Recovering an accepted POST drops cookie permission without resubmitting its token. A submitted job lost to server restart returns to fresh setup instead of spinning. `KEEP_EXTENSION_ID` configures the exact permitted extension origin and rejects invalid IDs.

Failed preflight/browser setup releases optional Google permission even before a login checkpoint exists. Profile startup and extension installation/update remove stale grants without network access, retain the local management key, and recreate progress polling. Lifecycle cleanup precedes popup messages; it does not run on ordinary worker wake, which could race a new user-approved grant. Verified hosted accounts survive a browser restart; incomplete browser sign-in starts fresh.

The bridge binds native `fetch` to the worker global. Calling it as an unbound bridge property supplies the wrong browser receiver and can fail before any request reaches the service; Node's fetch does not enforce this receiver check. A dedicated regression models that browser contract, while the TCP test verifies the real service exchange.

Extension archives allowlist eight runtime files and four local PNG icons; the packager reads binary assets unchanged. Toolbar/manager/store icons and the optional 256 px ChatGPT icon are rendered from `site/icon.svg` using a pinned developer-only renderer. They require no runtime library or remote asset fetch.

The encrypted, atomically written registry holds account credentials, hashes of browser management keys, and SDK OAuth state. A separate operator-controlled Fernet key comes from runtime secrets. Encryption is at rest: the host decrypts credentials for Keep. Stable public URL/key/storage are required. Local CLI OAuth state stays separate.

ChatGPT uses standard DCR/PKCE. The hosted consent window is 30 minutes, independent of Google's ten-minute cookie permission; local owner consent remains five minutes. `/connect` displays inline account/callback confirmation and Allow/Cancel controls through the isolated extension script. Synthetic DOM clicks cannot approve. The worker accepts only its own popup or the service's exact top-level origin/path/ticket and uses Chrome's sender tab, never page-supplied tickets/accounts/redirects. A setup tab retains the original consent tab in session storage, revalidating its URL before use. The toolbar popup remains a fallback.

Ended/unknown ChatGPT requests show recovery while preserving the connected Google account. Return to ChatGPT sends the validated original callback/state an OAuth failure when available. A bounded ephemeral decision cache (128 entries, 30 minutes) permits the same account to re-deliver a still-live one-minute authorization code after a lost response, without creating another grant. Status polling and extension/page messages contain no code. Successful exchange becomes a completed state; expired codes cannot be reissued. Re-enrollment/disconnect clear decision state. Process restart loses pending decisions but retains encrypted Google accounts and issued tokens, so recovery needs only a fresh ChatGPT request.

Authenticated `/api/approve` assigns the account ID to the SDK code's `subject`; access/rotated refresh tokens retain it. The extension validates the ChatGPT callback before navigating the original tab. `/mcp` selects a reader solely from verified token subject, never a client-supplied account ID. Each tool retains its chosen backend through metadata access. Missing/disconnected subjects fail closed.

Reconnecting a verified email rotates the management key and revokes old grants/codes/readers. Disconnect removes the account/cache/grants, but not Google's upstream session or host backups. Removing the extension alone is not server deletion. Docker uses locked dependencies and a non-root user; optional Render configuration uses one paid persistent service. Container CI registers an OAuth client to force an encrypted volume write, then replaces the container and verifies that client survives. Credentials never enter build/extension artifacts. The preview is not store-listed. The owner manually verified fresh Google sign-in, inline approval returning to ChatGPT, and recent-note retrieval in ChatGPT. Actual browser permission removal and plugin ZIP installation remain manual verification boundaries.

## Google access

Local `connect` manually exchanges a hidden EmbeddedSetup `oauth_token` cookie through gpsoauth and verifies read sync before saving a setup checkpoint in the native OS vault (`keep-context` / `setup-progress`). It then loops until a separate owner connection password has 20–1024 characters and matching confirmation. Only completed setup replaces the server's `account` vault entry; it then removes the checkpoint. Interrupting password entry or failing the final save preserves progress. Rerunning `connect` resumes the checkpoint, rechecks Keep, and skips the email/browser/token prompts. `connect --restart` discards progress; `disconnect` deletes both entries. The server loads only completed credentials, so a checkpoint does not grant MCP access.

Cookie input must be only the complete `oauth2_NUMBER/...` value; malformed values fail before network access. Cookies are short-lived and single-use. Exchange failures expose only fixed messages for recognized `BadAuthentication`, `NeedsBrowser` and `MissingDroidguard` codes; other response fields, unknown errors and exception details stay suppressed. Rejected Google authentication/Keep verification is never checkpointed. Existing master tokens can also be entered locally and explicitly start fresh setup. Environment secrets support headless deployments. Unknown/plaintext vault backends fail closed. Google master tokens never appear in MCP output.

Backend sync is lazy and serialized by a thread lock. It initially downloads notes, then refreshes after 60 seconds. Notes exist only in RAM. Failure never returns the old cached snapshot. A failed sync discards the client so a later request can retry from a fresh connection. Upstream errors are replaced with safe actionable messages; upstream debug logging is disabled.

Google read sync uses POST. `ReadOnlySession` rejects unexpected methods/routes and any nonempty nodes/userInfo mutation payload. The app creates no notes or labels and does not edit gkeepapi nodes. Sync requests have 10-second connect/30-second read deadlines; the sync loop has a two-minute deadline and Google 429 fails promptly. Auth refresh retries at most once. The original gpsoauth TLS adapter is subclassed only to add those network deadlines. Pinned-version API internals and real parsing are tested using mocked wire responses.

Full text conversion distinguishes text notes from lists. Checklists preserve item IDs, order, checked flags and parent IDs without duplicating list text. Timestamps are UTC. Source URLs prefer the Google server ID; local node IDs are used for tool retrieval. Labels include configured unused names. Images/audio/drawings and reminders are outside the text MVP.

## Tools

- `search(query, limit=20, offset=0, include_archived=true, label=null)`: Unicode NFKC/casefold substring search across titles/body/checklist; all keywords must match. Title matches rank first, then updated time/id. Returns excerpts, metadata, counts and next offset.
- `fetch(id)`: full text plus note metadata and checklist state. Trashed/missing notes return a tool error.
- `list_recent_notes(limit=20, offset=0, include_archived=false, label=null)`: updated-time descending.
- `list_labels()`: configured names and counts across non-trashed notes, including archived notes.
- `find_tasks(limit=50, offset=0, include_archived=false, label=null)`: unchecked checklist/Markdown items are explicit; English TODO/need-to/remember-to/task-title wording is heuristic. Completed/checked lines are omitted. It does not infer deadlines or promise complete task recall.

Every listing uses `next_offset`, limit 1–100 and nonnegative offset. Search/fetch arguments are bounded; empty/whitespace search fails. Exact label matching is case-insensitive. Trash is always excluded. Responses expose structured JSON and matching JSON text; source content is described as untrusted data in server instructions.

## MCP HTTP security

Stateless Streamable HTTP, JSON responses, loopback bind, 64 KiB request limit, explicit host/origin checks. SDK routes provide OAuth authorization metadata, protected resource metadata, DCR, PKCE S256, token exchange and revocation. All `/mcp` requests require valid `keep:read` tokens with resource `PUBLIC_ORIGIN/mcp`. Tool metadata declares read-only behavior and OAuth scope. `/health` is public and reveals only service status.

Owner consent uses a separate 20+ character password, scrypt comparison, per-flow CSRF token, five-minute ticket expiry, no-store/no-referrer/CSP headers, escaped client names and five failed password attempts per minute. Incorrect passwords/CSRF keep a blank retry form; rate limits keep the form with Retry-After. A CSRF-checked Cancel action returns `access_denied` and the original state to the client's validated callback. Expired tickets also return that OAuth failure, rather than leave the client waiting on a plain error page. Expired callback context is retained for up to 30 minutes in the bounded pending dictionary, solely for failure delivery; expired requests cannot create grants. Unknown/removed tickets explain recovery in ChatGPT. DCR callbacks are restricted to ChatGPT's documented HTTPS callback patterns or exact explicitly allowed URIs. Code exchange is client-bound, single-use and PKCE-checked, with one-minute expiry. Access tokens expire in one hour; refresh tokens rotate and expire in 30 days. Revocation invalidates both tokens in a pair.

Consent pages and their retry/redirect responses set CSP `form-action` to self plus the origin of this flow's registered, validated callback. Chromium checks this rule on redirects after form submission; self alone would block returning to ChatGPT after consuming the ticket. Redirects use 303 so the password POST body is not forwarded. Script execution, embedding and unrelated form destinations remain blocked.

Completed OAuth clients/tokens persist atomically in `.keep-context/oauth.enc`, encrypted with Fernet using domain-separated SHA-256 derivation from the high-entropy Google master token. No note data or Google credentials are in that file. Changing the master token or public resource requires `--reset-access`. Consent tickets/codes are ephemeral. Run one process/worker for each state file.

Optional `--tunnel` runs cloudflared over HTTP/2, suppresses raw log output, and waits for both a URL and a registered tunnel connection within a 45-second startup deadline. It cleans up its child process on shutdown. Temporary hostnames invalidate old OAuth access. Stable public URLs preserve sessions. Quick Tunnels are convenience hosting with no uptime guarantee, not a permanent deployment.

## Public project site

`https://spidey889.github.io/keep-context/` is a static product/setup page from `site/`. Plain HTML/CSS and a local SVG require no build, browser script, tracking or external fonts. It contains illustrative examples and public documentation links, never owner notes, credentials or the owner's live MCP endpoint. GitHub Pages does not run the MCP server; users configure their own server/account.

Public examples, demo notes and test fixtures use fictional gardening and travel topics. Demo IDs are `demo-garden` and `demo-trip`; the demo reads no Google account. Keep examples independent of the owner's personal projects.

`connect.html` explains invited extension setup and recovery in plain language. `privacy.html` explains stock data handling without inventing a third-party host's policies. The extension links both. `scripts/package_plugin.py` produces a two-file portable Agent Plugins private-test ZIP for one origin; it contains only public presentation/connection metadata. It does not bundle secrets, invent review evidence, submit a store listing or replace the custom MCP fallback before real upload verification. Release prerequisites are in `docs/RELEASE.md`.

`.github/workflows/pages.yml` deploys only `site/` on `main` changes to that folder/workflow or a manual dispatch. Actions are pinned to immutable commits; Pages write/OIDC permissions are limited to the deployment job. Server CI remains separate. Update README/site instructions together when setup behavior changes.
