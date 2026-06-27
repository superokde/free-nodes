---
name: clash-subscription-format-spec
description: OpenClash/Hiddify 兼容的 Clash 订阅 YAML 格式规范——与付费订阅完全对齐
metadata: 
  node_type: memory
  type: reference
  originSessionId: 05fa2522-c8d8-48b2-b9cc-c3e4bcda1058
---

# Clash 订阅 YAML 格式规范（OpenClash + Hiddify 双兼容）

## 核心规则

### 1. 对内联格式，不要展开

付费订阅和两个主流客户端都接受内联 YAML。展开格式可能导致解析失败。

```yaml
# ✅ 正确：内联格式
proxies:
    - { name: '🇺🇸 美国 01', server: '1.2.3.4', port: 443, type: ss, cipher: 'aes-128-gcm', password: xxx, udp: true }

# ❌ 错误：展开格式（Hiddify 可能不识别）
proxies:
  - name: 🇺🇸 美国 01
    server: 1.2.3.4
    port: 443
    type: ss
```

### 2. 嵌套字段绝对不能是 Python repr 字符串

subconverter 内联输出会把 `ws-opts` 等嵌套结构写成 Python repr 字符串，**OpenClash 和 Hiddify 都不认**。

```yaml
# ❌ 错误：Python repr 字符串
ws-opts: '{''path'': ''/'', ''headers'': {''Host'': ''xxx''}}'

# ✅ 正确：YAML 内联字典
ws-opts: { path: '/', headers: { Host: 'xxx' } }
```

修复方法：`ast.literal_eval(v.replace("''", "'"))` 把 Python repr 还原为真实 dict。

已知需要修复的字段名：`ws-opts`, `reality-opts`, `hysteria-opts`, `tuic-opts`, `grpc-opts`

### 3. 4 空格缩进

付费订阅和两个客户端都使用 4 空格缩进。

### 4. 完整配置结构

```yaml
mixed-port: 7890
allow-lan: false
bind-address: '*'
mode: rule
log-level: info
external-controller: '127.0.0.1:9090'
unified-delay: true
tcp-concurrent: true
dns:
    enable: true
    ipv6: false
    default-nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]
    enhanced-mode: fake-ip
    fake-ip-range: 198.18.0.1/16
    use-hosts: true
    respect-rules: true
    proxy-server-nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]
    nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]
    fallback: [1.1.1.1, 8.8.8.8]
    fallback-filter: { geoip: true, geoip-code: CN, geosite: [gfw], ipcidr: [240.0.0.0/4], domain: [+.google.com, +.facebook.com, +.youtube.com] }
proxies:
    - { name: '节点名', server: '1.2.3.4', port: 443, type: ss, ... }
proxy-groups:
    - { name: Proxy, type: select, proxies: [自动选择, 故障转移, '节点1', '节点2'] }
    - { name: 自动选择, type: url-test, proxies: ['节点1', '节点2'], url: 'http://www.gstatic.com/generate_204', interval: 300 }
    - { name: 故障转移, type: fallback, proxies: ['节点1', '节点2'], url: 'http://www.gstatic.com/generate_204', interval: 600 }
rules:
    - 'DOMAIN-KEYWORD,google,Proxy'
    - 'DOMAIN-SUFFIX,google.com,Proxy'
    - 'GEOIP,CN,DIRECT'
    - 'MATCH,Proxy'
```

### 5. Hiddify 纯代理列表格式

Hiddify 不需要完整配置，只需 `proxies:` 列表。（但用完整配置也能识别）

```yaml
proxies:
    - { name: '节点名', server: '1.2.3.4', port: 443, type: ss, ... }
```

### 6. HTTP 服务端要求

nginx 必须返回 `Content-Type: text/plain`，不能是 `application/octet-stream`（OpenClash 会拒绝）。

```nginx
types {
    text/plain yaml yml txt json;
    text/html  html htm;
}
location /sub/ {
    default_type text/plain;
}
```

## Hiddify 格式检测机制（源码确认）

```
解析顺序：JSON(sing-box) → V2Ray → Clash YAML → "unable to determine config format"
Clash 判断条件：yaml.Unmarshal 成功 && clashObj.Proxies != nil
代理解析：委托给 github.com/xmdhs/clash2singbox/convert 库
```

stale config（含 mixed-port）会导致 `yaml.Unmarshal` 成功但 proxies 已过期。检测 `mixed-port` 字段可区分新数据 vs 过期完整配置。

## OpenClash 已知问题

- IPv6 方括号 `server: "[2400:cbff:...]"` → 不识别；`server: "2400:cbff:..."` → 识别
- `Content-Type: application/octet-stream` → 拒绝解析为 YAML

## 参考来源

- liangxin.xyz 付费订阅格式（实测 OpenClash + Hiddify 双兼容）
- hiddify/hiddify-core v2/config/parser.go
- vernesong/OpenClash issue #4180

**Why:** aggregator-local 项目开发中发现 subconverter 产出的 YAML 与主流客户端不兼容，花费大量时间排查格式问题。此规范可直接复用到任何需要生成 Clash 订阅的 Go/Python/JS 项目。

**How to apply:** 生成 Clash 订阅 YAML 时，遵循上述内联格式、嵌套字段处理、4 空格缩进规则。nginx 用 `text/plain` Content-Type。
