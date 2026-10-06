# Verification report — 2026-10-06

## Built

Consumer Google Keep reader with the official MCP Python SDK. Five tools: title/body/checklist search, full-note fetch, recent notes, configured labels, and likely tasks. Supports local stdio and OAuth-protected, stateless Streamable HTTP with JSON responses. Local mode includes hidden-input Google setup, native OS-vault storage, encrypted OAuth persistence, owner consent and one-command HTTPS tunnel startup. A separately opted-in extension/hosted preview adds passwordless onboarding and account isolation.

## Consumer preview verification

The complete suite passes **88 Python tests on Windows/Python 3.14** and **11 Node tests**, with passing lint, formatting and source/wheel builds. Added checks cover separate accounts with identical note IDs, subject retention through refresh/restart, encrypted registry, wrong origin/key/audience, invite/body limits, safe Google failures, permission expiry, lost responses, interrupted setup and disconnect/re-enrollment revocation. A Node extension bridge completes enrollment, approval, PKCE and all five MCP tools against an actual TCP server with fake Google credentials; it uses simulated Chrome APIs, not a browser.

A separate public HTTPS hosted probe passed DCR/PKCE, extension-authorized passwordless consent, all five tools against **13 real Keep notes**, known-note search/full retrieval, safe missing-note errors and access denial after disconnect. It used the owner's already verified native-vault credentials in memory, seeded only into a temporary test registry. It did **not** prove a fresh EmbeddedSetup cookie exchange through the extension. Temporary accounts/grants, encrypted test state, server and tunnel were cleaned up; no account identifiers, secrets or note contents were printed.

