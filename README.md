# AstrBot 订阅聚合助手（重构版）

本目录是从旧插件重新构建的工作树。它按内容识别远程、本地和上传订阅，转换必要协议并输出 Mihomo/Clash YAML。

## AstrBot layout

Install the complete plugin tree under `AstrBot/data/plugins/astrbot_plugin_sub_aggregator`. Keep runtime output, snapshots, and state under `AstrBot/data/runtime/astrbot_plugin_sub_aggregator`; do not write persistent data into the plugin directory. Third-party dependencies belong in `requirements.txt`, and network I/O uses asynchronous libraries.


## Commands

- `/subagg help` — show commands.
- `/subagg bind` — bind the current session for failure notifications.
- `/subagg url` — show the tokenized subscription URL.
- `/subagg status` — show runtime, node, HTTP, and rule profile status.
- `/subagg refresh` — refresh sources now.
- `/subagg list` — list configured sources without printing their URLs.
- `/subagg add NAME URL` — add a remote source; configure a per-source `clash-verge` User-Agent in the plugin settings when required.
- `/subagg localfile NAME` — import a QQ `File` component from the same message; the file is copied into the persistent `local_sources` directory.
- `/subagg localfile NAME PATH_OR_URL` — import a local file path or HTTP(S) file without pasting its content.
- `/subagg remove NAME` — remove sources with the given name.

The public subscription path is fixed to `/sub/<token>` and defaults to `https://sub.tomori.cloud`. Route that hostname to the local subscription HTTP service through Cloudflare Tunnel without the Bot email Access policy. The internal health path is fixed to `/sub/healthz` for Tunnel checks only.


The default `metacubex` profile uses MetaCubeX MRS rule providers and boot-safe DNS. Use `minimal` only for diagnosis; it does not include the maintained DNS/rule profile.

The old Egern-derived profile is not the default and is retained only as historical context.
