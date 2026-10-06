# Verification report — 2026-10-06

## Built

Single-owner consumer Google Keep reader with the official MCP Python SDK. Five tools: title/body/checklist search, full-note fetch, recent notes, configured labels, and likely tasks. Supports local stdio and OAuth-protected, stateless Streamable HTTP with JSON responses. Includes hidden-input Google setup, native OS-vault storage, encrypted OAuth persistence, separate owner consent and optional one-command HTTPS tunnel startup.

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

## Remaining manual verification

Live Google read access and real HTTPS OAuth/MCP have now passed. The user's first attempts exposed cookie-expiry/copying friction and exit-on-short-password behavior; setup now provides safe diagnostics, retries passwords and resumes verified access from a separate native-vault checkpoint. **Actual installation and use inside the user's ChatGPT account remains unverified.** The official MCP client verifies the server transport, tools and real Google access, but cannot prove ChatGPT account/workspace feature availability or the final ChatGPT linking experience.

For another developer's first setup:

```sh
uv run keep-context connect
uv run keep-context doctor
uv run keep-context serve --tunnel
```

For the connected owner, only the ChatGPT step remains: add the running server's printed `/mcp` URL with OAuth/DCR and enter the separate connection password. Ask for a known note, read it, and inspect an unchecked item. Do not run `connect` again for an already verified account.

Limitations: unofficial Google API/authentication may break or reject an account; one Google owner per server; keyword search and English prose task heuristics; no image/audio/drawing transcription or reminder retrieval; no write tools. Quick tunnel URLs change on restart. Stable HTTPS deployment preserves OAuth state and is preferable for everyday use.

The dependency stack currently emits benign deprecation warnings from Starlette's test-client integration and gpsoauth's TLS-context construction. Tests retain certificate verification and the upstream TLS adapter; no warning was worked around by disabling TLS.
