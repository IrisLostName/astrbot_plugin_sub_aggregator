# Validation

## Status

- Target core: `Mihomo Meta alpha-fe22fdd windows amd64` (2026-08-17, `with_gvisor`).
- `python -m pytest -q` passes with 17 tests; `python -m compileall` passes for both rebuilt plugins.
- The three user-provided local samples contain 127 parsed nodes, 122 unique semantic nodes, and 122 YAML output nodes; 5 exact duplicates are intentionally merged. Input/output node fingerprint sets match exactly.
- The 122-node YAML passes `mihomo -t -f`; a temporary loopback Mihomo controller also exposed working `/version`, `/configs`, and `/proxies` APIs.
- The temporary credential-bearing validation YAML and API work directory were created only under `D:\courses\mihomo`, never logged or committed, and removed after every check.
- This proves Alpha configuration syntax/loading and basic controller visibility only. It does not prove individual node reachability, rule-provider downloads, DNS behavior, AstrBot integration, or Cloudflare Tunnel behavior.
- HTTP integration tests are part of the 17-test suite and pass with the declared dependencies installed.

## Required sequence

1. Run focused pytest tests.
2. Run the full pytest suite and compileall.
3. Use the local Mihomo executable in a temporary directory and record its `/version`.
4. Load generated YAML in an isolated core process and inspect `/configs`, `/proxies`, `/providers/rules`, `/logs`, and protocol health endpoints.
5. Use a non-sensitive real node for one connection test.
