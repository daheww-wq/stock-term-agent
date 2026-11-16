"""검수 노드(노드 6) 검증셋 실행 (컴플라이언스 체크리스트 4번, P-026).

미리 써 둔 답변 20개(위반 12 + 통과 8)를 그래프를 거치지 않고 검수 노드에만 넣어,
정답 판정과 비교한다. 검수가 위반을 놓치면 위반율 수치를 믿을 수 없기 때문이다.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤) — 측정 시점에만
  python eval/run_compliance.py                   # 20개 전부
  python eval/run_compliance.py --ids V01,P02     # 몇 개만
  python eval/run_compliance.py --model openai/gpt-6-luna
  python eval/run_compliance.py --with-question   # 질문(질문_참고 칸)도 넘김: 용어 설명 답에도 R1을 질문 기준으로 적용 (P-068)

결과: results/compliance_<모델>_<시각>.xlsx (탭: 요약 · 결과)
- 놓침: 정답이 위반인데 통과로 판정
- 과잉 차단: 정답이 통과인데 위반으로 판정
- 항목 일치: 위반을 맞힌 것 중 정답 항목(C1~C5, R1)을 위반 목록에 넣었는지

검증셋 파일(data/tests/test_compliance.csv)은 이 스크립트만 읽는다.
"""
import argparse
import csv
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TESTS = ROOT / "data" / "tests"
OUT_DIR = ROOT / "results"
FILE = "test_compliance.csv"


def read_rows():
    with open(TESTS / FILE, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def score(expected_verdict: str, expected_item: str, result: dict) -> dict:
    """한 문항 채점. result는 노드 6 judge()의 판정 결과."""
    got = result.get("verdict", "")
    items = [str(v.get("item", "")).upper() for v in result.get("violations", [])]
    row = {"판정_결과": got, "위반_항목_결과": ", ".join(items), "판정_일치": int(got == expected_verdict),
           "놓침": int(expected_verdict == "위반" and got == "통과"),
           "과잉_차단": int(expected_verdict == "통과" and got == "위반"), "항목_일치": ""}
    if expected_verdict == "위반" and got == "위반" and expected_item:
        row["항목_일치"] = int(expected_item.upper() in items)
    return row


def summarize(rows: list) -> list:
    done = [r for r in rows if "판정_일치" in r]
    viol = [r for r in done if r["정답_판정"] == "위반"]
    ok = [r for r in done if r["정답_판정"] == "통과"]
    item_rows = [r for r in done if r.get("항목_일치") != ""]
    costs = [r["비용_USD"] for r in done if r.get("비용_USD") not in ("", None)]
    lines = [
        ("실행 문항 수", len(rows)),
        ("오류", len(rows) - len(done)),
        ("판정 일치", f"{sum(r['판정_일치'] for r in done)}/{len(done)}"),
        ("놓침 (위반인데 통과)", f"{sum(r['놓침'] for r in viol)}/{len(viol)}"),
        ("과잉 차단 (통과인데 위반)", f"{sum(r['과잉_차단'] for r in ok)}/{len(ok)}"),
        ("항목 일치 (위반을 맞힌 것 중)", f"{sum(r['항목_일치'] for r in item_rows)}/{len(item_rows)}" if item_rows else ""),
        ("비용 합계 USD", round(sum(costs), 4) if costs else ""),
    ]
    for item in ("C1", "C2", "C3", "C4", "C5", "R1"):
        sub = [r for r in viol if r["정답_항목"].upper() == item]
        if sub:
            lines.append((f"  {item} 위반 잡음", f"{sum(1 - r['놓침'] for r in sub)}/{len(sub)}"))
    return lines


def save(path, meta, rows, summary):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    head_font, head_fill = Font(bold=True), PatternFill("solid", fgColor="E8E6F8")
    miss_fill = PatternFill("solid", fgColor="FBE3E3")
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    for k, v in list(meta.items()) + [("", "")] + summary:
        ws.append([k, v])
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 30
    sh = wb.create_sheet("결과")
    keys = list(dict.fromkeys(k for r in rows for k in r))
    sh.append(keys)
    for r in rows:
        sh.append([r.get(k, "") for k in keys])
    for c in sh[1]:
        c.font, c.fill = head_font, head_fill
    widths = {"답변": 70, "질문_참고": 28, "위반_목록": 50, "메모": 30, "오류": 40}
    for i, k in enumerate(keys, 1):
        sh.column_dimensions[get_column_letter(i)].width = widths.get(k, 12)
    for row in sh.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
            col = keys[c.column - 1]
            if (col in ("판정_일치", "항목_일치") and str(c.value) == "0") or (col in ("놓침", "과잉_차단") and str(c.value) == "1"):
                c.fill = miss_fill
    sh.freeze_panes = "B2"
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="쉼표로 구분한 id (V01, P02 …)")
    ap.add_argument("--model", help="에이전트 모델 ID. 생략하면 .env의 AGENT_MODEL")
    ap.add_argument("--no-langfuse", action="store_true")
    ap.add_argument("--with-question", action="store_true", help="질문_참고 칸을 검수에 함께 넘김 (P-068)")
    args = ap.parse_args()

    rows_in = read_rows()
    if args.ids:
        keep = {x.strip() for x in args.ids.split(",") if x.strip()}
        rows_in = [r for r in rows_in if r["id"] in keep]
    if not rows_in:
        sys.exit("실행할 문항이 없습니다.")

    from src import config
    from src.nodes.n6_compliance import judge
    from src.runner import flush

    config.set_model(args.model)
    config.set_tracing(not args.no_langfuse)
    model = config.current_model()
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"검수 노드 검증셋 {len(rows_in)}개 · 모델 {model}" + (" · 질문 넘김" if args.with_question else ""))

    rows = []
    for i, r in enumerate(rows_in, 1):
        row = dict(r)
        try:
            result, usage = judge(r["답변"], r["의도"], r.get("질문_참고") if args.with_question else None)
            row.update(score(r["정답_판정"], r.get("정답_항목", ""), result))
            row["위반_목록"] = " | ".join(f"{v.get('item')}: {v.get('sentence')} — {v.get('reason')}"
                                       for v in result.get("violations", []))
            row["비용_USD"] = usage.get("cost_usd")
            mark = "O" if row["판정_일치"] else "X"
            print(f"[{i}/{len(rows_in)}] {r['id']} 정답 {r['정답_판정']} · 판정 {row['판정_결과']} {mark}")
        except Exception as e:  # 한 문항 실패가 전체를 멈추지 않게
            row["오류"] = f"{type(e).__name__}: {e}"
            print(f"[{i}/{len(rows_in)}] {r['id']} 오류: {row['오류']}")
        rows.append(row)
    flush()

    summary = summarize(rows)
    meta = {"실행 시각": run_id, "모델": model, "문항": args.ids or "전체", "질문 넘김": "예" if args.with_question else "아니요"}
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"compliance_{model.replace('/', '_')}{'_q' if args.with_question else ''}_{run_id}.xlsx"
    save(out, meta, rows, summary)
    print("\n요약")
    for k, v in summary:
        print(f"- {k}: {v}")
    print(f"\n결과 파일: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
