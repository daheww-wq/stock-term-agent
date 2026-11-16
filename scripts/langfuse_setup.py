"""랭퓨즈 검토·비교 환경 만들기 (P-029, P-030, P-031). 처음 한 번, 그리고 이 기능 전에 돌린 측정(1차)에 쓴다.
여러 번 실행해도 이미 있는 것은 다시 만들지 않는다.

만드는 것
  가. 사람 검토용 점수 항목(Score Configs): 검토_의도, 검토_재구성, 검토_사전밖_뜻, 검토_사전밖_틀린사실없음, 검토_답변품질
  나. 측정 문항 Dataset 2개(단발·멀티턴)를 만들고, 측정 결과 엑셀의 trace를 "<접두어>-A/B/C" 실행으로 연결
     → 랭퓨즈 Datasets 화면에서 문항마다 설정 A·B·C의 답변과 점수를 나란히 본다
  다. 검토 대기열 하나 "<접두어> 측정 검토" (P-030, eval/review_queue.py)
     → 꼭 확인할 것을 앞에(이유는 trace 코멘트), 훑어볼 것을 뒤에 넣고, 모두에 점수 "검토_필요"를 남긴다
  라. 지침(prompts/*.md 6개)을 랭퓨즈 Prompts에 올린다 (P-031). 이름 stock-term/<파일 이름>, 라벨 production
     → 내용이 바뀐 지침만 새 버전. 기준은 저장소 파일이고 랭퓨즈 화면에서 고치지 않는다
     → 이후 LLM 호출마다 쓴 지침 버전이 연결되어 Prompts 화면에서 버전별 사용 횟수·지연·비용·점수를 본다

2차부터는 python eval/run_dev.py --set test --modes A B C --dataset-run 2차 하나로 나·다가 측정 끝에 자동으로 된다.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python scripts/langfuse_setup.py                                   # 가장 최근 측정 결과(results/test_*.xlsx), 실행 이름 "1차"
  python scripts/langfuse_setup.py --result results/test_ABC_...xlsx --run 1차
  python scripts/langfuse_setup.py --dry-run                         # 랭퓨즈에 쓰지 않고 무엇을 만들지만 출력
  python scripts/langfuse_setup.py --prompts-only                    # 가·라만: 점수 항목 + 지침 올리기 (측정 전, 새 랭퓨즈 프로젝트를 쓸 때. P-065)

키는 .env에서 읽고 화면에 출력하지 않는다. 측정용 문항 파일(test_*.csv)을 읽으므로 측정 시점 뒤에만 쓴다.
"""
import argparse
import csv
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "eval"))
from run_dev import DATASET_MULTI, DATASET_SINGLE, multi_item_id, single_item_id  # noqa: E402  (문항 id 규칙을 한 곳에서)
import review_queue  # noqa: E402  (P-030)

TESTS = ROOT / "data" / "tests"


def last_patch() -> str:
    """PATCHES.md의 마지막 패치 번호 → 지침 버전 메모 (예: "P-031 기준 저장소 파일")"""
    nums = re.findall(r"\| (P-\d{3}) \|", (ROOT / "PATCHES.md").read_text(encoding="utf-8"))
    return f"{max(nums)} 기준 저장소 파일" if nums else "저장소 파일"