All five jobs in [the hosted preview CI run](https://github.com/spidey889/keep-context/actions/runs/37532664455) passed: Windows/Linux on Python 3.11/3.14 with Node 24, and Docker build/boot/recovery. The container check rejects anonymous MCP access, writes encrypted OAuth state as its non-root user, then replaces the container and verifies that the registered client survives on a volume. Docker is unavailable on the local host; this is actual GitHub Actions evidence.

The private-test ChatGPT ZIP validates against both published Agent Plugins 1.0.0 JSON schemas. Inspection confirmed exactly two files, the intended hosted MCP URL, and no auth headers/credentials. Invalid origins are rejected before creating an archive, and rebuilding cannot overwrite an existing ZIP. Public setup/privacy pages pass HTML5 parsing, CSS parsing and local link/anchor checks. These checks do not prove plugin upload acceptance or visual/browser behavior.

The permission-lifecycle follow-up passes **15 Node tests** and three focused Python packaging/TCP integration cases. Three regressions failed before the fix: failed preflight, partial browser setup and stale grants on profile restart. The worker-module test drives simulated startup events and popup messages while offline, then recovers a verified account without Google sign-in or disclosing the management key. This models Chrome's documented [session-storage clearing](https://developer.chrome.com/docs/extensions/reference/api/storage) and [profile startup event](https://developer.chrome.com/docs/extensions/reference/api/runtime#event-onStartup); it is not a real browser test.

Extension packaging checks validate all four PNG dimensions, manifest/toolbar references and the exact eleven-file archive. The separate 256 px PNG is 4,326 bytes; it was visually inspected as the existing project mark. The optional pinned renderer reads only the local SVG and requires no browser.

Remaining manual boundaries: fresh Google sign-in/cookie exchange, permission removal and popup recovery, plus linking the extension-backed account in ChatGPT. The owner's subsequent screenshot confirms unpacked installation in Brave, as described below. Stable hosting, real provider disk ownership/backups/deletion retention and store reviews are not verified or provisioned. [Preview steps and operator setup](CONSUMER.md).

## Browser follow-up — 2026-10-06

After the owner explicitly permitted browser use, real Brave checks rendered the published connection/privacy pages and reached ChatGPT's plugin setup. ChatGPT discovered the preview's OAuth endpoints, selected Dynamic Client Registration, and offered `keep:read`. Creating the requested preview plugin reached the **Connect Keep Context Preview** dialog. This proves client discovery and creation, not account authorization or note access through the extension.

The selected browser tool rejected internal extension URLs; no workaround was attempted. Its file picker also required an unavailable local-file permission, so the plugin archive never reached ChatGPT validation. The custom MCP form remained usable. Subsequent state/screenshot requests timed out despite the same test tab remaining in the browser inventory; the sign-in continuation is not asserted. Unpacked extension installation and fresh Google connection still require user action. No browser credentials or cookies were inspected by the agent.

The owner then installed the unpacked 0.2.0 preview in Brave and supplied a screenshot of its popup's service-reachability error. Public health/config checks passed. Source inspection found that `Bridge.request` called native `fetch` with a bridge receiver instead of the worker global, contrary to the [Web IDL operation receiver rules](https://webidl.spec.whatwg.org/#es-operations) for the [Fetch global method](https://fetch.spec.whatwg.org/#fetch-method). A receiver-checking test reproduced the same safe error before the fix; binding the global receiver passes all **16 Node tests** and **three focused Python packaging/TCP cases**. These tests model the browser contract; they do not prove the actual popup retry or fresh Google authentication. The corrected archive was copied into the existing desktop preview after checking that its files still matched the prior archive. Browser automation remains stopped at the owner's request.

## Verified

The initial release passed **47 tests on Windows with Python 3.11 and Python 3.14**, plus lint, formatting and wheel/source-distribution builds. The authentication follow-up passes the full **56-test suite on Windows with Python 3.14**, lint and formatting. Its nine added cases cover incorrectly copied cookies before network access, recognized error codes, and suppression of upstream secrets/exceptions.

The resumable-setup fix passes the full **66-test suite on Windows with Python 3.14**, lint and formatting. Ten further cases cover password retry, interrupted setup/resume without repeating Google exchange, verification-before-checkpoint, final-save failure, separate progress/server credentials, cleanup and safe vault errors. An actual Windows credential-vault smoke passed checkpoint/save/read/isolation/cleanup using fake data under a unique test service; that entry was removed afterward.

Consent recovery raised the suite to **71 tests**, covering expiry callbacks, retries and CSRF-checked cancellation. The callback security-policy fix passes the full **77-test suite on Windows/Python 3.14**, lint and formatting. Its six new cases failed before the change: initial/retry/rate-limit pages and approval/cancel redirects must permit only self and the registered callback origin while preserving the remaining policy restrictions. HTTP clients do not enforce browser CSP; browser use remains a separate manual proof boundary. See [form-action behavior](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action).

- Real `gkeepapi` hydration/conversion using mocked Google wire responses: plain notes, labels, checklist order/hierarchy, checked state, empty lists and repeat synchronization. Assertions inspect outgoing requests and prove no note/label mutation payload is sent.
- Query behavior: title/body/checklist and Unicode matching, all-keyword semantics, ranking, pagination, excerpts, archive/label filters, excluded trash, complete retrieval and task heuristics/checked-item omission.
- OAuth HTTP flow: protected-resource and authorization metadata, DCR, callback allowlist, escaped consent content, CSRF/password rejection, rate limiting, PKCE, client binding, wrong audience, expiration, single-use codes, rotating refresh tokens and pair revocation.
- OAuth restart persistence: encrypted state, no plaintext access token on disk, restored clients/tokens and rejection when the public resource changes.
- Secret handling: rejected plaintext vaults, safe credential repr, hidden/noninteractive setup behavior, verification-before-save, and redacted Google authentication/network errors.
- Actual subprocess servers: official MCP client initializes and calls tools over stdio and TCP Streamable HTTP. Invalid input, missing notes and unknown tools return MCP errors.
- **Actual public HTTPS smoke:** Cloudflare tunnel, confidential DCR client, owner consent, PKCE code exchange, denied anonymous MCP access, and official MCP client calling all five tools against demo notes. Run `uv run python scripts/smoke_https.py` with cloudflared on PATH to reproduce. Both processes are cleaned up afterward.
- Package builds produce a wheel and source distribution. Lint and formatting checks pass. CI repeats tests/package checks on Windows and Linux, Python 3.11 and 3.14.

## Live Google account verification — 2026-10-06

The user completed local setup and verified **13 notes**. A fresh `doctor` connection independently confirmed that count. An official MCP client then passed a real public HTTPS check against the connected account: anonymous access rejected, DCR/owner consent/PKCE accepted, all five read tools callable, recently listed note fetched in full, search using a word from that note returned the same ID, label/task results structured correctly, and missing-note/invalid-query errors handled. Searches for the intended example topics also completed successfully; their result counts/content are not recorded here.

The live check printed only status and the total note count. No note contents, identifiers, Google tokens, connection passwords or MCP tokens were printed or committed. Its temporary OAuth access was revoked afterward and rejected on reuse. The server stayed running for the user's ChatGPT connection. After the consent fixes, a fresh HTTPS check also passed callback-specific confidential DCR, cancellation/state return, incorrect-password retry and the corrected callback CSP header, then repeated all five tools against 13 notes and revoked its temporary access.

The initial HTTPS probe failed before the tunnel was reachable. Startup was corrected to wait for a registered tunnel connection and use HTTP/2; the subsequent full public smoke passed.

## Manual ChatGPT verification — 2026-10-06

The owner completed authorization in Brave and used Keep Context in a real ChatGPT conversation. The supplied screenshot shows ChatGPT reporting **13 notes including archived notes**, matching independent Google verification. Safe server diagnostics confirm the fresh consent redirect, successful token exchange and subsequent successful authenticated MCP requests. This confirms the actual ChatGPT connection and note listing/count; individual search, full-note and checklist answers in ChatGPT are not asserted from that screenshot. All five tools were independently verified against the real account using the official MCP client.

The owner's manual browser retry also confirms that returning to ChatGPT works after correcting the consent security policy. No browser automation was used. Logs contain only fixed route names, method, time and status; this report contains no account identifiers, note contents or secrets.

## Setup for another developer

The first attempts exposed cookie-expiry/copying friction and exit-on-short-password behavior; setup now provides safe diagnostics, retries passwords and resumes verified access from a separate native-vault checkpoint. Account/workspace feature availability and Google consumer authentication remain specific to each user's environment.

For another developer's first setup:

```sh
uv run keep-context connect
uv run keep-context doctor
uv run keep-context serve --tunnel
```

The connected owner can now ask ChatGPT about notes. Keep the server and tunnel running; do not run `connect` again for an already verified account. A new installation uses the printed `/mcp` URL with OAuth/DCR and the separate connection password. Useful manual checks are searching for a known note, reading it, and inspecting an unchecked item.

Limitations: unofficial Google API/authentication may break or reject an account; local mode has one Google owner per server; keyword search and English prose task heuristics; no image/audio/drawing transcription or reminder retrieval; no write tools. Quick tunnel URLs change on restart. Stable HTTPS deployment preserves OAuth state and is preferable for everyday use. Hosted preview has separate account isolation and the manual boundaries described above.

The dependency stack currently emits benign deprecation warnings from Starlette's test-client integration and gpsoauth's TLS-context construction. Tests retain certificate verification and the upstream TLS adapter; no warning was worked around by disabling TLS.
