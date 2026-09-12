# AstrBot 订阅聚合助手

一个面向 AstrBot 的多来源代理订阅聚合插件。

它可以读取远程订阅、本地文件和聊天上传文件，按内容识别 Clash/Mihomo YAML、Base64 订阅和常见分享链接，统一转换为 Mihomo/Clash YAML、sing-box 1.14 JSON 与纯分享链接 Node List，并通过本地 HTTP 服务提供订阅地址。


## 功能概览

- 支持远程 URL、本地文件、内联本地内容和 AstrBot 聊天文件
- 按内容识别输入，不依赖文件名、URL 后缀或响应头
- 支持 Clash/Mihomo YAML、Base64 订阅和常见代理分享链接
- 支持多种代理协议转换：
  - VLESS
  - VMess
  - Trojan
  - Shadowsocks
  - Hysteria / Hysteria2
  - TUIC
  - AnyTLS
  - HTTP / SOCKS
  - WireGuard
- 节点规范化、语义指纹去重和稳定合并
- 数字越小的 `priority` 越优先；相同优先级保持配置顺序
- 生成三种输出：
  - Mihomo / Clash YAML
  - sing-box 1.14 JSON
  - 纯分享链接 Node List（每行一个原始 `ss://`、`vless://`、`vmess://` 等链接）
- 每个订阅源支持节点名称包含/排除正则
- 每个订阅源可选择过滤非法节点，避免单条脏数据阻断整体刷新
- sing-box 支持多个独立节点 outbound 和手动选择
- Mihomo 默认使用单一 `PROXY` 手动选择组
- 支持纯 TUN 输出；关闭 TUN 时不生成 mixed 入站
- 刷新失败时保留上一次成功输出
- 持久化节点状态、输出文件、元数据和运行日志
- 提供带 token 的 HTTP 订阅接口和健康检查接口

（因为我自己在实际使用中很少用到分流，如果很需要分流的话请告诉我）

## 工作流

```text
远程 URL / 本地文件 / 聊天上传文件
                │
                ▼
       内容检测与解码
                │
                ▼
  Clash YAML / Base64 / 分享链接解析
                │
                ▼
       协议适配与节点规范化
                │
                ▼
     按优先级合并并按指纹去重
                │
        ┌───────┴────────┐
        ▼                ▼
 Mihomo / Clash YAML   sing-box JSON
        │                │
        └───────┬────────┘
                ▼
       本地文件与 HTTP 订阅服务
```

核心代码按职责拆分：

```text
subagg/
├── subscription/       内容识别、协议适配、规范化、合并和输出
├── sources/            远程、本地和文件源处理
├── services/           刷新编排、变化通知和来源排序
├── state.py            持久化状态和输出文件
└── http_server.py      HTTP 订阅与健康检查
```

## 安装

将完整插件目录放入 AstrBot 的插件目录：

```text
AstrBot/data/plugins/astrbot_plugin_sub_aggregator/
```

目录至少应包含：

```text
astrbot_plugin_sub_aggregator/
├── main.py
├── _conf_schema.json
├── requirements.txt
└── subagg/
```

安装依赖：

```bash
python -m pip install -r requirements.txt
```

重载或重启 AstrBot 后，在插件配置中设置订阅源。

## 配置订阅源

### 远程订阅

```json
{
  "name": "example-remote",
  "source_type": "remote",
  "url": "https://example.invalid/subscription",
  "user_agent": "clash-verge",
  "priority": 100,
  "enabled": true,
  "notify_changes": true,
  "include_regex": "香港|日本",
  "exclude_regex": "过期|公告",
  "node_list_output": false,
  "filter_invalid_nodes": true
}
```

如果订阅服务要求特定 User-Agent，可以在单个来源上填写 `user_agent`。

来源筛选规则只匹配最终节点名称：`exclude_regex` 优先于 `include_regex`；包含为空表示不限制。`filter_invalid_nodes` 默认关闭，保持严格模式：缺少 `type/server/port`、Reality short-id 非法或分享链接适配失败会阻断本次发布。打开后这些非法节点会被跳过，其他有效节点仍可发布。

`node_list_output` 打开后，该来源中成功解析并通过名称筛选的原始分享链接会额外进入 Node List。Node List 只保留输入中真实存在的分享链接，不会把 Clash YAML 节点伪造反向转换为分享链接。


**！！不要把真实 token、密码或完整订阅地址提交到 Git 仓库。！！**

### 插件目录中的本地文件

推荐把文件手动放到插件目录下的 `sub` 文件夹：

```text
/AstrBot/data/plugins/astrbot_plugin_sub_aggregator/sub/XXXX
```

对应配置：

```json
{
  "name": "XXXX",
  "source_type": "local",
  "file_path": "sub/XXXX",
  "priority": 2,
  "enabled": true,
  "notify_changes": true
}
```

相对路径会相对于插件目录解析。也可以使用容器内的绝对路径：

```text
/AstrBot/data/plugins/astrbot_plugin_sub_aggregator/sub/XXXX
```

更新文件后执行：

```text
/subagg refresh
```

不需要再通过聊天框上传文件。

### 聊天上传文件

如果仍然希望通过 AstrBot 聊天上传，可以使用：

```text
/subagg localfile NAME
```

也支持本地路径或 HTTP(S) 地址：

```text
/subagg localfile NAME PATH_OR_URL
```

