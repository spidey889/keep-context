# Working on Keep Context

- Read README.md, LOGIC.md and CHANGELOG.md before changing behavior.
- Keep this a single-owner, read-only MVP. Use the official MCP SDK and maintained Google client dependencies. Do not add write tools or weaken authentication to simplify setup.
- Never print/log Google tokens, upstream responses, note contents, connection passwords or OAuth tokens. Use fake credentials in tests. Do not inspect browser credentials or automate a browser.
- Treat Google's consumer authentication as unofficial. Do not claim live account/ChatGPT verification from mocked tests; record the proof boundary.
- Pin and inspect gkeepapi/gpsoauth internals when updating the adapter. Preserve the empty mutation-payload guard.
- Update LOGIC.md after meaningful behavior changes and CHANGELOG.md for decisions useful in future work.
- Run relevant tests, `uv run ruff check .`, formatting checks and `git diff --check`. Stage only intended files. After coding tasks, commit and push the working branch without asking, as requested by the owner.
