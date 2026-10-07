# Make the connection ordinary

The user's job is to sign in and approve access. The product should carry connection state, detect completion, and choose the next page. Asking users to understand extension popups, token expiry, MCP addresses or separate connection passwords is avoidable work.

## Changes in 0.3.0

| Previous handoff | What the product does now |
| --- | --- |
| Pin the extension and find its popup | First installation opens setup. The icon opens or reuses that page. |
| Reopen the popup after Google sign-in | Detect completion by events and polling, then focus the validated setup/consent tab once. |
| Click Finish while Google keeps loading | No Finish button. Server progress is checked before a cookie can be exchanged again. |
| Remember which connection finished | Google, ChatGPT and Ready are separate states. Ready requires a live account-bound grant. |
| Tick an additional agreement box | A clear credential/host notice immediately precedes one explicit “Agree and sign in” action and Chrome's permission prompt. |
| Copy an MCP address for every installation | A configured real ChatGPT listing opens directly. Unpublished previews reveal one guided fallback. |
| Restart Google setup when ChatGPT's link ends | Preserve Google access, return to ChatGPT and start a new approval request. |

The setup page does not automatically approve access, inspect other pages, collect Google passwords or add browser permissions. Focus changes revalidate the owned URL/ticket; a repurposed tab is never focused. Closing setup preserves accepted progress. Updates never open surprise tabs.

## The minimum public flow

**Install → sign in with Google → approve ChatGPT.** A store-installed extension, stable hosted service and published/shared ChatGPT listing remove the remaining developer installation and custom-server form. The code supports that path; no store listing or stable production host is claimed. A Chrome publisher account and a ChatGPT publisher/listing are separate things. [Chrome publication](https://developer.chrome.com/docs/webstore/publish), [OpenAI submission](https://developers.openai.com/plugins/deploy/submission).

We retain the Google email field because the current mobile token exchange needs the intended account. Guessing it from other browser accounts or scraping Google's sign-in DOM would add permission and account-selection risks. Google's own login/challenges, Chrome's install/permission approval and ChatGPT's access consent remain explicit. The official Keep API still targets enterprise administration; it does not supply normal consumer OAuth as a replacement. [Google Keep API](https://developers.google.com/workspace/keep/api/guides), [gkeepapi authentication](https://github.com/kiwiz/gkeepapi/blob/main/docs/index.rst).

We did not invent a ChatGPT web install URL, automate its settings, or broaden the helper into a browser-lived notes scraper. The documented custom MCP form remains the fallback until a real listing is available. [OpenAI custom MCP](https://developers.openai.com/api/docs/guides/custom-mcp-server).

## Proof boundary

The previous preview's real Google connection, ChatGPT approval and note retrieval were manually verified by the owner. Version 0.3.0's lifecycle, missed events, lost replies, account-bound readiness and tab ownership have automated coverage, including a real TCP MCP flow driven by simulated browser APIs. Automatic first-install opening and fresh Google return in actual Chrome/Brave still need manual verification. Browser operations remain stopped at the owner's request.

Once the service is online, the smallest next check for an already connected user is: reload the unpacked extension once, open Keep Context and confirm its full setup page shows Ready. Fresh sign-in/automatic return and actual permission removal require a separate test account/session; never disconnect a working account merely to make an automated test pass.
