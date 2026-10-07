# Simpler setup preview

The companion extension moves toward **install → Google sign-in → approve ChatGPT**. It removes manual cookie copying, terminal setup for end users, and the separate Keep Context password. The existing local CLI remains supported.

This is a developer preview, **not yet listed in Chrome's or ChatGPT's directory**. An operator must host the pilot and supply an extension built for its origin. Actual extension/Google UI verification is manual: automated checks use fake browser APIs and never inspect real browser profiles.

## Connect your notes

1. **Install Keep Context.** The setup page opens automatically. Enter your Google email, read the connection notice and choose **Agree and sign in with Google**. Allow the one-time browser permission. Enter an invitation code only if your host requires one.
2. **Sign in with Google.** Complete Google's sign-in in the tab we opened. Keep Context detects completion and brings you back automatically, even if Google keeps loading after “I agree.” No Finish button, token copying or popup handoff.
3. **Connect ChatGPT.** Click **Connect ChatGPT**, install/connect the plugin, then choose **Allow ChatGPT** on the connection page. When you see **Your notes are ready**, open a new ChatGPT chat, select Keep Context and ask about your notes.

The host can configure a real ChatGPT listing link so the third step opens it directly. This unpublished preview still needs the one-time custom-server form: the setup page explains it and has **Copy address and open ChatGPT**. Leave OAuth/Dynamic Client Registration selected. A listing link is the plugin's own page in ChatGPT, not the MCP server address or a Chrome publisher account.

### Install this unpublished preview

Extract the extension ZIP from your trusted host. Open `chrome://extensions` or `brave://extensions`, enable Developer mode, choose **Load unpacked**, and select the extracted folder. Setup opens on first installation. No pinning is required. Clicking Keep Context in the extensions menu opens or reuses its setup page. Store publication will replace this developer installation step; it has not happened yet.

### If you get interrupted

Close the setup tab whenever you need; reopening Keep Context restores submitted progress. Keep the Google tab open until sign-in is accepted. **Go to Google sign-in** returns to it. **Start over** abandons only an unfinished sign-in, preserving a server-accepted job or saved account. An expired ten-minute window releases Google permission even when the service is offline. A server restart before verification offers fresh sign-in rather than indefinite waiting.

ChatGPT approval has a separate 30-minute window. An ended request offers **Return to ChatGPT**, then a fresh Connect without another Google sign-in. If the approval reply was lost, **Finish ChatGPT connection** safely delivers the same live code again. Updates/profile restart clear temporary Google permissions; verified accounts recover with the saved browser key.

**Manage connection → Disconnect Keep** deletes the hosted account, clears its reader and revokes MCP grants. It does not revoke Google's device session: revoke that separately in Google account security if needed. Removing the extension alone does not delete the hosted account. Losing its local key requires a fresh Google connection; reconnecting the same email revokes the previous browser/MCP access.

## Privacy

- The explicitly approved EmbeddedSetup token goes directly over HTTPS to the single host baked into the extension. Google master tokens have broad account access. The host exchanges/verifies credentials and stores them encrypted using an operator-controlled key. This is encryption at rest, not end-to-end encryption: the running host can decrypt credentials. Only use a host you trust.
- The browser stores a random management key in extension-only local storage, never Chrome Sync. It does not store Google cookies/master tokens. Outside web pages cannot message the worker. One isolated consent script can send only allowlisted actions from the configured service's exact top-level connection page; it cannot access credential storage. Optional Google permission is removed after submission or failure.
- Only the explicitly started ten-minute sign-in handles `oauth_token` for `accounts.google.com`. No Google/Keep page injection, note scraping, browsing history or Google password collection. Browser permission covers more than one cookie name; the implementation restricts its reads to that name.
- Notes stay in Keep and the reader's memory; no notes database is created. Notes returned to ChatGPT are shared with ChatGPT. A hosted service can read new notes while the user's computer is off; its host must stay online. Development tunnels depend on the operator's computer and are temporary.
- Server deletion cannot immediately delete encrypted host backups. Operators must declare backup retention before accepting ordinary users.

## Operator setup

The default invited pilot supports 50 accounts, 20 cached readers, one Google enrollment at a time and 12 enrollment attempts/minute globally. SDK clients/tokens/pending flows are bounded. Run one process; this is not a horizontally scaled public service.

1. Deploy the Dockerfile behind stable HTTPS with persistent `/data`, writable by UID 10001. It runs as a non-root user, binds on `PORT` (default 8800), and uses `/health` for readiness.
2. Supply **runtime secrets**: `KEEP_HOSTED_KEY` (generated 32-byte Fernet key, URL-safe base64), and a high-entropy `KEEP_ENROLLMENT_CODE`. Supply non-secret `KEEP_PUBLIC_URL` without `/mcp`; optionally set `KEEP_CHATGPT_URL` to your real published or workspace ChatGPT listing link (HTTPS on `chatgpt.com`, no query or fragment). Leave it unset until a listing exists; the preview then shows the guided form. Set `KEEP_EXTENSION_ID` to your actual browser extension ID. The URL is validated at startup and again in the extension. Render can use its `RENDER_EXTERNAL_URL` automatically. Never use secret build arguments. [Render runtime secrets](https://render.com/docs/docker-secrets).
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

- Verify actual Google sign-in, permission removal, automatic return/setup-tab recovery and ChatGPT linking in Chrome/Brave. Browser automation needs the owner's explicit authorization; installation and sign-in may still require manual checks when the selected tool blocks internal browser pages.
- Verify persistent hosting, disk ownership, TLS, backups, deletion/retention and operational abuse limits for the pilot size.
- Publish the extension through Chrome review, and package/test/submit the ChatGPT plugin for review. Directory approval is not guaranteed. Public ChatGPT plugins require a stable HTTPS MCP endpoint; Secure MCP Tunnel is not a public-distribution substitute. [OpenAI submission](https://developers.openai.com/plugins/deploy/submission), [MCP hosting](https://developers.openai.com/plugins/build/mcp-server).
- Replace the custom-server form with installation of the approved plugin when it exists. Never claim store availability before approval.

Consumer Keep authentication remains unofficial. This helper smooths the token flow but cannot remove Google's challenges or guarantee every account works. The application retains its network-level read-only guard.
