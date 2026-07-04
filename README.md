# AstrBot 订阅聚合助手

这个插件用于把多个机场订阅 URL 拉取后按配置顺序合并，输出一个总订阅 URL。

## 功能

| 功能 | 状态 |
| --- | --- |
| 多机场订阅 URL 配置 | 已支持 |
| 按顺序 Base64 解码并合并节点 | 已支持 |
| 输出 Base64 总订阅 | 已支持 |
| Clash YAML 订阅解析与聚合 | 已支持 |
| 节点名追加 `[机场名]` | 已支持 |
| 每 3 小时定时拉取 | 默认开启 |
| AstrBot 启动后推送一次 | 默认开启 |
| 拉取失败日志与 QQ 通知 | 已支持 |
| 节点新增/移除通知 | 已支持 |
| 自托管短路径订阅 URL | 已支持 |
| 按机场选择/自定义拉取 UA | 已支持 |
| 后台手动节点源 | 已支持 |
| 聚合结果保存到本地文件 | 已支持 |
| v2rayN 兼容订阅导出 | 已支持 |
| Telegram 风格按钮 | QQ 官方机器人 WS 下不保证支持，暂用指令和后台配置 |
| subconverter 规则转换 | 暂未内置 |

## 安装

1. 把本目录放进 `AstrBot/data/plugins/astrbot_plugin_sub_aggregator`。
2. 重启 AstrBot，或在 WebUI 插件管理里重载插件。
3. 在插件配置里填写 `机场订阅源`。
4. 在 QQ 里发送 `/subagg bind`，把当前会话设为通知接收处。
5. 发送 `/subagg refresh` 立即生成一次聚合订阅。
6. 发送 `/subagg url` 查看总订阅 URL。

## 关键配置

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `subscription_sources` | 空 | 多个机场订阅源，按列表顺序合并 |
| `subscription_sources[].priority` | `100` | 订阅源优先级，数字越小越靠前 |
| `manual_node_sources[].priority` | `100` | 手动节点源优先级，数字越小越靠前 |
| `update_interval_minutes` | `180` | 每 3 小时更新一次 |
| `user_agent_preset` | `mihomo` | 全局拉取 UA 预设 |
| `user_agent` | `mihomo/1.19.27` | 自定义全局 UA，预设为 `custom` 时使用 |
| `public_base_url` | 空 | 建议填公网 IP/域名，例如 `http://1.2.3.4:8077` |
| `http_port` | `8077` | 插件自带订阅 HTTP 出口端口 |
| `access_token` | 自动生成 | 订阅 URL 的访问 token |
| `output_format` | `auto` | 自动判断传统 Base64 或 Clash YAML |
| `output_base64` | `true` | 输出传统 Base64 订阅 |
| `rule_profile` | `mihomo_ruleset` | Clash YAML 规则模板；填 `none` 可关闭分流规则 |
| `save_local_files` | `true` | 每次刷新成功后保存本地文件 |
| `local_output_dir` | 空 | 留空表示插件目录 |
| `local_output_basename` | `merged-subscription` | 本地输出文件名前缀 |

## 节点命名

插件会把配置里的订阅源名称写入节点名：

| 原节点名 | 订阅源名称 | 输出节点名 |
| --- | --- | --- |
| `🇭🇰 Hong Kong 01` | `机场A` | `🇭🇰[机场A] Hong Kong 01` |
| `Node 01` | `机场A` | `[机场A]Node 01` |

手动节点源也使用同样规则，名称来自 `manual_node_sources` 里的 `name`。

## 手动节点源

后台 `manual_node_sources` 可以粘贴已经解密的节点链接，例如：

```text
vless://...
hysteria2://...
trojan://...
```

每个手动节点源都有 `name`、`nodes`、`priority`、`user_agent`、`enabled`。其中 `user_agent` 目前只用于记录来源，手动节点不会发起网络请求。

## 分流规则

默认 `rule_profile=mihomo_ruleset` 会生成带 emoji 的代理组，并通过远程 `rule-providers` 拉取常见规则。Microsoft / OneDrive / Office / GitHub / OpenAI 等常见服务默认走代理组。可选：

| 值 | 说明 |
| --- | --- |
| `mihomo_ruleset` | 推荐模板，带 emoji 分组，使用远程 rule-providers |
| `inline` / `emoji_microsoft_proxy` | 无远程依赖的简化内置规则，微软服务走代理组 |
| `basic` | 简单直连内网与 CN，其余走代理 |
| `none` | 不写 `rules`，并把 YAML 设为 `mode: global` |

