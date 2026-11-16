"""OpenRouter에서 쓸 수 있는 모델과 가격 보기 (P-050). 모델 비교에 쓸 후보를 고를 때.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python scripts/list_models.py                  # 기본 회사들
  python scripts/list_models.py --search flash   # 이름에 flash가 든 것만

- 기본 목록은 정해 둔 제공사(PROVIDERS)만 보여 준다 (--all이면 전부)
- 가격은 100만 토큰당 달러 (입력 / 출력). 키는 .env에서 읽고 출력하지 않는다
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROVIDERS = ("openai", "anthropic", "google", "mistralai", "meta-llama", "x-ai", "amazon", "microsoft", "cohere")


def fetch(base_url: str, key: str | None) -> list:
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res).get("data", [])


def rows(models: list, search: str = "", all_providers: bool = False) -> list:
    out = []
    for m in models:
        mid = m.get("id", "")
        if not all_providers and not mid.startswith(tuple(p + "/" for p in PROVIDERS)):
            continue
        if search and search.lower() not in mid.lower():
            continue
        price = m.get("pricing") or {}
        try:
            pin, pout = float(price.get("prompt", 0)) * 1e6, float(price.get("completion", 0)) * 1e6
        except (TypeError, ValueError):
            pin = pout = None
        out.append((mid, pin, pout, m.get("context_length")))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", default="")
    ap.add_argument("--all", action="store_true", help="회사 제한 없이 전부")
    args = ap.parse_args()
    from src import config  # noqa: F401  (.env 읽기)
    models = fetch(config.OPENROUTER_BASE_URL, os.getenv("OPENROUTER_API_KEY"))
    found = rows(models, args.search, args.all)
    print(f"{'모델 ID':55s} {'입력$/1M':>9s} {'출력$/1M':>9s} {'문맥':>9s}")
    for mid, pin, pout, ctx in found:
        fmt = lambda v: f"{v:9.2f}" if v is not None else f"{'?':>9s}"
        print(f"{mid:55s} {fmt(pin)} {fmt(pout)} {str(ctx or ''):>9s}")
    print(f"\n{len(found)}개. 지금 에이전트 {config.AGENT_MODEL} · 채점 {config.JUDGE_MODEL}")


if __name__ == "__main__":
    main()
