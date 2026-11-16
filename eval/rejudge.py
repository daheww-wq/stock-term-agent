"""사전 밖 답변을 다른 채점 모델로 다시 채점 (P-050). 에이전트는 다시 돌리지 않는다.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python eval/rejudge.py --result results/test_ABC_…_110507.xlsx --judge-model <모델 ID> --review results/review_2차_….xlsx
  python eval/rejudge.py --result … --judge-model <모델 ID> --dry-run   # 대상 건수만 보고 부르지 않음

- 결과 엑셀에서 답변(노드 5)을 만든 턴 중 "사전 근거 없음" 용어가 있는 턴만 다시 채점한다 (P-043 기준)
- 질문·용어·답변·평가용 정답은 처음 채점과 같게 넘긴다 (eval/judge.py, 평가용 정답 파일 + 정답지 풀이 P-039).
  P-051부터는 질문 속 표현 풀이(풀이_결과)도 넘기고, 되물은 용어는 뜻을 빈칸(해당 없음)으로 둔다.
  같은 채점 모델로 다시 돌리면 채점 기준을 바꾼 효과를 볼 수 있다
- --review를 주면 사람 판정(검토_사전밖_뜻 · 검토_사전밖_틀린사실없음, 매긴 그대로)과
  처음 채점·새 채점을 나란히 놓고, 서로 판정이 같은 답변 수를 센다
- 랭퓨즈에는 쓰지 않는다 (처음 채점 점수를 덮지 않게). 키는 .env에서 읽고 출력하지 않는다

결과: results/rejudge_<모델 이름>_<시각>.xlsx (요약 · 채점 탭)
"""
import argparse
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "eval", ROOT / "scripts"):
    sys.path.insert(0, str(p))
import review_queue  # noqa: E402
from langfuse_setup import read_result  # noqa: E402

PAIRS = (("뜻", "사전밖_뜻일치", "검토_사전밖_뜻"), ("틀린 사실 없음", "사전밖_틀린사실없음", "검토_사전밖_틀린사실없음"))


def _bool(v):
    if v in ("", None):
        return None
    return str(v).strip().lower() in ("1", "1.0", "true", "예", "yes")


def targets(results: dict) -> list:
    """다시 채점할 턴. results = {설정: (단발 행, 멀티턴 행)}"""
    out = []
    for mode in sorted(results):
        s_rows, m_rows = results[mode]
        for r in list(s_rows) + list(m_rows):
            terms = [t.strip() for t in str(r.get("사전_근거_없음") or "").split(" · ") if t.strip()]
            if terms and "5 답변" in str(r.get("경로") or ""):
                out.append({"label": f"{review_queue.item_key(r)}-{mode}", "row": r, "terms": terms})
    return out


def read_review(path: pathlib.Path) -> dict:
    """검토 결과 엑셀(P-034·P-049) → {문항-설정: {검토_사전밖_뜻, 검토_사전밖_틀린사실없음}}"""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    out = {}
    for name in ("검토", "대기열 밖"):
        if name not in wb.sheetnames:
            continue
        rows = list(wb[name].iter_rows(values_only=True))
        head = rows[0]
        for r in rows[1:]:
            rec = dict(zip(head, r))
            out[str(rec.get("문항-설정"))] = {k: rec.get(k) for _, _, k in PAIRS}
    return out


def compare(rows: list, a: str, b: str) -> tuple:
    """두 판정 칸이 모두 있는 행에서 같은 건수, 비교한 건수, 다른 문항"""
    both = [r for r in rows if _bool(r.get(a)) is not None and _bool(r.get(b)) is not None]
    diff = [r["문항-설정"] for r in both if _bool(r.get(a)) != _bool(r.get(b))]
    return len(both) - len(diff), len(both), diff


def summarize(rows: list, old_model: str, new_model: str) -> list:
    out = [("다시 채점한 답변", len(rows))]
    costs = [r["새_채점_비용_USD"] for r in rows if r.get("새_채점_비용_USD") not in ("", None)]
    out.append(("새 채점 비용 USD", round(sum(costs), 4) if costs else ""))
    out.append(("새 채점에서 되물어 뜻 해당 없음 (P-051)", sum(1 for r in rows if r.get("새_되물음"))))
    out.append(("새 채점에서 조건부 표준 용어 안내 (P-055)", sum(1 for r in rows if r.get("새_조건부안내"))))
    out.append(("", ""))
    for name, _, _ in PAIRS:
        out.append((f"[{name}]", ""))
        for label, a, b in ((f"처음 채점({old_model}) vs 사람", f"처음_{name}", f"사람_{name}"),
                            (f"새 채점({new_model}) vs 사람", f"새_{name}", f"사람_{name}"),
                            ("처음 채점 vs 새 채점", f"처음_{name}", f"새_{name}")):
            same, n, diff = compare(rows, a, b)
            if n:
                out.append((f"  {name} · {label}", f"{n}건 중 {same}건 같음 ({same / n:.1%})" + (f" · 다름: {', '.join(diff)}" if diff else "")))
        out.append(("", ""))
    return out


