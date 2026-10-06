# Connect a Google Keep account

## One-time local setup

Run `uv run keep-context connect` in an interactive terminal. Secrets are hidden; noninteractive input is rejected rather than echoed.

1. Enter your Google email.
2. Manually visit <https://accounts.google.com/EmbeddedSetup> in your browser and sign in. Complete Google's consent/challenges if requested. This program does not open or automate your browser.
3. Open browser DevTools. In Brave/Chrome/Edge use **Application → Storage → Cookies → https://accounts.google.com**. In Firefox/Zen use **Storage → Cookies**. Copy the value of the **`oauth_token`** cookie. A page that keeps loading can be normal.
4. Paste that value into the terminal's hidden prompt. The program exchanges it with Google; the temporary cookie is never saved or printed.
5. Choose and confirm a **separate connection password**, at least 20 characters, ideally a long random password from your password manager. This is the password for the Keep Context authorization screen, not your Google password.
6. The command verifies Google authentication and a read-only Keep sync, then saves the account in the native OS vault. Only a note count is printed. Run `uv run keep-context doctor` to recheck.

If you already have a master token, use `uv run keep-context connect --master-token`; the token prompt is still hidden. The ordinary flow deliberately does not accept Google passwords or app passwords. Upstream discourages password login because it commonly fails modern Google challenges. [gkeepapi documentation](https://github.com/kiwiz/gkeepapi/blob/main/docs/index.rst), [gpsoauth's alternative flow](https://github.com/simon-weber/gpsoauth#alternative-flow).

The consumer Google sign-in/token exchange is unofficial. Errors such as `BadAuthentication`, `NeedsBrowser` or `MissingDroidguard` can depend on Google/account policy. First obtain a fresh cookie while signed into the intended account. Complete any Google security challenge yourself and retry. If Google still rejects the exchange, there is no verified universal workaround; inspect [upstream gpsoauth issues](https://github.com/simon-weber/gpsoauth/issues). The command reports a safe error without printing Google's raw response or saving unsuccessful credentials. Do not disable two-factor authentication or send tokens to third-party token generators.

## Credential storage

Supported native vaults are Windows Credential Manager, macOS Keychain, Linux Secret Service and KWallet. The entry is service `keep-context`, account `account`. Plaintext/unknown keyring backends and automatic plaintext fallbacks are rejected. A working Linux desktop vault/unlocked session is required for local setup.

For headless deployment, inject these through the host's secret manager:

| Variable | Purpose |
| --- | --- |
| `KEEP_EMAIL` | Account email; required together with master token. |
| `KEEP_MASTER_TOKEN` | Google master token. Treat it like an account password. |
| `KEEP_ANDROID_ID` | Optional 16-character device identifier; use the setup identifier if provisioned separately. Default `0123456789abcdef`. |
| `KEEP_CONNECT_PASSWORD` | Separate 20+ character owner password; required for HTTP access. |
| `KEEP_PUBLIC_URL` | Non-secret stable HTTPS origin, without `/mcp`. |

There is no automatic `.env` loading. Do not put secret assignments into shell commands/history, committed files, or tool calls. Use a real secret manager or OS vault. Env mode requires both email and token and never silently falls back to another account.

Google master tokens are account-wide, not guaranteed read-only at Google. Read-only access is enforced by this application; restrict who can access its host. Only the distinct MCP tokens reach ChatGPT. Those tokens have the `keep:read` scope, a server-specific audience, a one-hour access lifetime, and rotating refresh tokens lasting up to 30 days.

## Disconnect or change account

Stop the running server. Run `uv run keep-context disconnect` to remove its local vault credentials. This does not revoke Google's device/session; use your Google account security settings to revoke the relevant session/token if needed. Remove the plugin from ChatGPT.

After reconnecting Google, start the stable server once with `--reset-access` to invalidate saved MCP connections:

```sh
uv run keep-context serve --public-url https://keep.example.com --reset-access
```

Then connect ChatGPT again. Quick tunnel startup automatically invalidates old access because the hostname changes. Do not run multiple server processes against one OAuth state file.
