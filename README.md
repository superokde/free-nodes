# Free Nodes Aggregator

免费代理节点自动聚合工具，每天自动从多个订阅源抓取免费节点，去重过滤后生成多格式固定订阅链接。

## ✨ 特性

- 🌐 **多源聚合**: 15+ 个精选订阅源，覆盖 GitHub/CDN/独立站
- 🎯 **信用分级**: L1(国内直连) / L2(CDN代理) / L3(境外直连) 三级信用
- 🚫 **智能过滤**: IP黑名单 + 端口过滤 + 节点有效性检查
- 📦 **三格式输出**: V2Ray 订阅 + Clash 配置 + Proxy-Provider
- ⏰ **每日更新**: GitHub Actions 每天 00:00(北京时间) 自动运行
- 🔗 **固定链接**: 订阅 URL 永久不变，内容自动更新

## 📥 订阅链接

| 格式 | 客户端 | 链接 |
|------|--------|------|
| `all.txt` | v2rayN / v2rayNG / Shadowrocket / Quantumult X | `https://raw.githubusercontent.com/<USER>/<REPO>/main/nodes/all.txt` |
| `all.yaml` | Clash Meta / Clash Verge / OpenClash | `https://raw.githubusercontent.com/<USER>/<REPO>/main/nodes/all.yaml` |
| `provider.yaml` | Clash proxy-provider | `https://raw.githubusercontent.com/<USER>/<REPO>/main/nodes/provider.yaml` |

### 国内加速镜像

```
https://ghp.ci/https://raw.githubusercontent.com/<USER>/<REPO>/main/nodes/all.txt
https://cdn.jsdmirror.com/gh/<USER>/<REPO>@main/nodes/all.yaml
```

## 🚀 快速开始

### 本地运行

```bash
git clone https://github.com/<USER>/<REPO>.git
cd <REPO>
pip install -r requirements.txt
python main.py
```

### GitHub Actions 自动运行

Fork 本仓库 → GitHub Actions 自动启用 → 每天 00:00 自动更新。

也可以手动触发: **Actions** → **Update Free Nodes** → **Run workflow**.

## 📁 项目结构

```
├── .github/workflows/update.yml  # GH Actions 工作流
├── config/
│   ├── sources.yaml              # 订阅源配置
│   └── blacklist.yaml            # IP/域名黑名单
├── src/
│   ├── config.py                 # 配置加载
│   ├── collector.py              # 多格式源抓取+解析
│   ├── deduplicator.py           # server:port:type 去重
│   ├── filters.py                # 黑名单+端口过滤
│   ├── formatter.py              # 三格式输出生成
│   └── merger.py                 # 管道编排
├── nodes/                        # 输出目录（自动更新）
│   ├── all.txt
│   ├── all.yaml
│   └── provider.yaml
├── main.py                       # 入口
└── README.md
```

## 🔧 配置

### 添加新订阅源

编辑 `config/sources.yaml`:

```yaml
sources:
  - name: my-new-source
    url: https://example.com/free-nodes.yaml
    format: clash       # clash | v2ray | base64 | singbox
    credit: 2           # 1=L1 2=L2 3=L3
    enabled: true
```

### 黑名单

编辑 `config/blacklist.yaml` 添加被墙 IP 段或端口。

## 📊 源列表

| 源 | 格式 | 信用 |
|---|------|------|
| xrayvip.com (YAML) | clash | L1 |
| xrayvip.com (TXT) | v2ray | L1 |
| lhw828/clashnode | clash | L2 |
| mahdibland/V2RayAggregator (Public) | clash | L2 |
| mahdibland/V2RayAggregator (Airport) | clash | L2 |
| free18/v2ray (Clash) | clash | L2 |
| free18/v2ray (V2Ray) | v2ray | L2 |
| vxiaov/free_proxies | clash | L2 |
| Net-9QdV/FreeNodes (YAML) | clash | L2 |
| Net-9QdV/FreeNodes (TXT) | v2ray | L2 |
| awesome-vpn (Clash) | clash | L2 |
| awesome-vpn (All) | base64 | L2 |
| ermaozi/get_subscribe | base64 | L2 |
| +境外直连源 (L3) | clash/v2ray | L3 |

## ⚠️ 免责声明

本项目仅供学习研究使用。所有节点资源来自互联网公开信息，节点质量、可用性、安全性均无法保证。请遵守当地法律法规。

## 📄 License

MIT License
