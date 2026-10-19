# hermes-web-deepseek

[Hermes Agent](https://github.com/NousResearch/hermes-agent) 的 **DeepSeek 网页搜索 / 抓取**后端插件：把 `web_search` 与 `web_extract` 接到 DeepSeek 的 Server 端工具接口。

| 能力 | 接口 |
|---|---|
| 搜索 | `POST https://api.deepseek.com/v1/tools/search` |
| 抓取 | `POST https://api.deepseek.com/v1/tools/fetch` |

官方文档：<https://api-docs.deepseek.com/zh-cn/guides/search>

## 计费与限制

- 按**成功请求**计费：Search / Fetch 各 ¥5 / 1000 次（失败、无结果、超时不计费）。
- QPS 为账号级：Search 100、Fetch 25（Fetch 另有目标域名限制）。
- 搜索接口支持 `site:` / `-site:` / `"精确短语"` / `lang:zh,en` / `after:2025` / `before:2026` 等语法；`count` 上限 50。

## 安装

```bash
git clone https://github.com/Afaraster/hermes-web-deepseek.git \
  ~/.hermes/plugins/web-deepseek
hermes plugins enable web-deepseek
```

## 配置

```bash
# 1) 凭据（建议用一把专用于 Search/Fetch 的 key，便于核对用量）
printf '\nDEEPSEEK_SEARCH_API_KEY=sk-...\n' >> ~/.hermes/.env

# 2) 指定后端（config.yaml 受保护，必须走 hermes config set）
hermes config set web.search_backend deepseek
hermes config set web.extract_backend deepseek
```

可选环境变量：`DEEPSEEK_SEARCH_BASE_URL`（默认复用 `DEEPSEEK_BASE_URL`，再退回 `https://api.deepseek.com`）。

重启不需要：gateway 会热重载插件，`.env` 每次调用都会重读。

## 验证

```bash
cd ~/.hermes/hermes-agent && source activate && python -c "\
import tools.web_tools as w; w._ensure_web_plugins_loaded();\
print(w._get_search_backend(), w._registered_web_provider('deepseek'))"
```

返回 `deepseek <DeepSeekWebProvider object …>` 即接入成功。真实调用后可在
`~/.hermes/logs/agent.log` 看到 `Web search via deepseek` / `Web extract via deepseek`。

## 实现要点

- `provider.py` 继承 Hermes 内部基类 `plugins.web._common.BaseWebSearchProvider`，实现 `search(query, limit)` 与 `extract(urls)`；`search` 用结果里的 `summary`（600–800 字符，官方定位“给模型阅读”）作描述，缺失时退回 `snippet`；`extract` 逐 URL 请求，4 并发、每次 60s 超时。
- 错误码做了中文释义（400 参数、401 key、402 余额、403 安全策略、404 无可提取正文、429 QPS、5xx 可重试）。
- **升级风险**：依赖 Hermes 内部模块 `plugins.web._common`（`BaseWebSearchProvider` / `title_hit` / `document` / `run_search` / `provider_env`）。上游重构该模块时插件会 import 失败，症状是 web 工具报 “no provider registered”，按上面的验证命令自查即可。

## License

MIT
