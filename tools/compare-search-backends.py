#!/usr/bin/env python3
"""同一组查询下并排比较 Hermes 的两个 web search 后端（DeepSeek vs Tavily）。

用法:
    cd ~/.hermes/hermes-agent && source activate
    python ~/path/to/compare-search-backends.py                    # 默认 3 个查询
    python ~/path/to/compare-search-backends.py "查询1" "查询2"     # 自定义查询

输出: 每个查询一张对照表（域名 / 标题 / 描述长度），并存 JSON 到
      ~/.hermes/cache/scratch/search-quality-compare.json

注意: DeepSeek 侧按成功请求计费（¥5/1000 次），每跑一个查询相当于 1 次计费请求；
      Tavily 免费额度 1000 credits/月（1 次搜索 = 1 credit）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from urllib.parse import urlparse

REPO = os.path.expanduser("~/.hermes/hermes-agent")
PLUGIN = os.path.expanduser("~/.hermes/plugins/web-deepseek/provider.py")
OUT = os.path.expanduser("~/.hermes/cache/scratch/search-quality-compare.json")

DEFAULT_QUERIES = [
    "DeepSeek V4 发布时间",
    "Hermes Agent Nous Research documentation",
    "Debian 13 trixie 发布日期",
]


def load_deepseek_provider():
    sys.path.insert(0, REPO)
    spec = importlib.util.spec_from_file_location("ds_provider", PLUGIN)
    assert spec is not None and spec.loader is not None, f"无法加载 provider: {PLUGIN}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DeepSeekWebProvider


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    queries = args.queries or DEFAULT_QUERIES

    DeepSeek = load_deepseek_provider()
    from plugins.web.tavily.provider import TavilyWebSearchProvider  # noqa: E402

    report = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "limit": args.limit, "queries": []}
    for q in queries:
        entry = {"query": q}
        for name, fn in (("deepseek", DeepSeek().search), ("tavily", TavilyWebSearchProvider().search)):
            try:
                raw = fn(q, args.limit)
            except Exception as exc:
                entry[name] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            if not raw.get("success"):
                entry[name] = {"error": str(raw.get("error"))}
                continue
            rows = [{
                "pos": i + 1,
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "domain": domain(r.get("url", "")),
                "desc_len": len(r.get("description") or ""),
                "desc_head": (r.get("description") or "")[:160].replace("\n", " "),
            } for i, r in enumerate(raw["data"]["web"][:args.limit])]
            entry[name] = {"n": len(rows), "rows": rows}
        report["queries"].append(entry)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("saved:", OUT)

    for e in report["queries"]:
        print("\n" + "=" * 78)
        print("QUERY:", e["query"])
        for name in ("deepseek", "tavily"):
            block = e.get(name, {})
            if "error" in block:
                print(f"  [{name}] ERROR: {block['error']}")
                continue
            print(f"  [{name}] n={block['n']}")
            for r in block["rows"]:
                print(f"    {r['pos']}. {r['domain']:<30} | {r['title'][:52]:<52} | desc {r['desc_len']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
