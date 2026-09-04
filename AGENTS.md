# Agent rules

- This plugin owns subscription fetch, content detection, protocol conversion, Mihomo YAML output, refresh, persistence, and subscription HTTP. It must not import or manage the Cloudflare Tunnel plugin.
- Parse by content, never by source name, URL suffix, filename, or response Content-Type. Local/uploaded YAML and remote YAML share the same parser.
- Root cause first: add a reproducing pytest before changing behavior. Run the focused test and the full suite after the fix.
- Do not write real subscription URLs, tokens, UUIDs, passwords, private keys, session IDs, or complete runtime logs into source, tests, docs, or output.
- Runtime output and state must use an explicitly configured persistent `/AstrBot/data/...` directory in production.
- Keep `metadata.yaml`, `main.py @register`, market registry, schema, README, and migration notes synchronized when behavior or configuration changes.

Common commands:

```bash
pytest -q
python -m compileall .
```
