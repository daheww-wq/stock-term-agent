"""4차 측정 새 문항이 기존 측정용 문항과 겹치는지 검사 (2026.11.12).

왜: 개발용 새 문항이 기존 측정용과 같으면 고칠 때 보는 문항과 근거 숫자를 내는 문항이 겹친다.
    홀드아웃 새 문항이 기존 측정용과 같으면 같은 문항을 두 번 세게 된다.
    Claude는 측정용 문항(data/tests/test_*)을 열어 보지 않으므로 이 검사는 사람이 PC에서 돌린다.

읽는 것
- 새 문항: data/tests_4th/LangGraph_PoC_4차측정_문항구성안_261111.xlsx (개발용),
           data/holdout/LangGraph_PoC_4차측정_문항구성안_홀드아웃_261111.xlsx (홀드아웃)
           의 문항_자연 · 문항_강제 · 문항_검수단독 시트
- 기존 측정용: data/tests/test_*.csv 에서 이름에 '질문'이 든 칸
- 기존 개발용: data/tests/dev_*.csv 에서 이름에 '질문'이 든 칸 (K34 후보를 고를 때만 씀. 11.12 추가)

보는 것 (셋 다 띄어쓰기와 문장부호는 빼고 비교)
- 같은 문장: 문장 전체가 같다
- 앞부분 같음: "뭐야?", "무슨 뜻이야?" 같은 끝말을 뺀 앞부분이 같다 (예: "컨콜이 뭐야?"와 "컨콜이 무슨 뜻이야?")
- 8자 겹침 (참고): 끝말을 뺀 앞부분에서 8자 이상이 그대로 들어 있다

화면과 결과 파일에는 새 문항 쪽 내용만 적는다. 측정용 문장은 적지 않고 파일 이름과 줄 번호만 적는다.
LLM을 부르지 않는다. 에이전트 코드도 건드리지 않는다.

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python scripts/check_overlap_4th_261112.py
결과: results/overlap_4th_<시각>.csv
"""
import csv
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NEW_FILES = [
    ("개발용", DATA / "tests_4th" / "LangGraph_PoC_4차측정_문항구성안_261111.xlsx"),
    ("홀드아웃", DATA / "holdout" / "LangGraph_PoC_4차측정_문항구성안_홀드아웃_261111.xlsx"),
]
ITEM_SHEETS = {"문항_자연": "질문", "문항_강제": "질문", "문항_검수단독": "함께 넘기는 질문"}
CHIPS = {"맞아요", "다른뜻이에요", "몰라요"}  # 빠른 답 칩. 화면의 고정 글자라 겹쳐도 된다

# 뜻을 묻는 흔한 끝말 (긴 것부터)
TAILS = sorted([
    "이라는말을봤는데뭐야", "라는말을봤는데뭐야", "이라는게무슨뜻이야", "라는게무슨뜻이야", "이라는게무슨말이야", "라는게무슨말이야",
    "다는게무슨뜻이야", "다는게무슨말이야", "다는게뭐야", "이라는게뭐야", "라는게뭐야", "가무슨뜻이야", "이무슨뜻이야",
    "은무슨뜻이야", "는무슨뜻이야", "무슨뜻이야", "무슨뜻이에요", "무슨말이야", "뜻알려줘", "이뭐예요", "가뭐예요", "이뭐야", "가뭐야",
    "은뭐야", "는뭐야", "뭐예요", "뭐야",
], key=len, reverse=True)


def norm(s):
    return re.sub(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]", "", s or "")


def core(s):
    n = norm(s)
    for t in TAILS:
        if n.endswith(t) and len(n) > len(t):
            return n[: -len(t)]
    return n


def share8(a, b):
    if len(a) < 8 or len(b) < 8:
        return False
    return any(a[i:i + 8] in b for i in range(len(a) - 7))


def load_new():
    from openpyxl import load_workbook
    items = []
    for set_name, path in NEW_FILES:
        if not path.exists():
            print(f"[없음] {path}")
            continue
        wb = load_workbook(path, read_only=True, data_only=True)
        for sheet, qcol in ITEM_SHEETS.items():
            if sheet not in wb.sheetnames:
                continue
            rows = wb[sheet].iter_rows(values_only=True)
            head = [str(h or "") for h in next(rows)]
            if qcol not in head or "id" not in head:
                print(f"[칸 없음] {path.name} / {sheet}")
                continue
            qi, ii = head.index(qcol), head.index("id")
            ki = head.index("경우") if "경우" in head else None
            for r in rows:
                q = r[qi]
                if not q or norm(str(q)) in CHIPS:
                    continue
                items.append({"세트": set_name, "시트": sheet, "id": r[ii], "경우": r[ki] if ki is not None else "",
                              "질문": str(q)})
    return items


