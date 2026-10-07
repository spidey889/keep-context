# Integration research — 2026-10-06

Follow-up, 2026-10-07: [guided setup decisions](SIMPLER_SETUP.md) remove avoidable browser handoffs without replacing consumer authentication or weakening consent. The normal public target is install, Google sign-in, ChatGPT approval. Stable hosting and actual Chrome/ChatGPT publication remain separate release work.

## Decision

Use Python, maintained `gkeepapi`/`gpsoauth` dependencies, and the official `mcp` SDK. One consumer account per process. Authenticate Google once in a local hidden-input command; authenticate ChatGPT separately with OAuth 2.1/PKCE. Use Streamable HTTP for ChatGPT and stdio for local clients. No notes database, embeddings, Google Cloud project, paid AI API, frontend build, or write tools are needed for this MVP.

## Approaches inspected

| Approach | Finding | Decision |
| --- | --- | --- |
| [Google Keep REST API](https://developers.google.com/workspace/keep/api/guides) | Enterprise administration and domain-wide delegation, not an ordinary consumer OAuth connection. | Unsuitable for the consumer-account MVP. |
| [gkeepapi](https://github.com/kiwiz/gkeepapi), [client docs](https://github.com/kiwiz/gkeepapi/blob/main/docs/index.rst) | Unofficial mobile Keep client with sync, notes, lists, labels and token refresh. MIT licensed; published version 0.17.1 inspected. | Reuse directly and pin the adapter dependency. |
| [gpsoauth](https://github.com/simon-weber/gpsoauth) | Handles mobile master-token exchange. The documented alternate flow requires an `oauth_token` cookie from manual EmbeddedSetup login. Account-wide token; password login is discouraged by gkeepapi. Version 2.0.0 inspected. | Reuse protocol implementation; add a network deadline at its existing TLS adapter boundary. |
| [kud/mcp-google-keep](https://github.com/kud/mcp-google-keep) | gkeepapi-based MCP and macOS Keychain setup; reviewed `keep_setup.py`, including its manual cookie exchange. Includes writes and auth handling that can print upstream errors. | Useful reference, but no code copied; use native-vault support and safe errors. |
| [staryxchen/google-keep-mcp](https://github.com/staryxchen/google-keep-mcp) | gkeepapi-based personal task/knowledge tools, environment master token, optional disk cache, stdio-oriented setup. | Confirms viable library approach; omit write workflow and plaintext note caching. |
| [shanewwarren/mcp-google-keep](https://github.com/shanewwarren/mcp-google-keep) | Official Keep API with Google Cloud/OAuth setup and broad note-writing features. | OAuth here does not establish consumer Keep API access; not the selected consumer backend. |
| [ag2-mcp-servers/google-keep-api](https://github.com/ag2-mcp-servers/google-keep-api) | Generated wrapper around the official OpenAPI spec. | Does not remove enterprise authorization constraints. |
| [OpenAI custom MCP](https://developers.openai.com/api/docs/guides/custom-mcp-server), [auth](https://developers.openai.com/plugins/build/auth), [tool contracts](https://developers.openai.com/api/docs/mcp) | Remote Streamable HTTP/SSE, OAuth discovery, PKCE and DCR; private data must be authorized. Custom API keys are not a normal ChatGPT authentication option. | Protected HTTP, standard SDK OAuth routes, DCR, audience-bound opaque tokens and read-only `search`/`fetch`. |

An ordinary consumer **Connect with Google** button cannot be promised from these sources. Google may change/challenge private mobile authentication, including errors tracked in [gpsoauth issues](https://github.com/simon-weber/gpsoauth/issues). This is the main external limitation, isolated in local setup. No passwords or cookies are collected by the remote consent page. A Google Takeout-only reader would avoid live authentication but would not satisfy account connection/live notes; it was not substituted for the requested product.

The official MCP SDK handles protocol framing, OAuth discovery/registration, client authentication and PKCE validation. Application code supplies owner consent, token lifecycle and persistence. Two SDK 1.30 interoperability gaps discovered by tests are isolated and commented: authorization's error enum omits `invalid_target`, and revocation requires an optional `client_secret` form field. The app rejects a bad authorization resource as `invalid_request` and supplies an empty revocation field for public clients without bypassing SDK client authentication.

No browser automation or Computer Use was used for research or validation.
