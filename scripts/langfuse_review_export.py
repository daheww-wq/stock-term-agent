"""측정 검토 결과 내려받기 (P-034). 랭퓨즈 대기열에서 사람이 매긴 점수·코멘트를 엑셀 하나로 모은다.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python scripts/langfuse_review_export.py --result results/test_ABC_google_gemini-3.8-flash_20261008_154517.xlsx --run 1차

대기열 밖 trace도 같이 (P-049): 다른 측정 결과 엑셀에서 문항-설정을 골라 trace 화면(Annotate)에서 매긴 점수를 읽는다
  python scripts/langfuse_review_export.py --result results/test_ABC_…_110507.xlsx --run 2차 \
      --extra-result results/test_BCD_…_173514.xlsx --extra S17-C,S45-D,M15-2-D,M14-2-D

결과: results/review_<실행 이름>_<시각>.xlsx
- 검토: 대기열 순서대로 문항-설정, 꼭 확인 이유, 상태(완료/대기), 사람 점수(검토_*), 사람 코멘트, LLM 채점(사전밖_*)
- 요약: 상태 건수, 검토_원인별 건수와 문항, 검토_의도별 건수, LLM 채점과 사람 판정 일치
- 대기열 밖 (--extra를 줬을 때): 같은 칸으로 따로 모은 탭. 요약에도 따로 적고 대기열 수치에는 섞지 않는다
랭퓨즈에는 쓰지 않고 읽기만 한다. 키는 .env에서 읽고 출력하지 않는다.
"""
import argparse
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "scripts"))
import review_queue  # noqa: E402
from langfuse_setup import read_result  # noqa: E402

HUMAN = [sc["name"] for sc in review_queue.SCORE_CONFIGS]
LLM = {"unknown_meaning_ok": "LLM_뜻일치", "unknown_no_false_fact": "LLM_틀린사실없음"}
AUTO_PREFIXES = (review_queue.KEY_PREFIX, review_queue.COMMENT_PREFIX)


def _value(s):
    """v3 점수 값: 선택형은 이름(str), 예/아니오형은 bool, 숫자형은 수"""
    v = getattr(s, "value", None)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else v
    return v


def trace_scores(api, trace_id):
    """trace의 점수 전부 (v3 API, 커서로 끝까지). v2(scores.get_many)는 2026.09.16 이후 만든 조직에서 막혀 있다"""
    if not hasattr(api, "scores_v3"):
        sys.exit("langfuse 패키지가 오래돼 점수 v3 API가 없습니다. pip install -U langfuse 후 다시 실행해 주세요.")
    out, cursor = [], None
    while True:
        res = api.scores_v3.get_many_v3(trace_id=trace_id, fields="details", limit=100, cursor=cursor)
        out.extend(res.data)
        cursor = getattr(res.meta, "cursor", None)
        if not cursor or not res.data:
            return out


def _bool(v):
    if v in ("", None):
        return None
    return str(v).strip().lower() in ("1", "1.0", "true", "예", "yes")


def extra_items(results: dict, labels: list) -> list:
    """대기열 밖 trace (P-049). results = {설정: (단발 행, 멀티턴 행)}, labels = ["S17-C", ...] (적은 순서대로)"""
    found = {}
    for mode, (s_rows, m_rows) in results.items():
        for r in list(s_rows) + list(m_rows):
            label = f"{review_queue.item_key(r)}-{mode}"
            tid = review_queue._txt(r.get("trace_id"))
            if label in labels and tid:
                found[label] = {"trace_id": tid, "label": label, "must": True, "extra": True,
                                "reasons": review_queue.flag_reasons(r)}
    missing = [x for x in labels if x not in found]
    if missing:
        print(f"(대기열 밖: 결과 엑셀에서 찾지 못함 {', '.join(missing)})")
    return [found[x] for x in labels if x in found]


def collect(api, items, queue_id=None):
    status = {x.object_id: str(getattr(x.status, "value", x.status))
              for x in review_queue._all_pages(api.annotation_queues.list_queue_items, queue_id)} if queue_id else {}
    rows = []
    for i, x in enumerate(items, 1):
        tid = x["trace_id"]
        scores = trace_scores(api, tid)
        row = {"순서": i, "문항-설정": x["label"], "꼭 확인": "대기열 밖" if x.get("extra") else ("예" if x["must"] else ""),
               "꼭 확인 이유": " / ".join(g for g, _ in x["reasons"]),
               "상태": {"COMPLETED": "완료", "PENDING": "대기"}.get(status.get(tid, ""), status.get(tid, ""))}
        notes = []
        for s in scores:
            src = str(getattr(getattr(s, "source", ""), "value", getattr(s, "source", "")))
            if s.name in HUMAN and src == "ANNOTATION":
                row[s.name] = _value(s)
                if getattr(s, "comment", None):
                    notes.append(f"{s.name}: {s.comment}")
            elif s.name in LLM:
                row[LLM[s.name]] = _value(s)
        comments = api.comments.get(object_type="TRACE", object_id=tid, limit=100).data
        people = [c.content for c in comments if not (c.content or "").startswith(AUTO_PREFIXES)]
        row["점수 코멘트"] = " | ".join(notes)
        row["사람 코멘트"] = " | ".join(people)
        row["trace_id"] = tid
        if x.get("extra"):  # 대기열 상태가 없으니 사람 점수가 있으면 완료
            row["상태"] = "완료" if any(row.get(h) not in (None, "") for h in HUMAN) else "점수 없음"
        rows.append(row)
    return rows


