"""DeepSeek 网页搜索 + 抓取插件（用户级，需在 plugins.enabled 中启用）。

Config: ``web.search_backend`` / ``web.extract_backend: "deepseek"``（或 ``web.backend``）。
Env: ``DEEPSEEK_SEARCH_API_KEY``（建议专用于 Search/Fetch 的 key）、可选 ``DEEPSEEK_SEARCH_BASE_URL``
（默认复用 ``DEEPSEEK_BASE_URL``，再退到 ``https://api.deepseek.com``）。

接口文档: https://api-docs.deepseek.com/zh-cn/guides/search
计费：Search / Fetch 各按成功请求计费，5 元 / 1000 次；失败、无结果、超时不计费。
限制：query ≤ 128 字符，count 1~50；Search QPS 100、Fetch QPS 25（账号级）。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from plugins.web._common import (
    BaseWebSearchProvider,
    document,
    page_error,
    provider_env,
    run_extract,
    run_search,
    search_fail,
    search_ok,
    setup_schema,
    title_hit,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.deepseek.com"
_SEARCH_TIMEOUT = 30
_FETCH_TIMEOUT = 60
_MAX_FETCH_WORKERS = 4

# DeepSeek 的错误码含义（见指南“错误”一节），用于把裸状态码翻译成可行动的原因。
_STATUS_HINT = {
    400: "请求体不合法（如 query 超过 128 字符或 count 越界）",
    401: "API key 缺失或无效",
    402: "账号余额不足",
    403: "抓取被安全策略拒绝",
    404: "未能取到可用网页内容（不可用 / 被站点拦截 / 无可提取正文）",
    408: "读取请求体超时（可重试）",
    413: "请求体超过大小限制",
    429: "超过账号级 QPS 限制（Search 100、Fetch 25；Fetch 还有目标域名限制）",
    500: "DeepSeek 服务器内部错误（可重试）",
    504: "下游请求超时（可重试）",
}


def _base_url() -> str:
    base = provider_env("DEEPSEEK_SEARCH_BASE_URL") or provider_env("DEEPSEEK_BASE_URL") or _DEFAULT_BASE
    return base.rstrip("/")


def _api_key() -> str:
    return provider_env("DEEPSEEK_SEARCH_API_KEY")


def _post(path: str, payload: dict[str, Any], key: str, timeout: int) -> tuple[Any, str]:
    """POST ``path`` and parse JSON → ``(data, "")`` on success, ``(None, error_message)`` otherwise."""
    url = f"{_base_url()}{path}"
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        logger.warning("DeepSeek %s request error: %s", path, exc)
        return None, f"Could not reach DeepSeek at {url}: {exc}"

    if resp.status_code != 200:
        detail = ""
        try:
            detail = ((resp.json() or {}).get("error") or {}).get("message") or ""
        except Exception:  # non-JSON error body — the status alone is the signal
            detail = ""
        hint = _STATUS_HINT.get(resp.status_code, "")
        message = f"DeepSeek HTTP {resp.status_code}{' — ' + hint if hint else ''}{': ' + detail if detail else ''}"
        logger.warning("%s", message)
        return None, message

    try:
        return resp.json(), ""
    except Exception as exc:
        logger.warning("DeepSeek %s response parse error: %s", path, exc)
        return None, f"Could not parse DeepSeek response as JSON: {exc}"


class DeepSeekWebProvider(BaseWebSearchProvider):
    """DeepSeek Search + Fetch provider (keyed only — no keyless tier)."""

    NAME = "deepseek"
    DISPLAY_NAME = "DeepSeek Search/Fetch"
    KEY_ENV = "DEEPSEEK_SEARCH_API_KEY"
    EXTRACT = True
    KEYLESS = False

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        def _body() -> dict[str, Any]:
            key = _api_key()
            if not key:
                return search_fail("DEEPSEEK_SEARCH_API_KEY is not set (set it in ~/.hermes/.env)")
            count = max(1, min(int(limit or 5), 50))
            logger.info("DeepSeek search: '%s' (count=%d)", query, count)
            data, error = _post("/v1/tools/search", {"query": query, "count": count}, key, _SEARCH_TIMEOUT)
            if error:
                return search_fail(error)
            rows: list[dict[str, Any]] = []
            for index, item in enumerate(data.get("results") or []):
                # summary（600~800 字符，官方定位“给模型阅读”）优先，退回 snippet。
                description = (item.get("summary") or item.get("snippet") or "").strip()
                rows.append(title_hit(item.get("title", ""), item.get("url", ""), description, index + 1))
            return search_ok(rows)

        return run_search("DeepSeek", logger, _body)

    def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        def _one(url: str) -> dict[str, Any]:
            key = _api_key()
            if not key:
                return page_error(url, "DEEPSEEK_SEARCH_API_KEY is not set (set it in ~/.hermes/.env)")
            data, error = _post("/v1/tools/fetch", {"url": url}, key, _FETCH_TIMEOUT)
            if error:
                return page_error(url, error)
            content = data.get("content") or ""
            if not content.strip():
                return page_error(url, "DeepSeek fetch returned an empty body")
            return document(url, data.get("title") or "", content)

        def _body() -> list[dict[str, Any]]:
            fetch_urls = list(urls)
            logger.info("DeepSeek fetch: %d URL(s)", len(fetch_urls))
            workers = min(_MAX_FETCH_WORKERS, max(1, len(fetch_urls)))
            if workers == 1:
                return [_one(u) for u in fetch_urls]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(_one, fetch_urls))

        return run_extract("DeepSeek", logger, urls, _body)

    def get_setup_schema(self) -> dict[str, Any]:
        return setup_schema(
            "DeepSeek Search/Fetch",
            "paid",
            "Search + Fetch，按成功请求计费：各 ¥5 / 1000 次；无 keyless 档。",
            "DEEPSEEK_SEARCH_API_KEY",
            "DeepSeek API key（建议新建一个专用于 Search/Fetch，便于核对用量）",
            "https://platform.deepseek.com/api_keys",
        )