def run(items: list, judge_fn, refs_fn, review: dict) -> list:
    """judge_fn(question, terms, answer, refs) → judge_row 결과. refs_fn(terms, row) → 평가용 정답"""
    rows = []
    for x in items:
        r = x["row"]
        rec = {"문항-설정": x["label"], "용어": " · ".join(x["terms"]),
               "처음_뜻": r.get("사전밖_뜻일치"), "처음_틀린 사실 없음": r.get("사전밖_틀린사실없음")}
        try:
            j = judge_fn(r.get("재구성_결과") or r.get("질문"), x["terms"], r.get("최종_답변") or "",
                         refs_fn(x["terms"], r) or None, r.get("풀이_결과") or "")
            rec.update({"새_뜻": j.get("사전밖_뜻일치"), "새_틀린 사실 없음": j.get("사전밖_틀린사실없음"),
                        "새_눈높이": j.get("사전밖_눈높이"), "새_되물음": j.get("사전밖_되물음"),
                        "새_조건부안내": j.get("사전밖_조건부안내"),
                        "새_채점메모": j.get("사전밖_채점메모"),
                        "새_채점_비용_USD": j.get("채점_비용_USD")})
        except Exception as e:  # 한 건 실패가 전체를 멈추지 않게
            rec["새_채점메모"] = f"[채점 오류] {type(e).__name__}: {e}"
        human = review.get(x["label"], {})
        rec["사람_뜻"] = human.get("검토_사전밖_뜻")
        rec["사람_틀린 사실 없음"] = human.get("검토_사전밖_틀린사실없음")
        rows.append(rec)
    return rows


def save(path, meta, rows, summary):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    for k, v in list(meta.items()) + [("", "")] + summary:
        ws.append([k, v])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 100
    sh = wb.create_sheet("채점")
    keys = ["문항-설정", "용어", "처음_뜻", "새_뜻", "사람_뜻", "처음_틀린 사실 없음", "새_틀린 사실 없음",
            "사람_틀린 사실 없음", "새_눈높이", "새_되물음", "새_조건부안내", "새_채점메모", "새_채점_비용_USD"]
    sh.append(keys)
    for r in rows:
        sh.append([r.get(k, "") for k in keys])
    for c in sh[1]:
        c.font = Font(bold=True)
    sh.column_dimensions["L"].width = 80
    for row in sh.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    sh.freeze_panes = "B2"
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True, help="측정 결과 엑셀")
    ap.add_argument("--judge-model", required=True, help="새 채점 모델 ID (OpenRouter)")
    ap.add_argument("--review", help="검토 결과 엑셀 (사람 판정과 비교할 때)")
    ap.add_argument("--dry-run", action="store_true", help="대상 건수만 보고 채점 모델을 부르지 않음")
    args = ap.parse_args()

    def resolve(p):
        p = pathlib.Path(p)
        return p if p.is_absolute() else ROOT / p

    result_path = resolve(args.result)
    items = targets(read_result(result_path))
    review = read_review(resolve(args.review)) if args.review else {}
    print(f"다시 채점할 답변 {len(items)}건 (사람 판정 있는 것 {sum(1 for x in items if x['label'] in review)}건)")
    if args.dry_run:
        return

    from src import config
    import judge as J
    import run_dev as RD
    config.set_tracing(False)  # 랭퓨즈에 쓰지 않음
    old_model = config.JUDGE_MODEL
    config.JUDGE_MODEL = args.judge_model  # judge.py가 부를 때마다 config.JUDGE_MODEL을 읽는다
    refs = RD.load_references()
    rows = run(items, J.judge_row, lambda terms, row: RD.judge_references(terms, refs, row), review)

    summary = summarize(rows, old_model, args.judge_model)
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    short = args.judge_model.split("/")[-1].replace(":", "_")
    out = ROOT / "results" / f"rejudge_{short}_{run_id}.xlsx"
    meta = {"측정 결과": result_path.name, "처음 채점 모델": old_model, "새 채점 모델": args.judge_model,
            "검토 결과": resolve(args.review).name if args.review else "없음", "실행 시각": run_id}
    save(out, meta, rows, summary)
    for k, v in summary:
        if k:
            print(f"{k} {v}")
    print(f"\n결과 파일: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
