# Verification report — 2026-10-06

## Built

Single-owner consumer Google Keep reader with the official MCP Python SDK. Five tools: title/body/checklist search, full-note fetch, recent notes, configured labels, and likely tasks. Supports local stdio and OAuth-protected, stateless Streamable HTTP with JSON responses. Includes hidden-input Google setup, native OS-vault storage, encrypted OAuth persistence, separate owner consent and optional one-command HTTPS tunnel startup.

## Verified

The initial release passed **47 tests on Windows with Python 3.11 and Python 3.14**, plus lint, formatting and wheel/source-distribution builds. The authentication follow-up passes the full **56-test suite on Windows with Python 3.14**, lint and formatting. Its nine added cases cover incorrectly copied cookies before network access, recognized error codes, and suppression of upstream secrets/exceptions.

- Real `gkeepapi` hydration/conversion using mocked Google wire responses: plain notes, labels, checklist order/hierarchy, checked state, empty lists and repeat synchronization. Assertions inspect outgoing requests and prove no note/label mutation payload is sent.
- Query behavior: title/body/checklist and Unicode matching, all-keyword semantics, ranking, pagination, excerpts, archive/label filters, excluded trash, complete retrieval and task heuristics/checked-item omission.
- OAuth HTTP flow: protected-resource and authorization metadata, DCR, callback allowlist, escaped consent content, CSRF/password rejection, rate limiting, PKCE, client binding, wrong audience, expiration, single-use codes, rotating refresh tokens and pair revocation.
- OAuth restart persistence: encrypted state, no plaintext access token on disk, restored clients/tokens and rejection when the public resource changes.
- Secret handling: rejected plaintext vaults, safe credential repr, hidden/noninteractive setup behavior, verification-before-save, and redacted Google authentication/network errors.
- Actual subprocess servers: official MCP client initializes and calls tools over stdio and TCP Streamable HTTP. Invalid input, missing notes and unknown tools return MCP errors.
- **Actual public HTTPS smoke:** Cloudflare tunnel, confidential DCR client, owner consent, PKCE code exchange, denied anonymous MCP access, and official MCP client calling all five tools against demo notes. Run `uv run python scripts/smoke_https.py` with cloudflared on PATH to reproduce. Both processes are cleaned up afterward.
- Package builds produce a wheel and source distribution. Lint and formatting checks pass. CI repeats tests/package checks on Windows and Linux, Python 3.11 and 3.14.

The initial HTTPS probe failed before the tunnel was reachable. Startup was corrected to wait for a registered tunnel connection and use HTTP/2; the subsequent full public smoke passed.

## Remaining manual verification

No Google Keep credentials were present during initial verification. The user's subsequent manual EmbeddedSetup attempt reached Google's token exchange, which Google rejected; the original generic error did not preserve a safe reason. The updated setup is ready for a fresh-cookie retry and will show recognized safe error codes. No real Google account has been read and no actual ChatGPT plugin has been installed. **Mocked Google responses, official MCP client tests and a real HTTPS tunnel do not prove live Google authentication or ChatGPT account availability.**

The smallest remaining step is local account setup:

```sh
uv run keep-context connect
uv run keep-context doctor
uv run keep-context serve --tunnel
```

Complete the manual EmbeddedSetup sign-in/cookie step shown by `connect`. Add the printed `/mcp` URL to ChatGPT with OAuth/DCR and enter your separate connection password. Ask for a known note, read it, and check an unchecked item. This verifies the external Google and ChatGPT account boundaries without exposing credentials here.

Limitations: unofficial Google API/authentication may break or reject an account; one Google owner per server; keyword search and English prose task heuristics; no image/audio/drawing transcription or reminder retrieval; no write tools. Quick tunnel URLs change on restart. Stable HTTPS deployment preserves OAuth state and is preferable for everyday use.

The dependency stack currently emits benign deprecation warnings from Starlette's test-client integration and gpsoauth's TLS-context construction. Tests retain certificate verification and the upstream TLS adapter; no warning was worked around by disabling TLS.