def summarize(rows):
    out = [("검토한 건수", f"{sum(r['상태'] == '완료' for r in rows)}/{len(rows)}"),
           ("꼭 확인 중 완료", f"{sum(r['상태'] == '완료' for r in rows if r['꼭 확인'])}/{sum(1 for r in rows if r['꼭 확인'])}"),
           ("", "")]
    for name in ("검토_원인", "검토_의도"):
        out.append((f"[{name}]", ""))
        groups = {}
        for r in rows:
            if r.get(name) not in (None, ""):
                groups.setdefault(str(r[name]), []).append(r["문항-설정"])
        for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            out.append((f"  {k} ({len(v)})", ", ".join(v)))
        out.append(("", ""))
    out.append(("[LLM 채점과 사람 판정]", ""))
    for human, llm in (("검토_사전밖_뜻", "LLM_뜻일치"), ("검토_사전밖_틀린사실없음", "LLM_틀린사실없음")):
        both = [r for r in rows if _bool(r.get(human)) is not None and _bool(r.get(llm)) is not None]
        diff = [r["문항-설정"] for r in both if _bool(r.get(human)) != _bool(r.get(llm))]
        out.append((f"  {human} vs {llm}", f"일치 {len(both) - len(diff)}/{len(both)}" + (f" · 다름: {', '.join(diff)}" if diff else "")))
    return out


def save(path, meta, rows, summary, extra_rows=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    for k, v in list(meta.items()) + [("", "")] + summary:
        ws.append([k, v])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 100
    sh = wb.create_sheet("검토")
    keys = ["순서", "문항-설정", "꼭 확인", "꼭 확인 이유", "상태", *HUMAN, *LLM.values(), "점수 코멘트", "사람 코멘트", "trace_id"]
    sh.append(keys)
    for r in rows:
        sh.append([r.get(k, "") for k in keys])
    head = PatternFill("solid", fgColor="E8E6F8")
    for c in sh[1]:
        c.font, c.fill = Font(bold=True), head
    widths = {"문항-설정": 12, "꼭 확인 이유": 24, "점수 코멘트": 40, "사람 코멘트": 50, "trace_id": 34}
    for i, k in enumerate(keys, 1):
        sh.column_dimensions[get_column_letter(i)].width = widths.get(k, 14)
    for row in sh.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    sh.freeze_panes = "C2"
    if extra_rows:
        ex = wb.create_sheet("대기열 밖")
        ex.append(keys)
        for r in extra_rows:
            ex.append([r.get(k, "") for k in keys])
        for c in ex[1]:
            c.font, c.fill = Font(bold=True), head
        for i, k in enumerate(keys, 1):
            ex.column_dimensions[get_column_letter(i)].width = widths.get(k, 14)
        for row in ex.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ex.freeze_panes = "C2"
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True, help="측정 결과 엑셀 (대기열을 만든 것과 같은 파일)")
    ap.add_argument("--run", default="1차")
    ap.add_argument("--extra-result", help="대기열 밖 trace를 찾을 측정 결과 엑셀 (P-049)")
    ap.add_argument("--extra", default="", help="대기열 밖 문항-설정, 쉼표로 (예: S17-C,S45-D)")
    args = ap.parse_args()
    if bool(args.extra_result) != bool(args.extra):
        sys.exit("--extra-result와 --extra는 같이 줘야 합니다.")
    result_path = pathlib.Path(args.result)
    if not result_path.is_absolute():
        result_path = ROOT / result_path
    items = review_queue.plan(read_result(result_path), args.run)

    from src import config  # noqa: F401  (.env 읽기)
    if not config.langfuse_configured():
        sys.exit(".env에 랭퓨즈 키가 없습니다.")
    from langfuse import get_client
    api = get_client().api
    name = review_queue.queue_name(args.run)
    q = next((q for q in review_queue._all_pages(api.annotation_queues.list_queues) if q.name == name), None)
    if q is None:
        sys.exit(f"대기열 '{name}'이 없습니다.")

    rows = collect(api, items, q.id)
    summary = summarize(rows)
    meta = {"대기열": name, "측정 결과": result_path.name}
    extra_rows = []
    if args.extra_result:
        extra_path = pathlib.Path(args.extra_result)
        if not extra_path.is_absolute():
            extra_path = ROOT / extra_path
        labels = [x.strip() for x in args.extra.split(",") if x.strip()]
        extra_rows = collect(api, extra_items(read_result(extra_path), labels))
        meta["대기열 밖 측정 결과"] = extra_path.name
        summary += [("", ""), ("[대기열 밖]", ", ".join(labels))] + summarize(extra_rows)
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    meta["내려받은 시각"] = run_id
    out = ROOT / "results" / f"review_{args.run}_{run_id}.xlsx"
    save(out, meta, rows, summary, extra_rows)
    for k, v in summary:
        if k:
            print(f"{k} {v}")
    print(f"\n결과 파일: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
