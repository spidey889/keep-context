# Changelog

## 0.1.0 — 2026-10-06

- Built the consumer-account Keep MVP on gkeepapi/gpsoauth after comparing official APIs and existing MCP servers. The official enterprise API cannot provide the intended normal consumer OAuth flow.
- Added search, full-note retrieval, recent notes, labels and task discovery, preserving checklist hierarchy/checked state and excluding trash.
- Added official SDK stdio and protected Streamable HTTP, owner consent, DCR/PKCE, audience-bound tokens, refresh rotation and encrypted restart persistence.
- Isolated Google authentication in a hidden-input local setup command using native OS vaults, plus explicit secret-manager deployment support. Added safe errors, network deadlines and a network-level write guard.
- Added optional one-command HTTPS tunnel startup, setup/deployment/research documentation, linting and regression tests using real MCP clients/server processes.
- Discovered SDK structured-output and OAuth error/revocation quirks through wire tests; documented narrow compatibility handling in source. Real Google/ChatGPT account linking remains a manual verification boundary when credentials are unavailable.
- Verified public HTTPS/OAuth/MCP against demo notes. An initial tunnel reachability failure led to waiting for a registered connection and selecting HTTP/2; the complete remote smoke then passed.