def load_tests():
    out = []
    for path in sorted((ROOT / "data" / "tests").glob("test_*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = [c for c in (reader.fieldnames or []) if "질문" in c]
            for line, row in enumerate(reader, 2):
                for c in cols:
                    v = (row.get(c) or "").strip()
                    if v:
                        out.append({"파일": path.name, "줄": line, "칸": c, "n": norm(v), "c": core(v)})
    return out


def load_dev_cores():
    """기존 개발용 문항(dev_*.csv)의 질문 앞부분. 후보가 기존 개발용과 겹치지 않게 (11.12: '갭상이 뭐야?'가 dev_multi에 있었음)"""
    out = set()
    for path in sorted((ROOT / "data" / "tests").glob("dev_*.csv")):
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = [c for c in (reader.fieldnames or []) if "질문" in c]
            for row in reader:
                for c in cols:
                    v = (row.get(c) or "").strip()
                    if v:
                        out.add(core(v))
    return out


def free_candidates(new, tests):
    """사전에 있는 말로 "○○가 뭐야?"를 만들어, 측정용·기존 개발용·새 문항 어디에도 없는 것만 적는다 (문항을 바꿀 때 쓴다).

    끝말을 뺀 앞부분으로 비교하므로 "○○가 무슨 뜻이야?"로 들어 있는 말도 빠진다. 측정용 문장은 적지 않는다.
    """
    dev = load_dev_cores()
    if not dev:
        print("\n[주의] 기존 개발용 문항(data/tests/dev_*.csv)을 읽지 못해 후보에서 빼지 못했다")
    used = {t["c"] for t in tests} | {core(x["질문"]) for x in new} | dev
    words = []
    for name, col in (("nonstandard.csv", "비표준표현"), ("standard_terms.csv", "표준용어")):
        with open(ROOT / "data" / "dictionary" / name, encoding="utf-8-sig", newline="") as f:
            words += [(r.get(col) or "").strip() for r in csv.DictReader(f)]
    free = []
    for w in words:
        if not w or " " in w or len(w) > 6:
            continue
        last = w[-1]
        josa = "이" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "가"
        q = f"{w}{josa} 뭐야?"
        if core(q) not in used and norm(w) not in used:
            free.append(q)
    print(f"\n[바꿀 때 쓸 수 있는 후보] 측정용·기존 개발용·새 문항 어디에도 없는 것 {len(free)}개")
    print("  " + " / ".join(free))


def main():
    new, tests = load_new(), load_tests()
    if not new or not tests:
        print("새 문항이나 측정용 문항을 읽지 못했다. 위 메시지를 확인한다.")
        sys.exit(1)
    by_n, by_c = {}, {}
    for t in tests:
        by_n.setdefault(t["n"], []).append(t)
        by_c.setdefault(t["c"], []).append(t)
    rows, seen = [], set()
    for it in new:
        n, c = norm(it["질문"]), core(it["질문"])
        kind, hits = "", []
        if n in by_n:
            kind, hits = "같은 문장", by_n[n]
        elif len(c) >= 2 and c in by_c:
            kind, hits = "앞부분 같음", by_c[c]
        else:
            hits = [t for t in tests if share8(c, t["c"])]
            kind = "8자 겹침 (참고)" if hits else ""
        if not kind:
            continue
        key = (it["세트"], it["id"])
        if key in seen:
            continue
        seen.add(key)
        where = ", ".join(dict.fromkeys(f"{t['파일']} {t['줄']}줄" for t in hits))
        rows.append({**it, "겹침": kind, "측정용 위치": where})

    order = {"같은 문장": 0, "앞부분 같음": 1, "8자 겹침 (참고)": 2}
    rows.sort(key=lambda r: (r["세트"], order[r["겹침"]], str(r["id"])))
    print(f"새 문항 {len(new)}개 (개발용 {sum(1 for x in new if x['세트'] == '개발용')}, "
          f"홀드아웃 {sum(1 for x in new if x['세트'] == '홀드아웃')}) · 측정용 질문 {len(tests)}개와 비교\n")
    for set_name in ("개발용", "홀드아웃"):
        part = [r for r in rows if r["세트"] == set_name]
        print(f"[{set_name}] 같은 문장 {sum(1 for r in part if r['겹침'] == '같은 문장')} · "
              f"앞부분 같음 {sum(1 for r in part if r['겹침'] == '앞부분 같음')} · "
              f"8자 겹침(참고) {sum(1 for r in part if r['겹침'].startswith('8자'))}")
        for r in part:
            print(f"  {r['겹침']} · {r['id']} ({r['경우']}, {r['시트']}) · {r['질문']} · {r['측정용 위치']}")
        print()
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"overlap_4th_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["세트", "겹침", "id", "경우", "시트", "질문", "측정용 위치"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"결과 파일: {out.relative_to(ROOT)}")
    free_candidates(new, tests)
    print("같은 문장과 앞부분 같음으로 나온 번호를 Claude에게 알려 주면 그 문항만 다른 문장으로 바꾼다.")


if __name__ == "__main__":
    main()