上传文件会被复制到持久化的 `local_sources` 目录，配置中保存文件路径而不是完整文件内容。

## 来源优先级与去重

来源使用数字 `priority` 表示优先级：

- `1` 比 `100` 优先
- 数字越小越早处理
- 相同优先级保持配置中的顺序
- 相同连接指纹重复出现时，先处理的来源获胜

示例：

```json
[
  {
    "name": "primary",
    "source_type": "local",
    "file_path": "sub/primary.yaml",
    "priority": 1,
    "enabled": true
  },
  {
    "name": "backup",
    "source_type": "remote",
    "url": "https://example.invalid/backup",
    "priority": 100,
    "enabled": true
  }
]
```

## AstrBot 命令

| 命令 | 作用 |
| --- | --- |
| `/subagg help` | 查看帮助 |
| `/subagg bind` | 绑定当前会话接收故障通知 |
| `/subagg url` | 查看带 token 的订阅地址 |
| `/subagg status` | 查看节点数、来源数、HTTP 和刷新状态 |
| `/subagg refresh` | 立即刷新所有启用的来源 |
| `/subagg list` | 查看已配置来源，不显示完整 URL |
| `/subagg add NAME URL` | 添加远程来源 |
| `/subagg localfile NAME` | 从聊天附件导入本地文件 |
| `/subagg localfile NAME PATH_OR_URL` | 从本地路径或 URL 导入文件 |
| `/subagg remove NAME` | 删除同名来源 |

## 输出与运行目录

生产环境建议将运行数据放在 AstrBot 的持久化数据目录，而不是插件代码目录：

```text
/AstrBot/data/runtime/astrbot_plugin_sub_aggregator/
```

主要文件包括：

```text
merged-subscription.yaml          # Mihomo / Clash 输出
merged-subscription.singbox.json  # sing-box 输出
merged-subscription.node-list.txt # 纯分享链接 Node List
merged-subscription.metadata.json  # 输出元数据
state.json                         # 节点状态和指纹
subagg.log                         # 脱敏运行日志
```

插件 HTTP 服务默认监听：

```text
127.0.0.1:8077
```

路由形式：

```text
/sub/<access_token>/clash
/sub/<access_token>/singbox
/sub/<access_token>/node-list
/sub/healthz
```

`/sub/healthz` 用于 Tunnel 或反向代理健康检查，不包含访问 token。

## Mihomo 与 sing-box 行为

### Mihomo

默认 `metacubex` profile 包含：

- 单一 `PROXY` select group
- 广告规则集 → `REJECT`
- 中国大陆规则集 → `DIRECT`
- 其他流量 → `PROXY`
- IPv6 默认关闭
- MetaCubeX MRS 规则提供器

`minimal` profile 适合诊断，只保留最小规则和手动代理组。

### sing-box

生成的 sing-box 配置面向 1.14 版本：

- 每个节点生成独立 outbound
- 使用一个 selector 进行手动切换
- 不生成 URLTest 或地区自动分组
- 国内和私有流量直连，其他流量走代理
- 使用新版 DNS、rule-set 和 route 结构
- 可生成纯 TUN 入站
- 关闭 TUN 时不生成 mixed 入站

## 失败处理

刷新过程中如果某个来源失败，插件会：

1. 记录来源级错误
2. 保留上一次成功的 Mihomo、sing-box 和 Node List 输出
3. 在刷新结果中显示失败来源
4. 不用不完整结果覆盖已发布配置

开启来源的 `filter_invalid_nodes` 后，单个非法节点会被跳过，不再作为阻断发布的来源错误；远程请求失败、内容无法识别和非法筛选正则仍会阻断本次发布。

运行日志只记录错误类型、来源名和统计信息，不应写入完整订阅内容、节点密码或 token。

## 开发与验证

安装开发依赖后运行测试：

```bash
python -m pip install -r requirements.txt
pytest -q
python -m compileall .
```

项目测试覆盖：

- 内容识别和 Base64 解码
- 各协议分享链接适配
- 节点规范化和指纹去重
- 来源优先级
- Mihomo profile 输出
- sing-box 1.14 配置结构
- 本地文件来源
- 远程请求和重试
- HTTP 订阅路由
- 插件生命周期相关方法

## 安全边界

请不要提交以下内容：

- 真实订阅 URL 和 token
- UUID、密码、私钥和 Cookie
- 完整运行日志
- 包含真实节点信息的测试样本
- 服务器 SSH 信息

建议使用：

- `example.invalid` 等占位域名
- 脱敏后的节点样本
- 独立的本地配置文件
- 环境变量或部署平台的 secret 管理

这个插件会读取并转换第三方订阅内容，但不会替你验证每个节点的可用性，也不保证上游订阅长期稳定。

## 项目定位

这个项目的核心不是简单下载一个订阅文件，而是把多个不稳定、格式不同的来源，转换成稳定、可验证、可回滚的本地配置发布流程：

```text
来源接入 → 内容识别 → 协议转换 → 节点合并 → 配置生成 → HTTP 发布 → 客户端验证
```

它适合作为：

- AstrBot 插件示例
- Python 异步网络服务练习
- 代理协议适配和配置生成项目
- 个人基础设施自动化项目
- 订阅解析、持久化和故障恢复的实践案例

## License

本项目采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 授权，完整文本见 [`LICENSE`](LICENSE)。使用或再发布本项目时请保留署名、许可证链接和变更说明，并以相同方式共享衍生版本。
