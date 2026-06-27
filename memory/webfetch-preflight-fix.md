---
name: webfetch-preflight-fix
description: WebFetch 域名预检失败解决方案——skipWebFetchPreflight 配置
metadata: 
  node_type: memory
  type: reference
  originSessionId: 05fa2522-c8d8-48b2-b9cc-c3e4bcda1058
---

# WebFetch 预检失败修复

## 问题

WebFetch 抓取目标网站前，会先请求 `https://claude.ai/api/web/domain_info?domain=` 做安全校验。如果 `claude.ai` 被墙或被企业防火墙拦截，预检查失败，即使目标网站本身可正常访问。

## 解决方案

在 Claude Code 的 `settings.json` 中配置：

```json
{
  "skipWebFetchPreflight": true
}
```

此选项跳过域名安全预检，直接抓取目标网站。

## 参考

- https://github.com/anthropics/claude-code/issues/6388

**Why:** 国内网络环境中 claude.ai 被墙，导致所有 WebFetch 调用失败。此配置在 aggregator-local 项目开发过程中发现并验证。

**How to apply:** 在 `~/.claude/settings.json` 中添加 `"skipWebFetchPreflight": true`。