def read_csv(name):
    with open(TESTS / name, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def read_result(path: pathlib.Path) -> dict:
    """측정 결과 엑셀 → {설정: (단발 행, 멀티턴 행)}"""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    out = {}
    # 설정이 하나뿐인 실행은 탭 이름이 "단발"·"멀티턴"이라 설정을 요약 탭 "설정" 칸에서 읽는다 (P-067)
    single_mode = ""
    if "요약" in wb.sheetnames:
        for r in wb["요약"].iter_rows(values_only=True):
            if r and r[0] == "설정" and r[1]:
                single_mode = str(r[1]).strip()[:1]
                break
    for name in wb.sheetnames:
        if name in ("단발", "멀티턴") and single_mode:
            kind, mode = name, single_mode
        elif "_" in name and name.startswith(("단발", "멀티턴")):
            kind, mode = name.split("_", 1)
        else:
            continue
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        head = rows[0]
        recs = [dict(zip(head, r)) for r in rows[1:]]
        out.setdefault(mode, ([], []))[0 if kind == "단발" else 1].extend(recs)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", help="측정 결과 엑셀. 생략하면 results/test_*.xlsx 중 가장 최근")
    ap.add_argument("--run", default="1차", help="Dataset 실행 이름 접두어 (1차 → 1차-A, 1차-B, 1차-C)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prompts-only", action="store_true",
                    help="점수 항목과 지침만 올림 (측정 결과·측정용 문항을 읽지 않음). 새 랭퓨즈 프로젝트에서 측정 전에 (P-065)")
    args = ap.parse_args()

    if args.prompts_only:
        from src import config  # noqa: F401  (.env 읽기)
        from src.llm import prompt_files, sync_prompts
        print("지침(랭퓨즈 Prompts): " + ", ".join(prompt_files()))
        if args.dry_run:
            return
        if not config.langfuse_configured():
            sys.exit(".env에 랭퓨즈 키가 없습니다.")
        from langfuse import get_client
        lf = get_client()
        review_queue.ensure_score_configs(lf.api)
        print("점수 항목 준비됨: " + ", ".join(sc["name"] for sc in review_queue.SCORE_CONFIGS))
        for name, status in sync_prompts(lf, note=last_patch()):
            print(f"지침 {name}: {status}")
        lf.flush()
        print("완료. 이제 측정 실행의 LLM 호출마다 이 프로젝트의 지침 버전이 연결됩니다.")
        return

    if args.result:
        result_path = ROOT / args.result if not pathlib.Path(args.result).is_absolute() else pathlib.Path(args.result)
    else:
        found = sorted((ROOT / "results").glob("test_*.xlsx"), key=lambda p: p.stat().st_mtime)
        if not found:
            sys.exit("results 폴더에 측정 결과(test_*.xlsx)가 없습니다.")
        result_path = found[-1]
    result = read_result(result_path)
    single, multi = read_csv("test_single.csv"), read_csv("test_multi.csv")
    items = review_queue.plan(result, args.run)
    print(f"측정 결과: {result_path.name} · 설정 {' '.join(result)}")
    print(f"Dataset: 단발 {len(single)} · 멀티턴 {len(multi)}턴")
    review_queue.print_plan(items)
    from src.llm import prompt_files
    print("지침(랭퓨즈 Prompts): " + ", ".join(prompt_files()))
    if args.dry_run:
        return

    from src import config  # noqa: F401  (.env 읽기)
    if not config.langfuse_configured():
        sys.exit(".env에 랭퓨즈 키가 없습니다.")
    from langfuse import get_client
    lf = get_client()
    api = lf.api

    # 가. 점수 항목
    review_queue.ensure_score_configs(api)
    print("점수 항목 준비됨: " + ", ".join(sc["name"] for sc in review_queue.SCORE_CONFIGS))

    # 나. Dataset과 문항 (문항 id를 고정해 다시 실행해도 같은 문항을 덮어씀)
    n_scen = len({r["시나리오"] for r in multi})
    for name, desc in ((DATASET_SINGLE, f"측정용 단발 {len(single)} (data/tests/test_single.csv)"),
                       (DATASET_MULTI, f"측정용 멀티턴 {n_scen}건 {len(multi)}턴 (data/tests/test_multi.csv)")):
        try:
            api.datasets.get(name)
            print(f"Dataset 있음: {name}")
        except Exception:
            api.datasets.create(name=name, description=desc)
            print(f"Dataset 만듦: {name}")
    for r in single:
        api.dataset_items.create(
            dataset_name=DATASET_SINGLE, id=single_item_id(r["id"]),
            input={"질문": r["질문"]},
            expected_output={"의도": r["의도_정답"], "범위밖_사유": r.get("범위밖_사유", ""),
                             "풀이": r.get("풀이_정답", ""), "기대_행동": r.get("기대_행동", "")},
            metadata={k: r.get(k, "") for k in ("id", "세트", "하위구분", "슬랭_유형", "RQ1_구분", "관용구_패턴사전", "출처", "확인_포인트")})
    for r in multi:
        api.dataset_items.create(
            dataset_name=DATASET_MULTI, id=multi_item_id(r["시나리오"], r["턴"]),
            input={"시나리오": r["시나리오"], "턴": r["턴"], "질문": r["질문"]},
            expected_output={"재구성": r["재구성_정답"], "의도": r["의도_정답"], "허용_의도": r.get("허용_의도", ""),
                             "기대_행동": r["기대_행동"]},
            metadata={k: r.get(k, "") for k in ("시나리오", "턴", "세트", "유형", "확인_포인트")})
    print(f"Dataset 문항 올림: 단발 {len(single)} · 멀티턴 {len(multi)}")

    # 나. 측정 trace를 Dataset 실행으로 연결
    ds_ids = {DATASET_SINGLE: api.datasets.get(DATASET_SINGLE).id, DATASET_MULTI: api.datasets.get(DATASET_MULTI).id}
    for mode, (s_rows, m_rows) in result.items():
        run_name = f"{args.run}-{mode}"
        for ds, rows, to_id in ((DATASET_SINGLE, s_rows, lambda r: single_item_id(r["id"])),
                                (DATASET_MULTI, m_rows, lambda r: multi_item_id(r["시나리오"], r["턴"]))):
            try:
                done = {x.dataset_item_id for x in api.dataset_run_items.list(dataset_id=ds_ids[ds], run_name=run_name, limit=100).data}
            except Exception:
                done = set()
            n = 0
            for r in rows:
                if not r.get("trace_id") or to_id(r) in done:
                    continue
                api.dataset_run_items.create(run_name=run_name, dataset_item_id=to_id(r), trace_id=r["trace_id"],
                                             run_description=f"{result_path.name} · 설정 {mode} ({config.MODES.get(mode, '')})")
                n += 1
            print(f"Dataset 실행 연결: {ds} · {run_name} · 새로 {n}개 (이미 {len(done)}개)")

    # 다. 검토 대기열 (P-030)
    r = review_queue.build(lf, args.run, items, source=result_path.name)
    print(f"대기열 '{r['queue']}': 새로 {r['added']}개 넣음 (모두 {r['items']}개 · 꼭 확인 {r['must']}개) · 코멘트 새로 {r['commented']}개")

    # 라. 지침 올리기 (P-031)
    from src.llm import sync_prompts
    for name, status in sync_prompts(lf, note=last_patch()):
        print(f"지침 {name}: {status}")
    lf.flush()

    print("\n완료. 랭퓨즈 왼쪽 메뉴 Human Annotation(대기열), Datasets(설정별 비교), Prompts(지침 버전)에서 확인하세요.")


if __name__ == "__main__":
    main()
