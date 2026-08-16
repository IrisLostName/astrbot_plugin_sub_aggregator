# AstrBot 订阅聚合助手

AstrBot 插件，用于按配置顺序拉取多个机场订阅、保留来源备注、合并节点并输出一份 Clash/Mihomo 订阅。插件也提供本地 HTTP 出口和节点变化通知。

Cloudflare Tunnel 和 `cloudflared` 守护已经拆分到 [`astrbot_plugin_cloudflare_tunnel`](../astrbot_plugin_cloudflare_tunnel)，本插件不负责 Tunnel 进程、Bot 后台保活或公网链路重启。

## 功能

| 功能 | 说明 |
| --- | --- |
| 多订阅聚合 | 按优先级和配置顺序拉取并去重 |
| 自定义 UA | 支持全局 UA 和单个订阅源 UA |
| 来源备注 | 节点名称保留为 `[来源名]节点名` |
| Clash/Mihomo 输出 | Clash YAML 输入会合并 `proxies`，并生成代理组和规则 |
| MetaCubeX 分流 | `mihomo_metacubex` 会写入远程 `.mrs` rule-provider |
| 定时刷新 | 启动后立即刷新，随后按更新间隔刷新；单次失败不会终止后续轮次 |
| 变化通知 | 新增、更新、移除分组逐行显示，每类最多 50 条 |
| 本地 HTTP 出口 | 提供带 token 的订阅 URL |
| 本地文件 | 可保存 YAML、最近结果和元数据 |

## 安装

将完整目录放入：

```text
/AstrBot/data/plugins/astrbot_plugin_sub_aggregator
```

目录中的 `src/` 必须一并复制。然后重启 AstrBot，或使用 WebUI 重载插件。

安装后：

1. 在插件配置中填写 `机场订阅源`。
2. 使用 `/subagg bind` 绑定接收通知的会话。
3. 使用 `/subagg refresh` 手动刷新并验证订阅源。
4. 使用 `/subagg status` 检查 HTTP 服务和最近刷新时间。
5. 使用 `/subagg url` 获取带 token 的订阅地址。

## 主要配置

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `subscription_sources` | 空 | 机场订阅列表，支持名称、URL、优先级、单独 UA、启用状态 |
| `manual_node_sources` | 空 | 粘贴单条或多条已解密的节点链接 |
| `update_interval_minutes` | `180` | 定时拉取间隔，单位分钟，最小为 1 |
| `startup_push` | `true` | AstrBot 启动后刷新并按配置推送结果 |
| `notify_on_node_change` | `true` | 节点变化时通知 |
| `notify_on_error` | `true` | 拉取或输出失败时通知 |
| `user_agent_preset` | `mihomo` | 全局 UA 预设；也支持 `clashmeta`、`clash`、`flclash`、`karing`、`custom` |
| `user_agent` | `mihomo/1.19.27` | 预设为 `custom` 时使用的 UA |
| `request_timeout_seconds` | `20` | 单个订阅请求超时 |
| `rule_profile` | `mihomo_metacubex` | Clash/Mihomo 分流模板 |
| `deduplicate_nodes` | `true` | 合并时按节点指纹去重 |
| `save_local_files` | `true` | 保存聚合结果到本地 |
| `local_output_dir` | 空 | 留空表示插件目录 |
| `local_output_basename` | `merged-subscription` | 输出文件名前缀 |
| `http_enable` | `true` | 启用本地订阅 HTTP 出口 |
| `http_host` | `0.0.0.0` | HTTP 监听地址 |
| `http_port` | `8077` | HTTP 监听端口 |
| `public_base_url` | 空 | 公网域名或 IP，例如 `https://sub.example.com` |
| `path_prefix` | `/sub` | 订阅路径前缀 |
| `access_token` | 自动生成 | 订阅访问 token；泄露后清空并重载插件 |
| `max_change_names` | `50` | 变化通知展示上限，按新增、更新、移除顺序计算 |

## 输出和规则

后台 schema 已移除 v2ray 专用导出配置。插件的目标输出是 Clash/Mihomo；输出结果的实际格式会记录在 `/subagg status` 和本地 metadata 中。

`mihomo_metacubex` 会在生成的 YAML 中写入 `rule-providers` 和 `RULE-SET`。规则文件由 Mihomo 客户端运行时从远程地址下载，因此客户端仍需要能够访问规则源。若客户端无法下载远程规则，可临时使用 `inline`、`basic` 或 `none`。

可用规则模板：

| 值 | 说明 |
| --- | --- |
| `mihomo_metacubex` | 推荐，MetaCubeX `.mrs` 规则 |
| `mihomo_dustinwin` | 使用 DustinWin `.mrs` 规则 |
| `mihomo_ruleset` | 兼容旧版 blackmatrix7 YAML rule-provider |
| `inline` | 无远程依赖的简化规则 |
| `basic` | 基础直连/代理规则 |
| `none` | 不写分流规则，使用 global 模式 |

## 节点备注和变化通知

机场源名称会加到节点名之前：

```text
原名称：Hong Kong 01
来源名称：机场A
输出名称：[机场A]Hong Kong 01
```

变化通知按新增、更新、移除分组逐行显示。每类最多展示 50 个节点；超出部分只显示该类别的剩余数量。插件会从上一轮保存的节点快照中恢复移除节点的真实名称，不应显示 fingerprint。

## HTTP 地址

假设公网域名为 `https://sub.example.com`、端口为 `8077`、路径前缀为 `/sub`，则订阅地址为：

```text
https://sub.example.com/sub/YOUR_TOKEN
```

按当前解耦方案，订阅插件不创建 HTTP/Tunnel 保活任务。需要检查订阅 HTTP 出口、Bot 后台或 cloudflared 时，请在独立 Cloudflare 插件中配置实际可访问的回源地址。

## 指令

| 指令 | 作用 |
| --- | --- |
| `/subagg help` | 查看帮助 |
| `/subagg bind` | 绑定当前会话接收通知 |
| `/subagg status` | 查看 HTTP 服务、订阅 URL、最近刷新和节点数量 |
| `/subagg refresh` | 立即拉取并聚合 |
| `/subagg url` | 查看订阅 URL |
| `/subagg list` | 查看机场列表 |
| `/subagg add 名称 URL` | 添加机场订阅 |
| `/subagg remove 名称` | 删除机场订阅 |

## 自动更新排查

重载或更新插件后建议完整重启 AstrBot 容器，尤其是遇到 `8077 address already in use` 时。仅重载插件可能留下旧 HTTP 实例占用端口。

1. `/subagg status` 确认 `服务：已启动` 和 `定时任务：运行中`。
2. `/subagg refresh` 确认手动拉取成功。
3. 等待一个 `update_interval_minutes` 周期，确认 `最近刷新` 变化。
4. 检查日志中的定时刷新错误和失败通知。

定时任务会继续运行，即使某一次机场请求失败；失败会记录日志，并按配置通知。

## 安全和发布

- 不要在公开群、README 或 Git 中粘贴真实订阅 URL、访问 token 或运行日志。
- `access_token` 泄露后清空配置并重载插件，使其重新生成。
- 发布前运行 `python -m compileall .`、测试和 `git diff --check`。
- `AGENTS.md` 中记录了本插件的开发规范。
