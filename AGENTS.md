# AstrBot 插件开发规范

本文件适用于 `astrbot_plugin_sub_aggregator`，供 Codex、Claude Code 及其他代码代理读取。

## 项目边界

- 本插件只负责订阅源拉取、节点解析合并、Clash/Mihomo 配置输出和变化通知。
- Cloudflare Tunnel、`cloudflared` 守护、Bot 后台连通性检查属于独立的 `astrbot_plugin_cloudflare_tunnel` 插件。
- HTTP 出口的 `/sub/health` 路由是订阅服务的被动状态接口，不在本插件内创建定时保活任务。

## 修改要求

- 修改前先阅读 `main.py`、`src/subagg_core.py`、`_conf_schema.json`、`metadata.yaml` 和相关测试。
- 核心逻辑优先放在 `src/subagg_core.py`；`main.py` 负责 AstrBot 生命周期、命令、通知和 HTTP 服务。
- 兼容导入时保留 `src` 包结构，不要删除 `src/__init__.py` 或根目录兼容 shim。
- 节点名称必须保留来源备注，格式为 `[来源名]节点名`；更新和移除通知必须优先使用可读节点名，不能把 fingerprint 当作名称展示。
- 变化通知每类最多展示 50 个节点，新增、更新、移除分组并逐行输出。
- 定时刷新任务必须捕获单次刷新异常并继续下一轮；取消任务时要正确传播 `asyncio.CancelledError`。
- 分流规则配置要保持 `mihomo_metacubex` 等既有 profile 的兼容性，不要在没有测试的情况下改动远程 rule-provider URL。

## 配置与安全

- 不要把机场订阅 URL、访问 token、Cloudflare Tunnel token、邮箱、QQ 会话 ID 或运行日志提交到 Git。
- README 和示例只能使用占位符；日志和状态输出中的 token 必须脱敏。
- 配置字段改动后同步更新 `_conf_schema.json`、README 和必要的兼容读取逻辑。
- 每次发布代码或行为变更，都必须同步提升 `metadata.yaml` 与 `main.py` `@register` 中的版本号。

## 验证与发布

```powershell
python -m compileall .
python -m unittest discover -s tests -v
git diff --check
```

提交前确认完整插件树包含 `src/`、测试、schema、metadata 和 README。不要提交 `__pycache__`、日志、本地合并结果或订阅内容。

