# Taking the preview to ordinary users

The intended flow is **install extension → Google sign-in → install/connect Keep Context in ChatGPT**. Google consent and ChatGPT approval remain explicit. End users do not run a server or handle tokens. Source and automated checks are ready for invited testing; actual browser verification, stable hosting and directory publication remain open.

## Build the two downloads

Use the same stable service origin for both files:

```sh
uv run python scripts/package_extension.py --server https://keep.example.com --out dist/keep-context-extension.zip
uv run python scripts/package_plugin.py --server https://keep.example.com --out dist/keep-context-plugin.zip
```

The extension ZIP contains seven runtime files and four PNG icons. The private-test ChatGPT ZIP contains only root `plugin.json` and `mcp.json`, in the portable Agent Plugins format. No static authorization headers, accounts or secrets are included. Existing archives are never silently replaced. **A ZIP that validates is not proof of actual installation or review approval.** [OpenAI package format and submission](https://developers.openai.com/plugins/deploy/submission).

For an invited ChatGPT test, the user can try **Plugins → Add → Upload plugin archive** with the plugin ZIP, then Connect. This route is a prepared alternative to the already documented custom MCP form; its real UI has not been verified. Keep the custom-server form as the fallback until a manual test confirms ZIP installation. A temporary tunnel archive is private test material; do not distribute it as a permanent service.

## Before accepting ordinary users

1. Manually complete extension sign-in in Chrome/Brave, including popup closure, Google permission removal, rejected sign-in, ChatGPT approval and disconnect. Do not mark this gate passed from simulated browser APIs or previously saved Google credentials.
2. Deploy the [hosted pilot](CONSUMER.md#operator-setup) behind stable HTTPS. Confirm the real provider volume is writable and survives redeploy, with the same encryption key/origin. State locking and Docker volume recovery pass in CI; that does not verify a Render account or its disk. Decide which operator owns support, backup retention and deletion requests before collecting accounts.
3. Publish the host's privacy policy and terms with that operator's real identity and providers. The project's [privacy explanation](https://spidey889.github.io/keep-context/privacy.html) describes stock behavior; it cannot promise a third-party host's retention. Keep the broad Google credential disclosure before connection. [Chrome user data requirements](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq).
4. Register the Chrome publisher, use the included icon, supply actual screenshots and accurate data/permission declarations, upload the host-specific extension, and request review. Confirm the assigned extension ID and configure `KEEP_EXTENSION_ID` if it differs. Approval of this unofficial consumer authentication approach is unverified. [Chrome publication](https://developer.chrome.com/docs/webstore/publish).
5. Use a verified OpenAI publisher to upload the plugin draft. Complete publisher/terms/assets and actual positive/negative review cases in the dashboard, resolve automated findings and request review. The generated ZIP deliberately does not invent publisher identity, terms, screenshots or passing review cases. Publish only after approval.

No billable service or store submission is created automatically by this repository. These owner actions are postponed until the preview's manual verification is available.

## Prepared icons

The extension includes 16, 32, 48 and 128 px PNG icons for the toolbar, manager and store. A [256 px PNG](https://spidey889.github.io/keep-context/icon.png) is also available for ChatGPT's optional custom-server icon field (under 10 KB). These are rendered from the project's existing `site/icon.svg`, not a Google logo. Actual product screenshots remain a manual verification task. [Chrome icon requirements](https://developer.chrome.com/docs/extensions/reference/manifest/icons).

To regenerate after editing the vector source, use the optional development renderer; no renderer is shipped or needed to install/run the product:

```sh
npm install --prefix work/icon-tools --ignore-scripts --save-exact --no-audit --no-fund @resvg/resvg-js@2.6.2
node scripts/render_icons.cjs
```

The version is pinned and system fonts are disabled. [Renderer source and API](https://github.com/thx/resvg-js).

## Listing copy and permission notes

Single purpose: **Connect your Google Keep notes to ChatGPT for search and read access.**

Suggested short description: **Your Keep notes in ChatGPT**.

Suggested description: Search saved ideas, read full notes, browse recent notes and labels, and find unchecked checklist items. Connect your Google account in the companion extension, then approve ChatGPT. Keep Context does not create, edit or delete notes. Google consumer access is unofficial; images, audio and drawings are outside this preview. Credentials are encrypted on the configured host, which must be trusted. Read the host's privacy policy before connecting.

| Permission | Current feature that needs it |
| --- | --- |
| `storage` | Keep a random local management key and temporary sign-in progress, restricted to extension contexts. No Chrome Sync or saved Google tokens. |
| `activeTab` | Inspect the exact active Keep Context consent tab when the user opens the extension, then return to the validated ChatGPT callback. |
| `alarms` | Release expired sign-in permission and recover progress when the popup closes. |
| Configured service origin | Send connection/approval/disconnect requests to that one HTTPS host. |
| Optional `cookies` + `accounts.google.com` | Read the fresh EmbeddedSetup connection cookie during an explicitly approved sign-in; remove permission afterward. Chrome's API permission covers additional cookie names even though the implementation reads only this one. |

Declare authentication information, email and the connection metadata actually handled; notes are returned by the hosted MCP service. Do not claim “no user data collected” simply because the extension does not persist Google tokens. Proxy/provider logging and backup retention must match the real deployment, not a guessed declaration.
