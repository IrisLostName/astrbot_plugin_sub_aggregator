# Subscription Aggregator Project Notes

## Current status

- Rebuild started in `astrbot_plugin_sub_aggregator_rebuild`; the old plugin directory and Git history remain untouched.
- The pure core is split into content detection, protocol adapters, normalization, merging, YAML output, source readers, refresh orchestration, state persistence, and HTTP serving.
- The rebuilt HTTP service has a static internal `/sub/healthz` route registered separately from the token route, fixing the old documented-but-missing health endpoint.
- Local Mihomo baseline is `Mihomo Meta alpha-fe22fdd windows amd64` (2026-08-17, `with_gvisor`); help confirmed `-v` for version and `-t -f <file>` for configuration checking.
- `python -m compileall` and the full `pytest -q` suite have passed; the subscription plugin has 22 passing tests.
- The default refresh profile is now MetaCubeX MRS plus boot-safe DNS, with `minimal` retained only for diagnosis.
- The runtime writes `subagg.log` under `/AstrBot/data/runtime/astrbot_plugin_sub_aggregator`; HTTP startup failures, refresh failures, source issues, and successful publishes are recorded without subscription contents.
- `localfile` imports an AstrBot `File` component or a local path/HTTP(S) URL into a persistent `local_sources` directory; configuration stores only metadata and file path.
- The default refresh task records its next scheduled time for `status`.
- Three real local samples produced 127 parsed nodes, 122 unique semantic nodes, and 122 output nodes; exactly 5 duplicate connections were merged. The input/output fingerprint sets match exactly.
- The 122-node output passed Mihomo Alpha `-t -f`, a temporary loopback controller API check, and actual MRS provider loading: all 12 providers registered and all 12 MRS files downloaded non-empty.
- The temporary credential-bearing validation YAML and API/provider runtime directories were created only under `D:\\courses\\mihomo` and removed after validation.
- HTTP integration tests are included in the full suite and pass because the declared dependencies are installed.

## Stable decisions

- Input classification is content-based. Filename, source name, URL suffix, and response Content-Type are context only.
- Remote sources may require a per-source `clash-verge` User-Agent.
- Local/uploaded YAML and remote YAML use the same detection and parsing path.
- Final semantic output is Mihomo/Clash YAML. Base64 is not a separate node format.
- A failed refresh must not replace the last successful output by default.
- Egern-derived DNS/groups are no longer the default. The maintained MetaCubeX MRS profile is default; the old Egern sources remain documented as historical/candidate material only.
- The default `metacubex` profile uses 12 MetaCubeX MRS providers, boot-safe DNS without GeoSite/GeoIP startup downloads, and region/service proxy groups. All 12 providers downloaded as non-empty files in an isolated Mihomo Alpha runtime.
- Default commands are implemented: `help`, `bind`, `url`, `status`, `refresh`, `list`, `add`, `localfile`, and `remove`.
- The standalone AstrBot loader path is bootstrapped before `from subagg...`; upload packages must keep `main.py` and `subagg/` as siblings.

## Unresolved

- Real AstrBot container persistence and source-port firewall behavior are not yet verified.
- Remote source refresh through the real `clash-verge` UA has not been run against a live user source in this workspace.
- Individual proxy reachability, DNS query behavior, and rule matching still require a controlled live-node test; configuration/provider loading alone is not proof of connectivity.

## Common commands

```bash
pytest -q
python -m compileall .
```
