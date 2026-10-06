# Connect a Google Keep account

## One-time local setup

Run `uv run keep-context connect` in an interactive terminal. Secrets are hidden; noninteractive input is rejected rather than echoed.

1. Enter your Google email.
2. Manually visit <https://accounts.google.com/EmbeddedSetup> in your browser and sign in. Complete Google's consent/challenges if requested. This program does not open or automate your browser.
3. Open browser DevTools. In Brave/Chrome/Edge use **Application → Storage → Cookies → https://accounts.google.com**. In Firefox/Zen use **Storage → Cookies**. Expand the arrow beside Cookies and select the Google domain. If Application is hidden, focus DevTools, press **Ctrl+Shift+P**, type **Show Application**, and press Enter. Copy only the complete **Value** of the **`oauth_token`** cookie, starting with `oauth2_` followed by a number and `/`. A page that keeps loading after consent can be normal.
4. Paste that value promptly into the terminal's hidden prompt and press Enter. **This cookie expires quickly and is single-use:** after a failed attempt, sign in again to obtain a fresh cookie rather than reusing the old one. Prepare the terminal before doing the browser step. The program checks for incorrectly copied values, then exchanges the cookie with Google; the temporary cookie is never saved or printed. [Upstream token types](https://github.com/rukins/gpsoauth-java#types-of-tokens).
5. The command verifies Google authentication and a read-only Keep sync, then saves the verified Google login as **setup progress** in the native OS vault. This progress cannot be loaded by the MCP server and does not replace an existing connected account.
6. Choose and confirm a **separate connection password**, 20 to 1024 characters, ideally a long random password from your password manager. This is the password for the Keep Context authorization screen, not your Google password. A short/long password or a confirmation mismatch asks again without repeating Google sign-in. After a valid password is confirmed, the command saves the completed account and removes setup progress. Only a note count is printed. Run `uv run keep-context doctor` to recheck.

If you interrupt the password step or the final account save fails, rerun `uv run keep-context connect`. It resumes the saved Google login and rechecks Keep access without asking for an email or browser cookie. To discard setup progress and sign into a different account, use `uv run keep-context connect --restart`. `disconnect` removes both the completed account and any setup progress. Progress remains in the native vault until completed or explicitly removed; no token is printed or written to a plaintext file.

If you already have a master token, use `uv run keep-context connect --master-token`; the token prompt is still hidden. The ordinary flow deliberately does not accept Google passwords or app passwords. Upstream discourages password login because it commonly fails modern Google challenges. [gkeepapi documentation](https://github.com/kiwiz/gkeepapi/blob/main/docs/index.rst), [gpsoauth's alternative flow](https://github.com/simon-weber/gpsoauth#alternative-flow).

The consumer Google sign-in/token exchange is unofficial. The command shows only recognized, safe error codes and never prints Google's raw response or unknown error text:

- **BadAuthentication:** the cookie may be expired, already used, incompletely copied, or from a different account. Obtain a fresh cookie for the exact email entered in the terminal and paste it promptly. This code alone does not prove which cause applies; account policy or upstream changes can also reject the exchange.
- **NeedsBrowser:** complete Google's security challenge yourself in the browser, then obtain a fresh cookie.
- **MissingDroidguard:** Google requires device verification that this library cannot provide. There is no verified universal workaround. See [upstream discussion](https://github.com/simon-weber/gpsoauth/issues/81).
- **Other rejection:** details are intentionally suppressed because arbitrary response fields can contain secrets.

If a fresh, correctly copied cookie still fails, report only the displayed safe error message and inspect [upstream gpsoauth issues](https://github.com/simon-weber/gpsoauth/issues). Unsuccessful credentials are never saved. Do not disable two-factor authentication or send tokens to third-party token generators.

## Credential storage

Supported native vaults are Windows Credential Manager, macOS Keychain, Linux Secret Service and KWallet. The service is `keep-context`; `account` holds the completed account and `setup-progress` holds a verified Google login awaiting password setup. Plaintext/unknown keyring backends and automatic plaintext fallbacks are rejected. A working Linux desktop vault/unlocked session is required for local setup.

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
