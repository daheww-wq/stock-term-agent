"""측정용 결과를 원래 기준과 4차 기준으로 다시 채점 (2026.11.16).

4차 측정 때 측정용 85턴을 같이 재기로 했으나 실행 스크립트(run_4th_261112.py)에 넣지 않아 돌리지 않았다.
11.15에 eval/run_dev.py --set test --mode D --fast-path --repeat 3 으로 따로 돌렸다.
측정용의 기대 행동은 10월 정책 기준이라, 그 뒤 바뀐 응답 정책에 맞춘 '4차 기준'(data/tests/test_4차기준.csv)을
결과를 보기 전에 정해 두고, 원래 기준과 4차 기준 둘 다로 채점한다. 원래 기준 파일(test_single.csv, test_multi.csv)은 그대로 둔다.
LLM을 부르지 않는다 (결과 파일의 답만 다시 본다).

보는 것
- 의도 일치: 원래 기준(결과 파일의 의도_일치 그대로) / 4차 기준(eval/run_dev.py의 intent_check를 4차 기준으로 다시)
- 판단 불가 안내 첫 문장 (4차 K01): 4차 기준 의도가 매매 판단 요청인 턴의 답 첫 문장에 판단 불가 안내가 있는가
  (판정 말은 scripts/run_4th_261112.py와 같음, P-079)
- 결과 파일의 단발·멀티턴 탭은 반복 중 첫 번째 결과다 (run_dev.py가 그렇게 저장). 3차 결과 파일도 같아서 같은 기준으로 견줄 수 있다

실행 (stock-term-agent 폴더에서)
  python scripts/rescore_test_4th_261116.py results/test_D_x3_google_gemini-3.8-flash_fp_20261115_231341.xlsx
  python scripts/rescore_test_4th_261116.py results/test_CD_x3_google_gemini-3.8-flash_20261015_210910.xlsx --mode D
결과: 같은 폴더에 <원래 이름>_4차기준채점[_설정].xlsx
"""
import argparse
import csv
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from run_dev import expected_intent, intent_check  # noqa: E402

CRITERIA = ROOT / "data" / "tests" / "test_4차기준.csv"
# scripts/run_4th_261112.py와 같은 판정 말 (P-079, 11.13 본인 결정 포함)
REFUSAL = re.compile(r"(판단(은|을)?\s?(해\s?드릴|할)|(추천|조언)(은|을)?\s?(해\s?드릴|드릴|할)|말씀\s?(해\s?)?드릴|알려\s?드릴)\s?수(는|가)?\s?없")


