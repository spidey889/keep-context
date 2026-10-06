# Changelog

## Public repository and project website — 2026-10-06

- The owner requested making the repository public and publishing a small GitHub Pages site. Added a minimal responsive page with example prompts, capabilities, a three-step setup guide and clear product limits. It uses local HTML/CSS/SVG without scripts, analytics, remote fonts or a frontend dependency stack.
- Polished the README with the same identity, website/setup links and an explanation of live Keep access and the in-memory refresh behavior.
- At the owner's request, replaced personal-project examples throughout the site, documentation, demo notes, tool descriptions and corresponding fixtures with fictional gardening/travel examples. Folded this correction into the website publication commit.
- Added a separate Pages workflow with pinned action commits and scoped deployment permissions. Only `site/` becomes the Pages artifact; private server state and scratch files stay outside it. The public site does not host the MCP server or accept credentials.
- GitHub CLI was already authenticated; changed repository visibility to public and configured its homepage/topics and Pages publishing through the API. Publication history/content scans found no real secrets. Two explicitly fake test credentials are ignored only by their exact historical scanner fingerprints.
- Validated HTML, CSS and workflow syntax, local assets/anchors, keyboard/reduced-motion styles and small-text contrast. Browser automation remains prohibited, so visual appearance is left for the owner's review of the published site.

## ChatGPT connection confirmed — 2026-10-06

- After the consent-policy fix, the owner successfully authorized Keep Context in Brave and used it in ChatGPT. Their screenshot shows 13 notes including archived notes, matching the real Google account check. Safe server diagnostics independently confirm consent redirect, token exchange and authenticated MCP calls.
- Updated verification proof to distinguish the actual ChatGPT listing/count from all-five-tool verification by the official MCP client. No browser automation, account identifiers, note contents or credentials are included in the report.

## Consent callback security policy — 2026-10-06

- A fresh manual connection reached consent within seconds, returned a 303, then repeated the consumed form and received 400. No ChatGPT token exchange followed. Source/header inspection found `form-action 'self'` excluded the cross-origin OAuth callback, a browser behavior the HTTP-only verifier does not enforce. This matches the observed stalled return; actual browser confirmation remains manual because the owner prohibits browser automation.
- Consent policy now permits self and only the registered, validated callback origin, including explicit local Inspector callbacks. Initial, wrong-password, rate-limited and approval/cancel responses share the policy. Kept 303 redirects, CSRF/PKCE, redirect allowlisting, no-store and other CSP restrictions; no passwords are forwarded to the callback.
- Six regression cases failed before the change and pass afterward, covering both ChatGPT callback forms and an explicitly allowed local callback through retries, rate limiting and approve/cancel redirects. Full Windows/Python 3.14 suite: 77 passed; lint and formatting pass. Retained the existing tunnel hostname while replacing the server. Fresh public HTTPS checks confirmed the corrected policy, confidential DCR/PKCE, retry/cancel handling and all five tools against 13 real notes; temporary verification tokens were revoked.

## Consent failure recovery — 2026-10-06

- A manual ChatGPT connection reached our password page, expired, and left ChatGPT's Connect control spinning. Investigation confirmed ChatGPT registered its confidential callback-specific OAuth client but no token had been issued; HTTPS/discovery remained healthy. The exact ChatGPT UI state cannot be inspected without browser automation, which the owner prohibited.
- Reproduced an expired consent request returning a plain 400 instead of an OAuth error callback, and wrong passwords losing the form. Expired consent now returns `access_denied` with original client state; incorrect input keeps a blank retry form. Added a CSRF-checked Cancel action that works even during password rate limiting. Expired callback context is retained briefly only to deliver failure; the five-minute grant expiry remains enforced.
- All 71 tests pass on Windows/Python 3.14, with passing lint/format checks. Five new regression cases cover expiry callback/state, retry, cancellation/CSRF/rate limits and expired-context cleanup; the three primary cases failed before the fix.
- Replaced the running server while preserving its existing tunnel hostname and encrypted OAuth client registrations. The fresh real HTTPS check passed confidential callback-specific DCR/PKCE, wrong-password recovery, cancellation, all five tools against 13 notes, and revocation. Temporary diagnostics record only fixed route names, method, time and status; no secrets or note content. The already-stuck ChatGPT attempt still needs a fresh user-initiated connection.

## Live account verification — 2026-10-06

- The owner completed setup and verified 13 Keep notes. A fresh doctor connection and a real public HTTPS OAuth/MCP check using the official MCP client independently passed against the connected account.
- Verified all five tools, known-note search/full retrieval, invalid queries/missing notes, protected access and PKCE consent without printing note contents or secrets. Revoked the temporary check's MCP access and left the server running for ChatGPT linking.
- Actual installation/use inside ChatGPT remains the only unverified client boundary; documentation now distinguishes that from verified live Google access.

## Resumable setup — 2026-10-06

- The user's next cookie exchange succeeded, but a short connection password caused setup to exit before Keep verification or credential storage. That successful token was lost and could not be recovered from the exited process.
- Replaced exit-on-invalid-password behavior with retries for length and confirmation errors. Verify Keep first and preserve the Google login in a separate native-vault checkpoint before password setup; interrupted setup resumes with the same `connect` command.
- Keep checkpoints separate from server credentials and existing connected accounts. Remove progress after completed setup or disconnect; `connect --restart` explicitly starts a new Google sign-in. Rejected exchange/Keep verification is never saved.
- All 66 tests pass on Windows/Python 3.14, with passing lint/format checks. Tested actual Windows credential-vault checkpoint/save/isolation/cleanup using fake data under an isolated service, then removed the test entry.

## Authentication follow-up — 2026-10-06

- A real user's first cookie exchange was rejected by Google; the generic error hid the reason, so no account access has yet been verified. Show only an allowlist of safe Google error codes with actionable instructions, preserving suppression of raw responses and secrets.
- Catch incorrectly copied cookie values before network access and document that browser cookies expire quickly and are single-use. Added a keyboard path to Application and clarified expanding Cookies for users unfamiliar with DevTools.
- Verified all 56 tests on Windows/Python 3.14, including nine new authentication failure/input cases, with passing lint and formatting checks. Actual Google access remains unverified pending the user's fresh-cookie retry.

## 0.1.0 — 2026-10-06

- Built the consumer-account Keep MVP on gkeepapi/gpsoauth after comparing official APIs and existing MCP servers. The official enterprise API cannot provide the intended normal consumer OAuth flow.
- Added search, full-note retrieval, recent notes, labels and task discovery, preserving checklist hierarchy/checked state and excluding trash.
- Added official SDK stdio and protected Streamable HTTP, owner consent, DCR/PKCE, audience-bound tokens, refresh rotation and encrypted restart persistence.
- Isolated Google authentication in a hidden-input local setup command using native OS vaults, plus explicit secret-manager deployment support. Added safe errors, network deadlines and a network-level write guard.
- Added optional one-command HTTPS tunnel startup, setup/deployment/research documentation, linting and regression tests using real MCP clients/server processes.
- Discovered SDK structured-output and OAuth error/revocation quirks through wire tests; documented narrow compatibility handling in source. Real Google/ChatGPT account linking remains a manual verification boundary when credentials are unavailable.
- Verified public HTTPS/OAuth/MCP against demo notes. An initial tunnel reachability failure led to waiting for a registered connection and selecting HTTP/2; the complete remote smoke then passed.
