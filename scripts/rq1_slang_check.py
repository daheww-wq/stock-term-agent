"""RQ1 슬랭 사전 점검: 사전 없이 모델에게 슬랭 뜻을 묻고, 본인 판정용 시트를 만든다.

실행 (stock-term-agent 폴더에서)
  python scripts/rq1_slang_check.py                                   # .env의 AGENT_MODEL로 실행
  python scripts/rq1_slang_check.py --model openai/gpt-6-luna         # 다른 모델로 비교 실행
  python scripts/rq1_slang_check.py --model anthropic/claude-opus-5.5
  python scripts/rq1_slang_check.py --model anthropic/claude-opus-5.5 --ids-file data/rq1/rq1_subset_compare.txt  # 일부 문항만
  python scripts/rq1_slang_check.py --dry-run                         # 모델 호출 없이 문항만 확인
결과: results/rq1_answers_<모델>_<시각>.csv  → 엑셀로 열어 '판정' 칸을 채운다
"""
import argparse
import csv
import datetime as dt
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
ITEMS = [ROOT / "data/rq1/rq1_items.csv", ROOT / "data/rq1/rq1_candidates.csv"]
OUT_DIR = ROOT / "results"

PROMPT = (
    "한국 주식 커뮤니티에서 쓰는 표현 '{expr}'의 뜻이 뭐야? "
    "한두 문장으로 답해줘. 확실히 모르면 지어내지 말고 '모름'이라고만 답해."
)


def load_items():
    rows = []
    for path in ITEMS:
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows += [r for r in csv.DictReader(f) if r.get("표현")]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="비교용 모델 ID. 생략하면 .env의 AGENT_MODEL")
    ap.add_argument("--ids-file", help="이 파일에 적힌 id 문항만 실행 (한 줄에 하나)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = load_items()
    if args.ids_file:
        keep = [l.strip() for l in open(ROOT / args.ids_file, encoding="utf-8") if l.strip()]
        items = [r for r in items if r["id"] in keep]
    print(f"문항 {len(items)}개")
    if args.dry_run:
        for r in items[:5]:
            print(r["id"], r["표현"], "→", PROMPT.format(expr=r["표현"]))
        return

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    model = args.model or os.getenv("AGENT_MODEL")
    if not key or not model:
        sys.exit(".env에 OPENROUTER_API_KEY와 AGENT_MODEL을 채워주세요.")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
    OUT_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    tag = "_subset" if args.ids_file else ""
    out = OUT_DIR / f"rq1_answers_{model.replace('/', '_')}{tag}_{stamp}.csv"

    total_in = total_out = 0
    total_sec = 0.0
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "유형", "표현", "사전_정답", "모델_답변", "판정(정확/부분/틀림/모름)",
                    "그럴듯한_오답(O)", "메모", "응답_초", "입력_토큰", "출력_토큰"])
        for i, r in enumerate(items, 1):
            t0 = time.time()
            tin = tout = ""
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    messages=[{"role": "user", "content": PROMPT.format(expr=r["표현"])}],
                )
                ans = (resp.choices[0].message.content or "").strip()
                if resp.usage:
                    tin, tout = resp.usage.prompt_tokens, resp.usage.completion_tokens
                    total_in += tin or 0
                    total_out += tout or 0
            except Exception as e:  # 한 문항 실패가 전체를 멈추지 않게
                ans = f"[오류] {e}"
            sec = round(time.time() - t0, 2)
            total_sec += sec
            w.writerow([r["id"], r["유형"], r["표현"], r["사전_정답"], ans, "", "", "", sec, tin, tout])
            print(f"{i}/{len(items)} {r['표현']} → {ans[:40]}")

    print(f"\n완료: {out}")
    print(f"모델 {model} · 평균 응답 {total_sec/len(items):.2f}초 · 입력 토큰 {total_in} · 출력 토큰 {total_out}")


if __name__ == "__main__":
    main()
