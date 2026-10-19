"""web-deepseek — DeepSeek 网页搜索/抓取 provider（用户级插件）。

注册 ``deepseek`` 到 web_search_registry。启用：``hermes plugins enable web-deepseek``，
再在 config.yaml 指定 ``web.search_backend`` / ``web.extract_backend: deepseek``。
"""

from __future__ import annotations

from .provider import DeepSeekWebProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(DeepSeekWebProvider())
