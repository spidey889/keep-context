# Simpler setup preview

The companion extension moves toward **install → Google sign-in → approve ChatGPT**. It removes manual cookie copying, terminal setup for end users, and the separate Keep Context password. The existing local CLI remains supported.

This is a developer preview, **not yet listed in Chrome's or ChatGPT's directory**. An operator must host the pilot and supply an extension built for its origin. Actual extension/Google UI verification is manual: automated checks use fake browser APIs and never inspect real browser profiles.

## Connect your notes

1. Install the extension from a trusted host. For this preview, extract the ZIP, open `chrome://extensions` or `brave://extensions`, enable Developer mode, choose **Load unpacked**, and select the extracted folder. Pin Keep Context to the toolbar.
2. Open Keep Context. Enter your Google email, review the service hostname and credential notice, and choose **Connect Google Keep**. Enter an invitation code if your host requires one. Approve the one-time permission.
3. Complete Google's sign-in in the new tab. The extension handles the temporary token for this connection. If it does not finish automatically, open the extension and click **Finish connection**. A loading page after “I agree” can be normal; it is not proof of failure. You never copy a token or paste one into ChatGPT.
4. After **Keep is connected**, click **Connect ChatGPT**. Until directory publication, add a custom MCP server once: copy its URL with the extension, name it Keep Context in ChatGPT's form, and keep OAuth/DCR selected. Create/install the plugin and choose Connect.
5. On the final connection page, check the Google account and callback hostname, then click **Allow ChatGPT** directly on the page. No second password or toolbar handoff. The extension popup provides the same approval as a fallback. Then ask about your notes.

Closing the popup does not lose a submitted connection. Reopen it to see progress. A failed Google sign-in needs a fresh sign-in. ChatGPT setup has a 30-minute approval window; an ended request offers **Return to ChatGPT**, then a fresh Connect without repeating Google setup. If the approval response was lost, choose **Finish ChatGPT connection**. The same live code is delivered again without creating another grant.

For an abandoned Google tab, choose **Start over**. An expired ten-minute window releases Google permission and returns to setup, including when the service is offline. If the service restarts before verifying an account, the popup offers fresh sign-in rather than waiting indefinitely. Already verified accounts recover from encrypted state.

If the browser restarts or the extension updates, temporary Google sign-in starts fresh and its permission is cleared. Your saved browser key remains, so a verified Keep account reconnects without another Google sign-in. Failed setup before opening Google also releases the one-time permission.

**Disconnect Keep** deletes the account from the current hosted registry, clears its reader and revokes MCP grants. It does not revoke Google's device session: revoke that separately in Google account security if needed. Removing the extension alone does not delete the hosted account. Losing its local key requires a fresh Google connection; reconnecting the same email revokes the previous browser/MCP access.

## Privacy

- The explicitly approved EmbeddedSetup token goes directly over HTTPS to the single host baked into the extension. Google master tokens have broad account access. The host exchanges/verifies credentials and stores them encrypted using an operator-controlled key. This is encryption at rest, not end-to-end encryption: the running host can decrypt credentials. Only use a host you trust.
- The browser stores a random management key in extension-only local storage, never Chrome Sync. It does not store Google cookies/master tokens. Outside web pages cannot message the worker. One isolated consent script can send only allowlisted actions from the configured service's exact top-level connection page; it cannot access credential storage. Optional Google permission is removed after submission or failure.
- Only the explicitly started ten-minute sign-in handles `oauth_token` for `accounts.google.com`. No Google/Keep page injection, note scraping, browsing history or Google password collection. Browser permission covers more than one cookie name; the implementation restricts its reads to that name.
- Notes stay in Keep and the reader's memory; no notes database is created. Notes returned to ChatGPT are shared with ChatGPT. A hosted service can read new notes while the user's computer is off; its host must stay online. Development tunnels depend on the operator's computer and are temporary.
- Server deletion cannot immediately delete encrypted host backups. Operators must declare backup retention before accepting ordinary users.

## Operator setup

The default invited pilot supports 50 accounts, 20 cached readers, one Google enrollment at a time and 12 enrollment attempts/minute globally. SDK clients/tokens/pending flows are bounded. Run one process; this is not a horizontally scaled public service.

1. Deploy the Dockerfile behind stable HTTPS with persistent `/data`, writable by UID 10001. It runs as a non-root user, binds on `PORT` (default 8800), and uses `/health` for readiness.
2. Supply **runtime secrets**: `KEEP_HOSTED_KEY` (generated 32-byte Fernet key, URL-safe base64), and a high-entropy `KEEP_ENROLLMENT_CODE`. Supply non-secret `KEEP_PUBLIC_URL` without `/mcp`; Render can use its `RENDER_EXTERNAL_URL` automatically. Never use secret build arguments. [Render runtime secrets](https://render.com/docs/docker-secrets).
3. Keep key, URL and volume stable across deploys. An OS lock rejects a second CLI writer. Back up encrypted state and key separately. Do not rotate the key or hostname without an account migration. Do not import the operator's local account into the shared pilot.
4. Build the extension for this exact host:

   ```sh
   uv run python scripts/package_extension.py --server https://keep.example.com --out dist/keep-context-extension.zip
   ```

   Only eight runtime files and four PNG icons enter the archive. No credentials, tests or development configuration. Existing archives are not silently replaced. The included **public** manifest key stabilizes unpacked preview ID `fmpbecffbmodgopadagphiaopjfnoppo`; it is not a signing secret. Confirm the assigned ID before Chrome store publication and set the non-secret `KEEP_EXTENSION_ID` on the host if it differs. Invalid IDs fail closed.
5. Distribute the archive and invitation through your usual secure channel. No Google Cloud project is needed for this flow.

A companion private-test ChatGPT plugin ZIP can prefill the MCP connection instead of asking users to type its URL. See [release packaging and remaining publication steps](RELEASE.md). Its actual ChatGPT upload UI remains unverified; the custom MCP form is the tested fallback.

`render.yaml` is an optional blueprint for a **paid service with a persistent disk** and one instance. Provisioning needs an operator action; this project does not create or pay for a service automatically. [Persistent storage](https://render.com/docs/disks).

For protocol development, source `extension/` points at loopback port 8800. Supply a key through your secret manager, then run:

```sh
uv run keep-context-hosted --public-url http://127.0.0.1:8800
```

`--open-enrollment` explicitly disables invitations for a controlled test or deliberate public enrollment. Default enrollment fails closed without a valid invitation. Do not distribute a localhost-configured extension as the ordinary-user download.

## Before public release

- Verify actual Google sign-in, permission removal, popup recovery and ChatGPT linking in Chrome/Brave. Browser automation needs the owner's explicit authorization; installation and extension popups may still require manual checks when the selected tool blocks internal browser pages.
- Verify persistent hosting, disk ownership, TLS, backups, deletion/retention and operational abuse limits for the pilot size.
- Publish the extension through Chrome review, and package/test/submit the ChatGPT plugin for review. Directory approval is not guaranteed. Public ChatGPT plugins require a stable HTTPS MCP endpoint; Secure MCP Tunnel is not a public-distribution substitute. [OpenAI submission](https://developers.openai.com/plugins/deploy/submission), [MCP hosting](https://developers.openai.com/plugins/build/mcp-server).
- Replace the custom-server form with installation of the approved plugin when it exists. Never claim store availability before approval.

Consumer Keep authentication remains unofficial. This helper smooths the token flow but cannot remove Google's challenges or guarantee every account works. The application retains its network-level read-only guard.
