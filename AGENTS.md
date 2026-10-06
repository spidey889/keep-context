# Working on Keep Context

- Read README.md, LOGIC.md and CHANGELOG.md before changing behavior.
- Keep local `serve` single-owner and read-only. The separately opted-in hosted pilot must resolve every read from the SDK-authenticated account subject; never share the local owner's vault or backend between users. Use the official MCP SDK and maintained Google client dependencies. Do not add write tools or weaken authentication to simplify setup.
- Never print/log Google tokens, upstream responses, note contents, connection passwords or OAuth tokens. Use fake credentials in tests. Do not inspect browser credentials. Browser automation needs explicit owner authorization; respect the browser tool's restrictions and never work around blocked extension/settings access.
- The product's companion extension may handle only the user's explicitly approved, time-limited EmbeddedSetup connection. This is not permission for the coding agent to inspect profiles, cookies or browser credentials. Hand off installation, authentication challenges or permissions when the tool cannot safely perform them. Keep actual sign-in proof separate from website/ChatGPT UI checks.
- Treat Google's consumer authentication as unofficial. Do not claim live account/ChatGPT verification from mocked tests; record the proof boundary.
- Pin and inspect gkeepapi/gpsoauth internals when updating the adapter. Preserve the empty mutation-payload guard.
- Update LOGIC.md after meaningful behavior changes and CHANGELOG.md for decisions useful in future work.
- Run relevant tests, `uv run ruff check .`, formatting checks and `git diff --check`. Stage only intended files. After coding tasks, commit and push the working branch without asking, as requested by the owner.