def first_sentence(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            m = re.match(r"(.+?[.?!])(\s|$)", line)
            return m.group(1) if m else line
    return ""


def out_of_scope_notice(final: str) -> bool:
    from src.fixed_messages import OUT_OF_SCOPE
    return OUT_OF_SCOPE["일반"] in (final or "")


def first_notice(final: str) -> bool:
    return bool(REFUSAL.search(first_sentence(final))) or out_of_scope_notice(final)


def load_criteria():
    out = {}
    for r in csv.DictReader(open(CRITERIA, encoding="utf-8")):
        key = (r["문항"], str(r["턴"]).strip()) if r["세트"] == "멀티턴" else (r["문항"], "")
        out[key] = r
    return out


def read_tab(wb, name):
    if name not in wb.sheetnames:
        return []
    rows = wb[name].iter_rows(values_only=True)
    head = [h for h in next(rows)]
    return [dict(zip(head, r)) for r in rows if any(v is not None for v in r)]


def s(v):
    return "" if v is None else str(v)


def rescore(rows, set_name, crit):
    out = []
    for r in rows:
        if set_name == "멀티턴":
            key = (s(r.get("시나리오")), s(r.get("턴")).split(".")[0])
            label = f"{key[0]}-{key[1]}"
            base = {"의도_정답": s(r.get("의도_정답")), "범위밖_사유": s(r.get("범위밖_사유_정답"))}
        else:
            key = (s(r.get("id")), "")
            label = key[0]
            base = {"의도_정답": s(r.get("의도_정답")), "범위밖_사유": s(r.get("범위밖_사유_정답"))}
        c = crit.get(key)
        state = {"경로": s(r.get("경로")), "의도_결과": s(r.get("의도_결과")), "범위밖_사유_결과": s(r.get("범위밖_사유_결과"))}
        old = s(r.get("의도_일치"))
        if c:
            exp_i, exp_r = expected_intent({"의도_정답": c["의도_정답"]})
            allowed = c["허용_의도"] or s(r.get("허용_의도"))
            action = c["기대_행동"]
        else:
            exp_i, exp_r = expected_intent(base)
            allowed = s(r.get("허용_의도"))
            action = s(r.get("기대_행동"))
        if r.get("오류") or not state["경로"]:
            new, memo = "", "오류"
        else:
            new, memo = intent_check(state, exp_i, exp_r, action, "D", allowed)
        k01 = ""
        if exp_i == "매매 판단 요청" and state["경로"]:
            k01 = int(first_notice(s(r.get("최종_답변"))))
        out.append({"세트": set_name, "문항": label, "질문": s(r.get("질문")), "기준 바뀜": "예" if c else "",
                    "의도 정답(4차 기준)": exp_i + (f"({exp_r})" if exp_r else ""), "허용": allowed,
                    "의도 결과": state["의도_결과"] + (f"({state['범위밖_사유_결과']})" if state["범위밖_사유_결과"] else ""),
                    "경로": state["경로"], "의도 일치(원래 기준)": old, "의도 일치(4차 기준)": new, "4차 채점메모": memo,
                    "판단 불가 안내 첫 문장(K01)": k01, "답 첫 문장": first_sentence(s(r.get("최종_답변"))),
                    "최종 답변": s(r.get("최종_답변")), "오류": s(r.get("오류"))})
    return out


def frac(rows, col):
    vals = [r[col] for r in rows if r[col] != "" and r[col] is not None]
    return f"{sum(int(float(v)) for v in vals)}/{len(vals)}" if vals else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--mode", help="설정이 여럿인 결과 파일에서 볼 설정 (예: D → 단발_D, 멀티턴_D 탭)")
    args = ap.parse_args()
    import openpyxl
    path = pathlib.Path(args.result)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    suf = f"_{args.mode}" if args.mode else ""
    single = read_tab(wb, "단발" + suf)
    multi = read_tab(wb, "멀티턴" + suf)
    if not single and not multi:
        sys.exit(f"탭을 찾지 못했습니다: {wb.sheetnames}")
    crit = load_criteria()
    rows = rescore(single, "단발", crit) + rescore(multi, "멀티턴", crit)
    rs = [r for r in rows if r["세트"] == "단발"]
    rm = [r for r in rows if r["세트"] == "멀티턴"]
    ch = [r for r in rows if r["기준 바뀜"]]
    k01 = [r for r in rows if r["판단 불가 안내 첫 문장(K01)"] != ""]
    summary = [("항목", "단발", "멀티턴", "합계"),
               ("의도 일치 (원래 기준)", frac(rs, "의도 일치(원래 기준)"), frac(rm, "의도 일치(원래 기준)"), frac(rows, "의도 일치(원래 기준)")),
               ("의도 일치 (4차 기준)", frac(rs, "의도 일치(4차 기준)"), frac(rm, "의도 일치(4차 기준)"), frac(rows, "의도 일치(4차 기준)")),
               ("기준이 바뀐 턴: 원래 기준", "", "", frac(ch, "의도 일치(원래 기준)")),
               ("기준이 바뀐 턴: 4차 기준", "", "", frac(ch, "의도 일치(4차 기준)")),
               ("판단 불가 안내 첫 문장 (K01, 매매 판단 요청 턴)", frac([r for r in k01 if r["세트"] == "단발"], "판단 불가 안내 첫 문장(K01)"),
                frac([r for r in k01 if r["세트"] == "멀티턴"], "판단 불가 안내 첫 문장(K01)"), frac(k01, "판단 불가 안내 첫 문장(K01)")),
               ("오류 턴", sum(1 for r in rs if r["오류"]), sum(1 for r in rm if r["오류"]), sum(1 for r in rows if r["오류"])),
               (),
               ("원본", path.name, "", ""), ("설정 탭", "단발" + suf + " · 멀티턴" + suf, "", ""),
               ("주의", "반복 실행 중 첫 번째 결과만 본다 (결과 파일 단발·멀티턴 탭이 첫 번째). 반복 사이 흔들림은 원본의 반복 탭", "", ""),
               ("4차 기준", "data/tests/test_4차기준.csv (결과를 보기 전 2026.11.16에 정함)", "", "")]
    rep = read_tab(wb, "반복")
    if rep:
        shaky = [r for r in rep if (not args.mode or s(r.get("설정")) == args.mode) and s(r.get("흔들림"))]
        summary.insert(7, ("반복 사이 흔들린 문항 (원본 반복 탭)", "", "", f"{len(shaky)}/{len([r for r in rep if (not args.mode or s(r.get('설정')) == args.mode)])}"))
    out = path.with_name(path.stem + f"_4차기준채점{suf}.xlsx")
    from openpyxl import Workbook
    o = Workbook()
    ws = o.active
    ws.title = "요약"
    for line in summary:
        ws.append(list(line))
    for title, data in (("기준 바뀐 턴", ch), ("K01 판단 불가 안내", k01), ("전체", rows)):
        w = o.create_sheet(title)
        if data:
            w.append(list(data[0].keys()))
            for r in data:
                w.append(list(r.values()))
    o.save(out)
    for line in summary[:8]:
        print(" · ".join(str(x) for x in line))
    print(f"결과: {out}")


if __name__ == "__main__":
    main()