ACL4SSR 的 `.ini` 通常是给 subconverter 使用的远程转换模板，不是可以直接放进 Mihomo `rules:` 的规则文件。本插件默认使用 blackmatrix7 的 Clash 规则集作为远程 rule-providers；如果客户端不支持 rule-providers，改用 `inline` 或 `none`。

## 客户端建议

| 客户端 | 建议订阅 | 说明 |
| --- | --- | --- |
| Karing | 主订阅 URL | 更适合 Mihomo/sing-box 风格节点和 YAML |
| Betterbox | 主订阅 URL | 如果它按 sing-box/Mihomo 解析成功，优先用主订阅 |
| v2rayN | `/sub/你的token/v2ray` 或 `merged-subscription.v2ray.txt` | v2rayN 更适合传统 Base64 分享链接订阅 |
| 老 Clash | 不建议 | `hysteria2`、`vless xhttp`、Reality 等新字段经常不兼容 |

## 国旗补全

不建议在主刷新流程里直接探测每个节点出口 IP：这需要真实连接每个代理再访问 IP 查询服务，速度慢，也容易被限流。更稳的做法是后续单独做一个“节点探测任务”，把探测到的国家缓存起来，再用于改名。

## 本地输出文件

刷新成功后默认写到插件目录，也就是部署在容器里时：

```text
/astrbot-napcat-bjiqg3/data/plugins/astrbot_plugin_sub_aggregator/
```

| 文件 | 说明 |
| --- | --- |
| `merged-subscription.yaml` | 当输出格式为 Clash YAML 时生成 |
| `merged-subscription.base64.txt` | 当输出格式为 Base64 时生成 |
| `merged-subscription.txt` | 当输出格式为 plain 时生成 |
| `merged-subscription.latest` | 最近一次聚合结果，不管格式都会覆盖 |
| `merged-subscription.v2ray.txt` | v2rayN 兼容的 Base64 分享链接订阅。仅包含能从原始 `vless://` 等链接保留下来的节点 |
| `merged-subscription.metadata.json` | 最近刷新时间、节点数、输出格式、文件路径 |

## 指令

| 指令 | 作用 |
| --- | --- |
| `/subagg help` | 查看帮助 |
| `/subagg bind` | 绑定当前会话接收通知 |
| `/subagg url` | 查看聚合订阅 URL |
| `/subagg status` | 查看 HTTP 出口、健康检查地址、最近刷新状态 |
| `/subagg refresh` | 立即拉取并聚合 |
| `/subagg list` | 查看机场列表 |
| `/subagg add 名称 URL` | 添加一个机场订阅 |
| `/subagg remove 名称` | 删除指定名称的机场订阅 |

## HTTP 无响应排查

| 检查项 | 说明 |
| --- | --- |
| URL 写法 | IPv4 不要加方括号，正确格式是 `http://公网IP:8077/sub/token` |
| 健康检查 | 先访问 `http://公网IP:8077/sub/health`，能返回 `ok` 才说明 HTTP 出口通了 |
| Docker 端口 | 如果 AstrBot 在 Docker 里运行，需要把容器的 `8077` 映射到宿主机 |
| 防火墙/安全组 | 云服务器需要放行 TCP `8077` 入站 |
| 插件状态 | 在 QQ 里发送 `/subagg status` 查看服务是否启动 |

## 说明

- 插件只处理常见分享链接：`ss`、`ssr`、`vmess`、`vless`、`trojan`、`hysteria`、`hysteria2`、`hy2`、`tuic`。
- 如果某个机场会按客户端 UA 下发不同内容，可以在该机场订阅源的 `user_agent` 里单独填写完整 UA，例如 `Karing/1.2.21.2406 platform/windows`。
- 全局 UA 预设可填：`mihomo`、`clashmeta`、`clash`、`v2ray`、`flclash`、`karing`、`custom`。
- 如果机场给的是 Clash YAML 订阅，插件会聚合 `proxies` 并生成一份简化 Clash 配置；规则默认使用本插件生成的基础规则。
- 节点变化通知只提示新增/移除节点，不会再次发送总订阅 URL。
- 总订阅 URL 含 token，请不要发到公开群。
