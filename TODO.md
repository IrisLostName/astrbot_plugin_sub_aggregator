# TODO

以下协议当前不做伪转换，只记录等待目标 Mihomo Alpha/后续版本明确支持并验证：

- ShadowsocksR
- ShadowQUIC
- Naive
- Mieru
- TrustTunnel
- Snell v5
- SSH
- Sudoku（需先确认协议规范）
- OpenVPN
- Tor
- OpenConnect
- WireGuard 系统级扩展能力
- Tailscale 内网穿透
- AnyTLS-Reality（当前 Mihomo 文档明确不支持 Reality 组合）

恢复条件：目标 Mihomo 文档明确支持、存在稳定配置语法、adapter fixture 通过、`mihomo -t` 通过，并完成至少一次受控真实连接验证。在此之前，不得把这些协议静默丢弃或伪装成其他协议。
