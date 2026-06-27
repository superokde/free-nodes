---
name: aggregator-local-project
description: 基于 wzdnzd/aggregator 的免费节点订阅本地化 Docker 部署项目完整记录（2026-06-19 终版）
metadata: 
  node_type: memory
  type: project
  originSessionId: 05fa2522-c8d8-48b2-b9cc-c3e4bcda1058
---

# Aggregator Local — 免费节点订阅本地化部署

## 项目概述

基于 [wzdnzd/aggregator](https://github.com/wzdnzd/aggregator)（6.7k stars）构建的本地化 Docker 镜像。

核心功能：9 个精选源聚合 → Clash 国内网络测速筛选 → 生成永久本地订阅链接。

## 项目路径

- **源码+构建**: `/home/superokde/vpnproxy/aggregator-local/`
- **可移植部署**: `/home/superokde/vpnproxy/docker-compose.yml`（端口 9000）
- **订阅数据**: `/home/superokde/vpnproxy/subscribe-data/subscribe/`
- **原始 clone**: `/home/superokde/vpnproxy/aggregator/`（上游参考）

## 架构

```
Docker 容器内（无需科学上网）：
  cron（每2小时）→ process.py（CDN/独立站拉10源→去重→Clash测速→输出）
                                          ↓
  postprocess.sh → v2ray_fallback.py（all.txt 始终从 all.yaml 重新生成）
                                          ↓
  nginx :8080 ← /sub/all.yaml, /sub/all.txt, /sub/all-singbox.json
```

**关键：10 个源全部通过 cdn.jsdmirror.com（国内CDN）或 xrayvip.com（独立站）访问，不需要 GitHub 代理。**

## 订阅源（10个，全部无需科学上网）

| # | 来源 | 访问方式 | 格式 | 特点 |
|---|------|---------|------|------|
| 1 | xrayvip.com free.yaml | 🏠 独立站直连 | Clash | 国内站点 |
| 2 | xrayvip.com free.txt | 🏠 独立站直连 | V2Ray | 国内站点 |
| 3 | lhw828/clashnode | 📡 cdn.jsdmirror.com | Clash | 15+源+LiteSpeedTest |
| 4 | Net-9QdV/FreeNodes all.yaml | 📡 cdn.jsdmirror.com | Clash | SubsCheck 30分钟更新 |
| 5 | Net-9QdV/FreeNodes base64.txt | 📡 cdn.jsdmirror.com | V2Ray | 同上 |
| 6 | vxiaov/free_proxies | 📡 cdn.jsdmirror.com | Clash | TG频道精选 |
| 7 | free18/v2ray c.yaml | 📡 cdn.jsdmirror.com | Clash | 长期维护 |
| 8 | free18/v2ray v.txt | 📡 cdn.jsdmirror.com | V2Ray | 长期维护 |
| 9 | mahdibland Eternity.yml | 📡 cdn.jsdmirror.com | Clash | Top200精选 |
| 10 | ermaozi get_subscribe | 📡 cdn.jsdmirror.com | V2Ray | 9k stars |

> URL 格式：`https://cdn.jsdmirror.com/gh/USER/REPO@BRANCH/PATH`（替代 raw.githubusercontent.com）

## 关键设计决策

### 为什么用精选输出而非原始 dump
- mahdibland 的 `Eternity.yml`（Top200 LiteSpeedTest精选）而非 `sub_merge.txt`（1600+全量）
- lhw828/clashnode 的 `Eternity.yml`（已合并+测速）而非各个源分别拉

### 为什么 all.txt 从 all.yaml 生成
- 子转换器 v2ray 格式不稳定，可能失败
- all.yaml 确认可用后，`v2ray_fallback.py` 直接转换：解析 YAML proxies → 生成 vmess:///ss:///trojan:///vless:// 等URI → Base64编码
- postprocess.sh **每次强制重新生成**，不检查文件是否已存在

### 为什么 SKIP_ALIVE_CHECK=false
- 国内网络下 Clash 测速有实际意义：测试谷歌/YouTube 能否通过代理访问
- 有VPN时设 true（避免假阳性），无VPN时设 false（正确过滤GFW封锁节点）

### 为什么关闭 Google/Telegram/Twitter/GitHub 爬虫
- 国内不可用，关闭减少无意义请求
- 依赖固定优质源更稳定

## Dockerfile 关键配置

```
基础镜像: docker.m.daocloud.io/library/python:3.12-slim  ← 国内镜像
apt源: mirrors.tuna.tsinghua.edu.cn
pip源: pypi.tuna.tsinghua.edu.cn
GH_PROXY: https://hk.gh-proxy.org,https://ghp.ci,https://ghproxy.net  ← 3个冗余
SKIP_ALIVE_CHECK: false  ← 国内网络开启Clash测速
TZ: Asia/Shanghai
```

## 关键文件

| 文件 | 作用 |
|------|------|
| `config.json` | 9个订阅源 + 本地存储 + 节点过滤规则 |
| `Dockerfile` | 国内镜像源构建 |
| `docker-compose.yml` | 构建用（aggregator-local/） |
| `entrypoint.sh` | 首次爬取 + nginx 启动 + cron |
| `crontab` | 每2小时爬取 |
| `postprocess.sh` | 每次强制从 all.yaml 重新生成 all.txt |
| `v2ray_fallback.py` | YAML → V2Ray Base64 格式转换 |
| `build.sh` | 一键构建 + 导出 tar |
| `nginx.conf` | 静态文件服务 + 健康检查 |
| `utils.py` | GH_PROXY 多代理自动切换 |

## 已解决的 Bug

1. **404** — pages爬虫只提取HTTP链接不解析ss://原始节点 → 改用domains直连
2. **threshold=3 太严** — 降到1
3. **国内GitHub不通** — 改用 cdn.jsdmirror.com 国内CDN + xrayvip独立站，GH_PROXY置空
4. **all.txt与all.yaml不同步** — postprocess.sh每次强制重新生成
5. **VPN环境Clash测速假阳性** — SKIP_ALIVE_CHECK可配置
6. **Docker Hub不通** — 基础镜像+apt+pip全换国内源
7. **节点国内不可用** — 换用精选源（Eternity.yml等），关掉无效爬虫
8. **科学上网环境才能拉取源** — 10个源全切 CDN/独立站，无需代理

## 部署

```bash
# 构建（有网的机器，只需一次）
cd /home/superokde/vpnproxy/aggregator-local
bash build.sh          # 构建 + 导出 aggregator-local.tar

# 部署（任意机器，无需网络）
sudo docker load -i aggregator-local.tar
cd /home/superokde/vpnproxy
sudo docker compose up -d
```

## 订阅链接

| 格式 | 地址 |
|------|------|
| Clash | `http://<IP>:9000/sub/all.yaml` |
| V2Ray | `http://<IP>:9000/sub/all.txt` |
| SingBox | `http://<IP>:9000/sub/all-singbox.json` |

**Why:** 用户需要免费节点订阅服务。原 Barabama/FreeNodes 依赖固定爬虫网站已大面积停更。选用 wzdnzd/aggregator 作为基础，进行本地化改造：替换订阅源为国内可用精选源、解决国内网络访问 GitHub/Docker Hub 问题、修复 v2ray 格式输出、优化 Clash 测速策略。

**How to apply:** 在 aggregator-local/ 修改 config.json 的 domains 数组添加/替换订阅源。修改 GH_PROXY 环境变量换代理。修改 SKIP_ALIVE_CHECK 根据网络环境切换测速模式。build.sh 构建导出，docker-compose.yml 部署。
