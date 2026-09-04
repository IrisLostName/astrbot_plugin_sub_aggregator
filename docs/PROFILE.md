# Mihomo DNS and rule profile

The default `metacubex` profile uses rule providers from the MetaCubeX `meta-rules-dat` repository:

```text
https://github.com/MetaCubeX/meta-rules-dat
```

The provider files are MRS and are refreshed every 86400 seconds. The profile includes ads, mainland China, Apple, Microsoft, Google, GitHub, YouTube, Telegram, Netflix, TikTok, Discord, and OpenAI categories.

The DNS profile deliberately does not use `geosite:cn` in `nameserver-policy` during bootstrap. That field can force Mihomo to download `GeoSite.dat` before DNS is ready, creating a circular startup dependency in a restricted container. Mainland DNS uses AliDNS and Tencent DoH; overseas fallback and proxy-server DNS use Cloudflare and Google DoH. Mainland routing is handled by the `cn.mrs` rule provider.

Provider URLs are public and were checked with HTTP HEAD during development. The full profile was loaded by the local Mihomo Alpha binary, and all 12 MRS provider files were downloaded as non-empty files in an isolated temporary runtime directory.

If the remote rule repository changes format or becomes unavailable, set `rule_profile` to `minimal` for diagnosis. Do not silently replace MRS with Loon, Surge, or Egern provider files.
