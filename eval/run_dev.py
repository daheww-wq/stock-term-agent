"""개발용 21개(단발 13 + 멀티턴 8건) 실행. --set test 를 주면 측정용 문항을 실행한다 (측정 시점에만).

실행 (stock-term-agent 폴더에서, 가상환경 켠 뒤)
  python eval/run_dev.py --ids D01                 # 개발용 1번 문항 하나만 (처음엔 이것부터)
  python eval/run_dev.py --ids D01,D07,DM2         # 몇 개만 골라서
  python eval/run_dev.py                           # 개발용 21개 전부, 설정 C
  python eval/run_dev.py --mode A                  # 설정 A(정규화 없음)로
  python eval/run_dev.py --modes A B C             # 같은 문항을 설정 A·B·C로 차례로 (3단 실험)
  python eval/run_dev.py --set test --modes D --dataset-run 2차  # 설정 D(사전 우선+필요 시 LLM)만 측정용으로, 2차 결과와 나란히 (P-042)
  python eval/run_dev.py --set test --modes B C D --ids S17,M14,M16 --repeat 5  # 같은 문항을 5번씩 돌려 흔들림 재기 (P-046)
  python eval/run_dev.py --set test --modes A B C  # 측정용(단발 49 + 멀티턴 15건, 2차 변형 포함)을 A·B·C로 = 2차 측정 (1차는 단발 41 + 멀티턴 13건)
  python eval/run_dev.py --set test --modes A B C --dataset-run 2차   # 랭퓨즈 Dataset 실행 "2차-A/B/C"로 연결 (P-029)
                                                                    # + 끝나면 검토 대기열 "2차 측정 검토" 자동 생성 (P-030)
  python eval/run_dev.py --only single             # 단발만 (multi: 멀티턴만)
  python eval/run_dev.py --model openai/gpt-6-luna # 다른 모델로
  python eval/run_dev.py --set test --modes D --repeat 3 --node-models "n0,n2,n3,n5=openai/gpt-6-luna" --fast-path
                                                   # 3차 개선 D: 검수(n6)만 --model(기본 gemini), 나머지 노드는 luna (P-061) + 규칙 분류 (P-062)
  python eval/run_dev.py --no-langfuse             # 랭퓨즈 기록 없이
  python eval/run_dev.py --dry-run                 # LLM 없이 노드 1(사전 정규화) 결과만 확인 (비용 0)
  python eval/run_dev.py --no-judge                # 사전 밖 용어 LLM 채점 없이 (채점 비용 0)

결과: results/<dev|test>_<설정>_<모델>_<시각>.xlsx  (실행 한 번에 파일 하나)
- 탭: 요약(설정별 단발·멀티턴) · 비교(설정별로 세트·슬랭 유형·RQ1 구분·관용구 패턴 사전 안/밖 등으로 나눠 봄)
  · 단발 · 멀티턴 (설정이 여러 개면 단발_A, 멀티턴_A …)
- 의도_일치, 재구성_일치는 자동 채점. 풀이_자동은 대략 확인용(정답 표현이 풀렸는지만 봄)
- "사전 근거 없음"으로 나간 답변은 채점용 모델(JUDGE_MODEL)이 뜻 일치·틀린 사실·눈높이를 1차 채점하고, 근거 없음 표시는 코드로 확인한다 (eval/judge.py). 본인이 전수 확인한다
- 답변 품질·근거 일치·컴플라이언스 정답 여부는 결과 파일을 보고 판단한다
- --dataset-run 을 주면 측정이 끝난 뒤 랭퓨즈 대기열 "<이름> 측정 검토"를 만든다 (P-030, eval/review_queue.py).
  꼭 확인(의도 불일치·재구성 글자 다름·LLM 채점 0점·오류·용어 보정 작동)을 앞에, LLM이 채점한 나머지를 뒤에 넣는다
- --dataset-run 을 주면 측정 전에 prompts/ 지침을 랭퓨즈 Prompts에 맞춰 올리고, LLM 호출마다 지침 버전을 연결한다 (P-031)

채점 규칙 (P-026)
- 허용_의도: 의도 정답 외에 정답으로 인정하는 의도. 맞으면 1, 의도_채점메모에 "허용 의도(안전 쪽)"
- 되묻기가 정답인 문항을 설정 A·B로 돌리면 되묻기 단계(노드 2)가 없으므로 (C·D는 있음) 의도 정답으로 채점하고 메모를 남긴다
- 측정용은 사전 밖 채점에 평가용 정답(test_사전밖_평가용정답.md)을 함께 넘긴다. 에이전트에는 주지 않는다
- 문항에 풀이_정답이 있으면 평가용 정답이 없는 용어에 "정답지 풀이: …"로 함께 넘긴다 (P-039)

측정용 문항(test_*.csv)은 --set test 를 줄 때만 읽는다. 측정 시점 전에는 쓰지 않는다.
검수 노드 검증셋(test_compliance.csv)은 eval/run_compliance.py가 따로 돌린다.
"""
import argparse
import csv
import datetime as dt
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TESTS = ROOT / "data" / "tests"
OUT_DIR = ROOT / "results"
SETS = {"dev": ("dev_single.csv", "dev_multi.csv", "개발용"),
        "test": ("test_single.csv", "test_multi.csv", "측정용")}
REFERENCE_FILE = "test_사전밖_평가용정답.md"
# 랭퓨즈 Dataset (P-029, scripts/langfuse_setup.py가 만든다). 문항 id를 고정해 실행 결과를 같은 문항에 연결한다
DATASET_SINGLE = "stock-term-test-single"
DATASET_MULTI = "stock-term-test-multi"
# 실험 설정 (src/config.py MODES·ASK_MODES와 같게 둔다. --dry-run은 .env를 읽는 config를 불러오지 않아 여기 따로 둠, P-042)
MODE_CHOICES = ["A", "B", "C", "D"]
ASK_MODES = ("C", "D")  # 되묻기(노드 9)까지 갈 수 있는 설정


def single_item_id(item_id: str) -> str:
    return f"stk-test-single-{item_id}"


def multi_item_id(scenario: str, turn) -> str:
    return f"stk-test-multi-{scenario}-t{turn}"


def read_csv(name):
    with open(TESTS / name, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def expected_intent(row):
    """'범위 밖(불법·유해)' 같은 표기를 (의도, 사유)로 나눈다."""
    raw = (row.get("의도_정답") or "").strip()
    reason = (row.get("범위밖_사유") or "").strip()
    if raw.startswith("범위 밖") and "(" in raw:
        reason = raw[raw.find("(") + 1: raw.rfind(")")]
        raw = "범위 밖"
    return raw, reason


def norm_check(expected: str, norm_log: list) -> str:
    """풀이_정답의 표현들이 norm_log에서 풀렸는지 대략 센다. 예: '2/2'"""
    if not expected.strip():
        return ""
    items = [x.strip() for x in expected.replace(" · ", "·").split("·") if x.strip()]
    exprs = [x["expr"] for x in norm_log if x.get("status") != "되묻기"]
    hit = 0
    for item in items:
        left = item.split("=")[0].split("→")[0].strip()
        if any(left in e or e in left for e in exprs):
            hit += 1
    return f"{hit}/{len(items)}"


def _same_intent(s, intent, reason):
    return s["의도_결과"] == intent and (intent != "범위 밖" or s["범위밖_사유_결과"] == reason)


def _split_intents(allowed: str) -> list:
    """'매매 판단 요청, 범위 밖(일반)' → [('매매 판단 요청', ''), ('범위 밖', '일반')]"""
    out = []
    for x in (allowed or "").replace("·", ",").split(","):
        x = x.strip()
        if x:
            out.append(expected_intent({"의도_정답": x}))
    return out


def intent_check(s, exp_intent, exp_reason, expected_action, mode="C", allowed=""):
    """의도 채점. (일치 0/1, 메모)를 돌려준다.

    - 되묻기(9)로 끝난 턴은 의도 분류를 거치지 않으므로, 기대 행동이 되묻기였는지로 본다 (P-006)
    - 되묻기는 노드 2가 있는 설정(C·D)에서만 동작한다. 되묻기가 정답인 문항을 A·B로 돌리면 의도 정답으로 채점한다 (P-026, P-042)
    - 허용_의도로 맞히면 정답으로 치고 메모를 남긴다 (P-026)
    - 기대 행동이 "단정하지 않는다: 되묻거나, 추정임을 밝히고 맞는지 확인한다"(가상 신조어, P-054)이면
      되물었으면 정답, 답했으면 의도로 채점한다. 단정했는지(지어냈는지)는 사전 밖 채점(되물음·틀린 사실)이 본다
    """
    asked = "9 되묻기" in s["경로"]
    if "추정임을 밝히고" in (expected_action or ""):
        if asked:
            return 1, "단정하지 않음 문항: 되물음"
        return int(_same_intent(s, exp_intent, exp_reason)), "단정하지 않음 문항: 의도로 채점, 단정 여부는 사전 밖 채점"
    expect_ask = "되묻는다" in (expected_action or "")
    if expect_ask and mode not in ASK_MODES:
        return int(_same_intent(s, exp_intent, exp_reason)), "A·B 되묻기 문항: 의도로 채점"
    if asked or expect_ask:
        return int(asked and expect_ask), ""
    if _same_intent(s, exp_intent, exp_reason):
        return 1, ""
    for it, rs in _split_intents(allowed):
        if _same_intent(s, it, rs):
            return 1, "허용 의도(안전 쪽)"
    return 0, ""


def intent_match(s, exp_intent, exp_reason, expected_action):
    """예전 이름 (설정 C, 허용 의도 없음). 오프라인 점검 호환용."""
    return intent_check(s, exp_intent, exp_reason, expected_action)[0]


def load_references() -> dict:
    """사전 밖 평가용 정답: '- 용어: 설명' 줄을 {용어: 설명}으로. 측정용에서만 쓰고 에이전트에는 주지 않는다."""
    path = TESTS / REFERENCE_FILE
    if not path.exists():
        return {}
    refs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            term, desc = line[2:].split(":", 1)
            refs[term.strip()] = desc.strip()
    return refs


def references_for(terms: list, refs: dict) -> dict:
    """에이전트가 뽑은 용어 이름이 정답 파일 이름과 조금 달라도(횡보하다 ↔ 횡보) 연결한다."""
    out = {}
    for t in terms:
        key = "".join(t.split()).lower()
        for name, desc in refs.items():
            k = "".join(name.split()).lower()
            if k and (k in key or key in k):
                out[t] = desc
                break
    return out


def judge_references(terms: list, refs: dict, row: dict) -> dict:
    """사전 밖 채점에 넘길 평가용 정답. 평가용 정답 파일에 있는 것 우선, 없으면 문항의 풀이_정답 (P-039)
    줄임말·오타처럼 정답이 있는데 채점 모델이 "확립 안 된 말을 단정했다"고 깎지 않게 한다"""
    out = dict(references_for(terms, refs) or {})
    key = (row.get("풀이_정답") or "").strip()
    if key:
        for t in terms:
            out.setdefault(t, f"정답지 풀이: {key}")
    return out


def normalization_text(state) -> str:
    """사전 밖 채점에 넘길 질문 속 표현 풀이 (P-051). 결과 칸 풀이_결과와 같은 글"""
    return " · ".join(x["annotation"] or f"{x['expr']}(되묻기)" for x in state.get("norm_log") or [])


def answered(state) -> bool:
    """이번 턴에 답변(노드 5)을 만들었는가. 되묻기·범위 밖으로 끝난 턴은 사전 근거 없이 '답한' 것이 아니다 (P-043)"""
    return any(str(p).startswith("5 답변") for p in state.get("path") or [])


def unknown_terms(state):
    """사전에 없던 용어 (사전 밖 채점 대상). 답변을 만들지 않은 턴은 빈 목록 (P-043: 설정 D는 조회 후 되묻기로 끝날 수 있음)"""
    if not answered(state):
        return []
    return [t["term"] for t in state.get("term_info") or [] if not t["found"]]


def summarize(state):
    norm_log = state.get("norm_log") or []
    info = state.get("term_info") or []
    usage = state.get("usage") or []
    costs = [u["cost_usd"] for u in usage if u.get("cost_usd") is not None]
    comp = state.get("compliance_history") or []
    return {
        "재구성_결과": state.get("rewritten_query", ""),
        "풀이_결과": normalization_text(state),
        "되묻기_대상": " · ".join(u["expr"] for u in state.get("unresolved") or []),
        "오타_확인": " · ".join(f"{t['typo']}→{t['original']}" for t in state.get("typo_confirm") or []),
        "의도_결과": state.get("intent", ""),
        "범위밖_사유_결과": state.get("out_reason", ""),
        "분류_근거": state.get("intent_reason", ""),
        "terms": " · ".join(state.get("terms") or []),
        "용어_보정": " · ".join(state.get("term_fixes") or []),
        "안전망_작동": state.get("intent_override", ""),
        "종목": state.get("ticker", ""),
        "조회_적중": f"{sum(1 for t in info if t['found'])}/{len(info)}" if info else "",
        "사전_근거_없음": " · ".join(unknown_terms(state)),
        "짐작_확인": "예" if state.get("guess_confirm") else "",
        "가까운_표준용어": " · ".join(f"{n['term']}→{n['standard']}" for n in state.get("near_terms") or []),
        "관련용어_안내": " · ".join(
            f"{t}({'넣음' if (t in (state.get('final_answer') or '') and '궁금하면' in (state.get('final_answer') or '')) else '안 넣음'})"
            for t in state.get("related_terms") or []),
        "검수_판정": " → ".join(c["verdict"] for c in comp),
        "검수_위반": " | ".join(f"{v.get('item')}: {v.get('sentence')}" for c in comp for v in c.get("violations", [])),
        "재생성_횟수": state.get("retry_count", 0),
        "경로": " → ".join(state.get("path") or []),
        "최종_답변": state.get("final_answer", ""),
        "LLM_호출": len(usage),
        "노드별_시간": " · ".join(f"{u['node'].split('_')[0]} {u['sec']}초" for u in usage),
        "사용_모델": " · ".join(sorted({str(u.get("model")) for u in usage})) if usage else "",
        "노드별_출력토큰": " · ".join(f"{u['node'].split('_')[0]} {u['output_tokens']}" for u in usage),
        "비용_USD": round(sum(costs), 6) if costs else "",
        "응답_초": state.get("_latency_sec", ""),
        "대기_초": state.get("_wait_sec", ""),
        "오류": " | ".join(state.get("errors") or []),
        "_usage": usage,
    }


LONG_COLS = {"사전밖_채점메모": 50, "질문": 30, "기대_행동": 40, "최종_답변": 70, "풀이_결과": 40, "경로": 50,
             "검수_위반": 40, "분류_근거": 35, "오류": 40, "재구성_결과": 30, "재구성_정답": 30,
             "노드별_시간": 40, "노드별_출력토큰": 35, "확인_포인트": 25, "풀이_정답": 35, "의도_채점메모": 22}


def _clean(rows):
    """엑셀·CSV에 쓸 칸만 남긴다 (_로 시작하는 내부 칸 제외)."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def _ratio(rows, key):
    done = [r for r in rows if key in r]
    return f"{sum(int(r[key]) for r in done)}/{len(done)}" if done else ""


def _stats(rows):
    """한 설정의 단발 또는 멀티턴 결과를 요약 지표로."""
    done = [r for r in rows if "의도_일치" in r]
    if not rows:
        return {}
    hit = tot = 0
    for r in done:
        if r.get("조회_적중"):
            a, b = r["조회_적중"].split("/")
            hit, tot = hit + int(a), tot + int(b)
    costs = [r["비용_USD"] for r in done if r.get("비용_USD") not in ("", None)]
    secs = [r["응답_초"] for r in done if r.get("응답_초") not in ("", None)]
    node_sec = {}
    for r in done:
        for u in r.get("_usage", []):
            node_sec.setdefault(u["node"], []).append(u["sec"])
    return {
        "실행 문항(턴) 수": len(rows),
        "오류": len(rows) - len(done),
        "의도 일치": _ratio(done, "의도_일치"),
        "  허용 의도(안전 쪽)로 맞힘": sum(1 for r in done if r.get("의도_채점메모") == "허용 의도(안전 쪽)"),
        "  A·B 되묻기 문항(의도로 채점)": sum(1 for r in done if (r.get("의도_채점메모") or "").startswith("A·B 되묻기")),
        "재구성 일치": _ratio(done, "재구성_일치"),
        "풀이 정답 모두 풀림": _ratio([r for r in done if r.get("풀이_자동")], "_풀이_완전"),
        "조회 적중 (용어 수)": f"{hit}/{tot}" if tot else "",
        "사전 근거 없이 답한 용어": sum(1 for r in done if r.get("사전_근거_없음")),
        "용어 보정 작동 (P-027)": sum(1 for r in done if r.get("용어_보정")),
        "매매 판단 안전망 작동 (P-044)": sum(1 for r in done if r.get("안전망_작동")),
        "규칙 분류로 노드 3 생략 (P-062)": sum(1 for r in done if "3 의도 분류(규칙)" in r.get("경로", "")),
        "출력 상한에 걸림 (P-028)": sum(1 for r in done if "출력 상한" in (r.get("오류") or "")),
        "되묻기로 끝남": sum(1 for r in done if "9 되묻기" in r.get("경로", "")),
        "짐작 + 확인 질문으로 답함 (P-056)": sum(1 for r in done if r.get("짐작_확인")),
        "가까운 표준 용어 함께 조회 (P-056)": sum(1 for r in done if r.get("가까운_표준용어")),
        "범위 밖 안내로 끝남": sum(1 for r in done if "8 범위 밖" in r.get("경로", "")),
        "오타 확인 문구 대상": sum(1 for r in done if r.get("오타_확인")),
        "관련 용어 안내 (후보 → 넣음)": f"{sum(1 for r in done if r.get('관련용어_안내'))} → {sum(1 for r in done if '(넣음)' in (r.get('관련용어_안내') or ''))}",
        "검수 첫 판정 위반": sum(1 for r in done if str(r.get("검수_판정", "")).startswith("위반")),
        "재생성 횟수 합계": sum(int(r.get("재생성_횟수") or 0) for r in done),
        "안전 답변 도달": sum(1 for r in done if "7 안전 답변" in r.get("경로", "")),
        "사전 밖 채점: 뜻 일치": _ratio([r for r in done if r.get("사전밖_뜻일치") != "" and "사전밖_뜻일치" in r], "사전밖_뜻일치"),
        "사전 밖 채점: 틀린 사실 없음": _ratio([r for r in done if r.get("사전밖_틀린사실없음") != "" and "사전밖_틀린사실없음" in r], "사전밖_틀린사실없음"),
        "사전 밖 채점: 근거 없음 표시": _ratio([r for r in done if r.get("사전밖_표시") != "" and "사전밖_표시" in r], "사전밖_표시"),
        "사전 밖 채점: 눈높이": _ratio([r for r in done if r.get("사전밖_눈높이") != "" and "사전밖_눈높이" in r], "사전밖_눈높이"),
        "사전 밖 채점: 되물어 뜻 해당 없음 (P-051)": sum(1 for r in done if r.get("사전밖_되물음")),
        "사전 밖 채점: 되물으며 조건부 표준 용어 안내 (P-055)": sum(1 for r in done if r.get("사전밖_조건부안내")),
        "비용 합계 USD": round(sum(costs), 4) if costs else "",
        "채점 비용 USD": round(sum(r["채점_비용_USD"] for r in done if r.get("채점_비용_USD") not in ("", None)), 4),
        "평균 응답 초": round(sum(secs) / len(secs), 1) if secs else "",
        "호출 간격 대기 합계 초 (응답 초에서 뺌)": round(sum(r.get("대기_초") or 0 for r in done), 1),
        **{f"평균 초 · {n}": round(sum(v) / len(v), 2) for n, v in sorted(node_sec.items())},
    }


def build_summary(meta, results):
    """요약 탭 내용. results = {설정: (단발 결과, 멀티턴 결과)}. 열: 항목 · 설정별 단발 · 설정별 멀티턴."""
    stats = {m: (_stats(s), _stats(mm)) for m, (s, mm) in results.items()}
    head = ["항목"]
    for m in results:
        head += [f"{m} 단발", f"{m} 멀티턴"]
    lines = [(k, v) for k, v in meta.items()] + [("",), tuple(head)]
    keys = list(dict.fromkeys(k for a, b in stats.values() for k in list(a) + list(b)))
    keys = [k for k in keys if not k.startswith("평균 초 ·")] + sorted(k for k in keys if k.startswith("평균 초 ·"))
    for k in keys:
        row = [k]
        for a, b in stats.values():
            row += [a.get(k, ""), b.get(k, "")]
        lines.append(tuple(row))
    return lines


def _slang_kind(value: str) -> str:
    v = (value or "").strip()
    for k in ("용어 슬랭", "종목 약어", "오타", "관용구"):
        if v.startswith(k):
            return k
    return "없음" if v.startswith("없음") or not v else "기타"


def _rq1_kind(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith("모름"):
        return "모름"
    if v.startswith("앎"):
        return "앎"
    return "기타(" + v + ")"


COMPARE_GROUPS = [
    ("전체", lambda r: "전체"),
    ("세트", lambda r: r.get("세트", "")),
    ("의도 정답", lambda r: r.get("의도_정답", "")),
    ("하위구분", lambda r: r.get("하위구분", "")),
    ("슬랭 유형", lambda r: _slang_kind(r.get("슬랭_유형", ""))),
    ("RQ1 (LLM이 아는 표현인가)", lambda r: _rq1_kind(r.get("RQ1_구분", ""))),
    ("관용구 패턴 사전", lambda r: r.get("관용구_패턴사전", "")),
]


def _group_metrics(rows):
    done = [r for r in rows if "의도_일치" in r]
    hit = tot = 0
    for r in done:
        if r.get("조회_적중"):
            a, b = r["조회_적중"].split("/")
            hit, tot = hit + int(a), tot + int(b)
    costs = [r["비용_USD"] for r in done if r.get("비용_USD") not in ("", None)]
    secs = [r["응답_초"] for r in done if r.get("응답_초") not in ("", None)]
    return {
        "의도 일치": _ratio(done, "의도_일치"),
        "풀이 정답 모두 풀림": _ratio([r for r in done if r.get("풀이_자동")], "_풀이_완전"),
        "조회 적중 (용어 수)": f"{hit}/{tot}" if tot else "",
        "사전 근거 없이 답한 문항": sum(1 for r in done if r.get("사전_근거_없음")),
        "검수 첫 판정 위반": sum(1 for r in done if str(r.get("검수_판정", "")).startswith("위반")),
        "문항당 비용 USD": round(sum(costs) / len(costs), 4) if costs else "",
        "평균 응답 초": round(sum(secs) / len(secs), 1) if secs else "",
    }


def _item_key(r):
    return r.get("id") or f"{r.get('시나리오')}-{r.get('턴')}"


def common_lookup(results):
    """조회 적중을 설정끼리 같은 분모로 비교 (P-041).

    설정마다 조회한 문항이 다르다(C는 되묻기·범위 밖으로 멈춰 조회를 건너뛰기도 하고, B·C는 종목 약어를 종목명으로 풀어
    용어 조회를 안 하기도 한다). 그래서 단발+멀티턴을 합쳐 '모든 설정이 조회한 문항'만으로 조회 적중과 사전 근거 없이 답한
    용어를 다시 센다. 다른 설정은 조회했는데 이 설정은 되묻기·범위 밖으로 끝나 조회하지 않은 문항 수도 함께 돌려준다.
    돌려주는 값: (공통 문항 수, {설정: {"조회 적중": "h/t", "사전 근거 없이 답한 용어": t-h, "조회 전에 멈춤": n}})
    """
    rows = {m: {_item_key(r): r for r in s + mm if "의도_일치" in r} for m, (s, mm) in results.items()}
    modes = list(rows)
    keys = [k for k in rows[modes[0]] if all(rows[m].get(k, {}).get("조회_적중") for m in modes)]
    out = {}
    for m in modes:
        hit = tot = 0
        for k in keys:
            a, b = rows[m][k]["조회_적중"].split("/")
            hit, tot = hit + int(a), tot + int(b)
        stopped = sum(1 for k, r in rows[m].items()
                      if not r.get("조회_적중") and any(rows[o].get(k, {}).get("조회_적중") for o in modes if o != m)
                      and ("9 되묻기" in r.get("경로", "") or "8 범위 밖" in r.get("경로", "")))
        out[m] = {"조회 적중": f"{hit}/{tot}" if tot else "", "사전 근거 없이 답한 용어": tot - hit, "조회 전에 멈춤": stopped}
    return len(keys), out


def build_compare(results):
    """비교 탭: 단발을 묶음별로 나눠 설정끼리 나란히 본다 (RQ2). 멀티턴은 전체만."""
    modes = list(results)
    lines = [("구분", "묶음", "문항 수", "지표", *modes)]
    first = next(iter(results.values()))
    for gname, fn in COMPARE_GROUPS:
        groups = list(dict.fromkeys(fn(r) for r in first[0] if fn(r)))
        for g in groups:
            per_mode = {m: _group_metrics([r for r in results[m][0] if fn(r) == g]) for m in modes}
            n = sum(1 for r in first[0] if fn(r) == g)
            for metric in per_mode[modes[0]]:
                lines.append((f"단발 · {gname}", g, n, metric, *[per_mode[m][metric] for m in modes]))
    if first[1]:
        per_mode = {m: {**_group_metrics(results[m][1]), "재구성 일치": _ratio([r for r in results[m][1] if "의도_일치" in r], "재구성_일치")}
                    for m in modes}
        for metric in per_mode[modes[0]]:
            lines.append(("멀티턴", "전체", len(first[1]), metric, *[per_mode[m][metric] for m in modes]))
    if len(modes) > 1:  # 같은 분모로 비교 (P-041)
        n, cl = common_lookup(results)
        g = "모든 설정이 조회한 문항"
        lines.append(("단발+멀티턴 · 같은 분모", g, n, "조회 적중 (용어 수)", *[cl[m]["조회 적중"] for m in modes]))
        lines.append(("단발+멀티턴 · 같은 분모", g, n, "사전 근거 없이 답한 용어", *[cl[m]["사전 근거 없이 답한 용어"] for m in modes]))
        lines.append(("단발+멀티턴 · 같은 분모", "다른 설정은 조회했는데 되묻기·범위 밖으로 끝남", "", "조회 전에 멈춤 (문항)",
                      *[cl[m]["조회 전에 멈춤"] for m in modes]))
    return lines


def _ending(r):
    """턴이 어떻게 끝났나: 답변 / 되묻기 / 범위 밖 / 안전 답변 / 오류"""
    path = r.get("경로", "")
    if "9 되묻기" in path:
        return "되묻기"
    if "8 범위 밖" in path:
        return "범위 밖"
    if "7 안전 답변" in path:
        return "안전 답변"
    return "답변" if path else "오류"


def build_repeat(runs):
    """반복 탭 (P-046): 같은 문항을 같은 설정으로 여러 번 돌렸을 때 결과가 얼마나 같은지.

    runs = {설정: [(단발 결과, 멀티턴 결과), ...]} (반복 순서대로). 문항마다 의도 일치 횟수, 의도·끝 경로가
    가장 많이 나온 값과 그 비율, 안전망·노드 2 경유 횟수를 적고, 한 번이라도 결과가 달랐으면 '흔들림'으로 표시한다.
    """
    lines = [("설정", "문항", "질문", "반복", "의도 일치", "의도 (가장 많음)", "끝 (가장 많음)", "안전망 작동", "노드 2 경유", "흔들림")]
    summary = {}
    for m, reps in runs.items():
        n = len(reps)
        per = {}
        for s_rows, m_rows in reps:
            for r in s_rows + m_rows:
                per.setdefault(_item_key(r), []).append(r)
        shaky = 0
        for k, rows in per.items():
            done = [r for r in rows if "의도_일치" in r]
            intents = [r.get("의도_결과") or _ending(r) for r in rows]
            ends = [_ending(r) for r in rows]
            top_i = max(set(intents), key=intents.count)
            top_e = max(set(ends), key=ends.count)
            unstable = len(set(intents)) > 1 or len(set(ends)) > 1
            shaky += unstable
            lines.append((m, k, rows[0].get("질문", ""), n, f"{sum(int(r['의도_일치']) for r in done)}/{n}",
                          f"{top_i} ({intents.count(top_i)}/{n})", f"{top_e} ({ends.count(top_e)}/{n})",
                          f"{sum(1 for r in rows if r.get('안전망_작동'))}/{n}",
                          f"{sum(1 for r in rows if '2 LLM 정규화' in r.get('경로', ''))}/{n}", "흔들림" if unstable else ""))
        summary[m] = (shaky, len(per))
    return lines, summary


def save_results(path_base, meta, results, repeat=None):
    """실행 한 번의 결과를 파일 하나로 저장. openpyxl이 있으면 엑셀, 없으면 CSV 하나.
    results = {설정: (단발 결과, 멀티턴 결과)}"""
    summary = build_summary(meta, results)
    compare = build_compare(results)
    multi_mode = len(results) > 1
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        out = path_base.parent / (path_base.name + ".csv")
        rows = []
        for m, (s_rows, m_rows) in results.items():
            rows += [{"설정": m, "구분": "단발", **r} for r in _clean(s_rows)]
            rows += [{"설정": m, "구분": "멀티턴", **r} for r in _clean(m_rows)]
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print("(openpyxl이 없어 CSV 하나로 저장했어요. pip install -r requirements.txt 하면 엑셀로 저장돼요)")
        return out, summary

    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E8E6F8")
    miss_fill = PatternFill("solid", fgColor="FBE3E3")
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    for line in summary:
        ws.append(list(line))
    for row in ws.iter_rows():
        if row[0].value in ("항목",):
            for c in row:
                c.font, c.fill = head_font, head_fill
    ws.column_dimensions["A"].width = 34
    for i in range(2, 2 + 2 * len(results)):
        ws.column_dimensions[get_column_letter(i)].width = 16

    if repeat:  # 반복 탭 (P-046)
        rs = wb.create_sheet("반복")
        for line in repeat:
            rs.append(list(line))
        for c in rs[1]:
            c.font, c.fill = head_font, head_fill
        for col, w in zip("ABCDEFGHIJ", (6, 10, 40, 6, 10, 22, 16, 10, 10, 8)):
            rs.column_dimensions[col].width = w
        rs.freeze_panes = "C2"

    if multi_mode or any(r[0] for r in results.values()):
        cs = wb.create_sheet("비교")
        for line in compare:
            cs.append(list(line))
        for c in cs[1]:
            c.font, c.fill = head_font, head_fill
        for col, w in zip("ABCD", (26, 30, 9, 22)):
            cs.column_dimensions[col].width = w
        cs.freeze_panes = "E2"

    for m, (s_rows, m_rows) in results.items():
        for title, rows in (("단발", s_rows), ("멀티턴", m_rows)):
            if not rows:
                continue
            rows = _clean(rows)
            keys = list(dict.fromkeys(k for r in rows for k in r))
            sh = wb.create_sheet(f"{title}_{m}" if multi_mode else title)
            sh.append(keys)
            for r in rows:
                sh.append([r.get(k, "") for k in keys])
            for c in sh[1]:
                c.font, c.fill = head_font, head_fill
            sh.freeze_panes = "C2"
            for i, k in enumerate(keys, 1):
                sh.column_dimensions[get_column_letter(i)].width = LONG_COLS.get(k, 12)
            for row in sh.iter_rows(min_row=2):
                for c in row:
                    c.alignment = wrap
                for c in row:
                    col = keys[c.column - 1]
                    if col in ("의도_일치", "재구성_일치", "사전밖_뜻일치", "사전밖_틀린사실없음", "사전밖_표시", "사전밖_눈높이") and str(c.value) == "0":
                        c.fill = miss_fill
                    if col == "오류" and c.value:
                        c.fill = miss_fill

    out = path_base.parent / (path_base.name + ".xlsx")
    wb.save(out)
    return out, summary


def dry_run(single, multi):
    from src.dictionary import dict_normalize, render_annotation
    print("LLM 없이 노드 1(사전 정규화) 결과만 봅니다. 멀티턴은 재구성 전 원문 기준입니다.\n")
    for r in single:
        q = r["질문"]
        res = dict_normalize(q)
        print(f"{r['id']:5} {render_annotation(q, res.norm_log)}")
        extra = []
        if res.typo_confirm:
            extra.append(f"오타 확인: {res.typo_confirm}")
        if res.unresolved:
            extra.append(f"되묻기: {res.unresolved}")
        extra.append(f"정답: {r.get('풀이_정답') or '(없음)'}")
        print("      " + " / ".join(extra))
    for r in multi:
        q = r["질문"]
        res = dict_normalize(q)
        print(f"{r['시나리오']}-{r['턴']} {render_annotation(q, res.norm_log)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev", choices=list(SETS), help="dev: 개발용(기본), test: 측정용 (측정 시점에만)")
    ap.add_argument("--mode", default="C", choices=MODE_CHOICES)
    ap.add_argument("--modes", nargs="+", choices=MODE_CHOICES, help="여러 설정을 차례로 (예: --modes A B C). 주면 --mode는 무시")
    ap.add_argument("--ids", help="쉼표로 구분한 문항 id (단발 D01·S01, 멀티턴 시나리오 DM1·M1)")
    ap.add_argument("--only", choices=["single", "multi"])
    ap.add_argument("--model", help="에이전트 모델 ID. 생략하면 .env의 AGENT_MODEL")
    ap.add_argument("--node-models", help='노드별 모델 (P-061). 예: "n0,n2,n3,n5=openai/gpt-6-luna" (나머지 노드는 --model). 노드는 n0·n2·n3·n5·n6')
    ap.add_argument("--fast-path", action="store_true", help="규칙 분류 켜기 (P-062): 뜻만 묻는 단순 질문 + 사전 용어는 노드 3 LLM 없이")
    ap.add_argument("--no-langfuse", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-judge", action="store_true", help="사전 밖 용어 LLM 채점을 하지 않음")
    ap.add_argument("--judge-model", help="사전 밖 채점 모델 ID (P-064). 생략하면 .env의 JUDGE_MODEL")
    ap.add_argument("--repeat", type=int, default=1,
                    help="같은 문항을 같은 설정으로 몇 번 돌릴지 (P-046). 2 이상이면 결과 엑셀에 '반복' 탭. 요약·비교는 첫 번째 결과, 사전 밖 채점도 첫 번째만")
    ap.add_argument("--dataset-run", help="측정용(--set test)일 때 랭퓨즈 Dataset 실행 이름 접두어 (예: 2차 → 2차-A, 2차-B, 2차-C)")
    args = ap.parse_args()
    if args.repeat < 1:
        sys.exit("--repeat 은 1 이상입니다.")
    if args.dataset_run and args.repeat > 1:
        sys.exit("--repeat 과 --dataset-run 은 함께 쓰지 않습니다 (같은 문항이 Dataset 실행에 여러 번 연결되므로).")
    if args.dataset_run and args.set != "test":
        sys.exit("--dataset-run 은 --set test 와 함께 씁니다.")
    modes = list(dict.fromkeys(args.modes or [args.mode]))
    single_file, multi_file, set_label = SETS[args.set]

    single = read_csv(single_file) if args.only != "multi" else []
    multi = read_csv(multi_file) if args.only != "single" else []
    if args.ids:
        keep = {x.strip() for x in args.ids.split(",") if x.strip()}
        single = [r for r in single if r["id"] in keep]
        multi = [r for r in multi if r["시나리오"] in keep]
    if not single and not multi:
        sys.exit("실행할 문항이 없습니다. --ids 값을 확인해주세요.")

    if args.dry_run:
        dry_run(single, multi)
        return

    from src import config
    from src.graph import build_graph
    from src.runner import flush, langfuse_client, run_turn

    config.set_model(args.model)
    if args.judge_model:
        config.JUDGE_MODEL = args.judge_model  # judge.py가 부를 때마다 config.JUDGE_MODEL을 읽는다 (P-064)
    config.set_node_models(args.node_models)
    config.set_fast_path(args.fast_path)
    config.set_tracing(not args.no_langfuse)
    model = config.current_model()
    graph = build_graph()
    lf = langfuse_client()
    from judge import judge_row  # eval/judge.py
    refs = load_references() if args.set == "test" else {}

    def add_judge(row, state, trace_id, rep=1):
        terms = unknown_terms(state)
        if args.no_judge or not terms or rep > 1:  # 반복 실행은 첫 번째만 채점 (P-046)
            return
        ref_map = judge_references(terms, refs, row)
        try:
            j = judge_row(state.get("rewritten_query") or state.get("raw_query"), terms, state.get("final_answer", ""),
                          ref_map or None, normalization_text(state))
        except Exception as e:  # 채점 실패가 실행 결과를 지우지 않게
            row["사전밖_채점메모"] = f"[채점 오류] {type(e).__name__}: {e}"
            return
        row.update(j)
        if lf and trace_id:
            for key, name in (("사전밖_뜻일치", "unknown_meaning_ok"), ("사전밖_틀린사실없음", "unknown_no_false_fact"),
                              ("사전밖_표시", "unknown_notice_ok"), ("사전밖_눈높이", "unknown_beginner_ok")):
                if j.get(key) != "":
                    lf.create_score(trace_id=trace_id, name=name, value=j[key])

    link_state = {"warned": False}

    def link_dataset(mode, dataset_item_id, trace_id):
        """측정 trace를 랭퓨즈 Dataset 실행에 연결 (P-029). 실패해도 측정은 계속한다."""
        if not (args.dataset_run and lf and trace_id):
            return
        try:
            lf.api.dataset_run_items.create(run_name=f"{args.dataset_run}-{mode}", dataset_item_id=dataset_item_id,
                                            trace_id=trace_id, run_description=f"eval_run {run_id} · 설정 {mode}")
        except Exception as e:
            if not link_state["warned"]:
                print(f"(랭퓨즈 Dataset 연결 실패: {type(e).__name__}. scripts/langfuse_setup.py를 먼저 실행했는지 확인. 측정은 계속합니다)")
                link_state["warned"] = True

    if args.dataset_run and lf:  # 측정 전에 지침을 랭퓨즈 Prompts와 맞춰 두어 trace마다 지침 버전이 연결되게 (P-031)
        try:
            from src.llm import sync_prompts
            changed = [f"{n}({st})" for n, st in sync_prompts(lf, note=f"{args.dataset_run} 측정 전 저장소 파일") if st != "같음"]
            print("지침 버전: " + (", ".join(changed) + " 올림" if changed else "랭퓨즈와 같음"))
        except Exception as e:
            print(f"(지침을 랭퓨즈에 올리지 못함: {type(e).__name__}. 지침 버전 연결 없이 측정합니다)")

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"{set_label} · 설정 {' '.join(modes)} · 모델 {model}"
          + (f" (노드별: {config.node_models_label()})" if config.NODE_MODELS else "")
          + (" · 규칙 분류 켜짐" if config.FAST_PATH else "")
          + f" · 랭퓨즈 {'켜짐' if lf else '꺼짐'} · 사전 밖 채점 {'끔' if args.no_judge else config.JUDGE_MODEL}")
    OUT_DIR.mkdir(exist_ok=True)
    tag_model = model.replace("/", "_") + ("_mix-" + sorted(set(config.NODE_MODELS.values()))[0].split("/")[-1] if config.NODE_MODELS else "") + ("_fp" if config.FAST_PATH else "")
    prefix = args.set  # trace 이름·세션 앞머리 (dev / test)

    def run_mode(mode, rep=1):
        tail = f"-r{rep}" if args.repeat > 1 else ""  # 반복 실행이면 trace 이름에 회차 (P-046)
        print(f"\n=== 설정 {mode} ({config.MODES[mode]})" + (f" · 반복 {rep}/{args.repeat}" if args.repeat > 1 else "") + " ===")
        # 단발
        s_rows = []
        for i, r in enumerate(single, 1):
            exp_intent, exp_reason = expected_intent(r)
            row = {"id": r["id"], "세트": r["세트"], "질문": r["질문"], "의도_정답": exp_intent,
                   "범위밖_사유_정답": exp_reason, "풀이_정답": r.get("풀이_정답", ""),
                   "기대_행동": r.get("기대_행동", ""), "확인_포인트": r.get("확인_포인트", ""),
                   "하위구분": r.get("하위구분", ""), "슬랭_유형": r.get("슬랭_유형", ""),
                   "RQ1_구분": r.get("RQ1_구분", ""), "관용구_패턴사전": r.get("관용구_패턴사전", "")}
            try:
                state, trace_id = run_turn(
                    graph, r["질문"], mode=mode, tags=[r["세트"], set_label, "단발"],
                    metadata={"item_id": r["id"], "eval_run": run_id, "rep": rep}, trace_name=f"{prefix}-{r['id']}-{mode}{tail}")
                s = summarize(state)
                match, memo = intent_check(s, exp_intent, exp_reason, r.get("기대_행동", ""), mode, r.get("허용_의도", ""))
                auto = norm_check(row["풀이_정답"], state.get("norm_log") or [])
                row.update({"의도_일치": match, "의도_채점메모": memo, "풀이_자동": auto,
                            "_풀이_완전": int(bool(auto) and auto.split("/")[0] == auto.split("/")[1]),
                            **s, "trace_id": trace_id or ""})
                if lf and trace_id:
                    lf.create_score(trace_id=trace_id, name="intent_match", value=match)
                add_judge(row, state, trace_id, rep)
                link_dataset(mode, single_item_id(r["id"]), trace_id)
                print(f"[{mode} {i}/{len(single)}] {r['id']} 의도 {'O' if match else 'X'} ({s['의도_결과']}) · {s['경로']}")
            except Exception as e:  # 한 문항 실패가 전체를 멈추지 않게
                row["오류"] = f"{type(e).__name__}: {e}"
                print(f"[{mode} {i}/{len(single)}] {r['id']} 오류: {row['오류']}")
            s_rows.append(row)

        # 멀티턴: 시나리오마다 대화방(thread_id) 하나 (설정마다 새로)
        m_rows = []
        scenarios = list(dict.fromkeys(r["시나리오"] for r in multi))
        for sc in scenarios:
            turns = sorted([r for r in multi if r["시나리오"] == sc], key=lambda r: int(r["턴"]))
            thread_id = f"{run_id}-{mode}{tail}-{sc}-{uuid.uuid4().hex[:6]}"
            for r in turns:
                exp_intent, exp_reason = expected_intent(r)
                row = {"시나리오": sc, "턴": r["턴"], "세트": r["세트"], "유형": r["유형"], "질문": r["질문"],
                       "재구성_정답": r["재구성_정답"], "의도_정답": exp_intent, "범위밖_사유_정답": exp_reason,
                       "허용_의도": r.get("허용_의도", ""), "기대_행동": r["기대_행동"], "확인_포인트": r["확인_포인트"]}
                try:
                    state, trace_id = run_turn(
                        graph, r["질문"], mode=mode, thread_id=thread_id,
                        tags=[r["세트"], set_label, "멀티턴"], session_id=f"{prefix}-{sc}-{mode}{tail}-{run_id}",
                        metadata={"item_id": f"{sc}-{r['턴']}", "eval_run": run_id, "rep": rep},
                        trace_name=f"{prefix}-{sc}-t{r['턴']}-{mode}{tail}")
                    s = summarize(state)
                    i_match, memo = intent_check(s, exp_intent, exp_reason, r["기대_행동"], mode, r.get("허용_의도", ""))
                    r_match = int(s["재구성_결과"].strip() == r["재구성_정답"].strip())
                    row.update({"의도_일치": i_match, "의도_채점메모": memo, "재구성_일치": r_match, **s, "trace_id": trace_id or ""})
                    if lf and trace_id:
                        lf.create_score(trace_id=trace_id, name="intent_match", value=i_match)
                        lf.create_score(trace_id=trace_id, name="rewrite_exact", value=r_match)
                    add_judge(row, state, trace_id, rep)
                    link_dataset(mode, multi_item_id(sc, r["턴"]), trace_id)
                    print(f"[{mode}] {sc}-{r['턴']} 재구성 {'O' if r_match else 'X'} · 의도 {'O' if i_match else 'X'} ({s['의도_결과']}) · {s['경로']}")
                except Exception as e:
                    row["오류"] = f"{type(e).__name__}: {e}"
                    print(f"[{mode}] {sc}-{r['턴']} 오류: {row['오류']}")
                m_rows.append(row)
        return s_rows, m_rows

    runs = {m: [run_mode(m, k) for k in range(1, args.repeat + 1)] for m in modes}
    results = {m: reps[0] for m, reps in runs.items()}
    flush()
    repeat_lines, repeat_summary = build_repeat(runs) if args.repeat > 1 else (None, {})

    meta = {"실행 시각": run_id, "문항 세트": set_label,
            "설정": " · ".join(f"{m} ({config.MODES[m]})" for m in modes), "모델": model + (f" (노드별: {config.node_models_label()})" if config.NODE_MODELS else ""), "규칙 분류 (P-062)": "켜짐" if config.FAST_PATH else "꺼짐",
            "채점 모델": "끔" if args.no_judge else config.JUDGE_MODEL,
            "사전 밖 평가용 정답": f"{len(refs)}개 사용" if refs else "없음",
            "랭퓨즈": "켜짐" if lf else "꺼짐", "문항": args.ids or "전체"}
    if args.repeat > 1:
        meta["반복"] = f"{args.repeat}회 (요약·비교·설정별 탭은 첫 번째, 반복 탭에 전체)"
        for m, (shaky, n) in repeat_summary.items():
            meta[f"흔들린 문항 · {m}"] = f"{shaky}/{n}"
    name = f"{args.set}_{''.join(modes)}{'_x' + str(args.repeat) if args.repeat > 1 else ''}_{tag_model}_{run_id}"
    out, summary = save_results(OUT_DIR / name, meta, results, repeat_lines)

    print("\n요약 (항목 · " + " · ".join(f"{m} 단발 · {m} 멀티턴" for m in modes) + ")")
    started = False
    for line in summary:
        if line and line[0] == "항목":
            started = True
            continue
        if started and len(line) > 1 and any(v != "" for v in line[1:]):
            print(f"- {line[0]}: " + " · ".join(str(v) if v != "" else "-" for v in line[1:]))
    for m, (shaky, n) in repeat_summary.items():
        print(f"- 흔들린 문항 · {m}: {shaky}/{n}")
    print(f"\n결과 파일: {out.relative_to(ROOT)}")

    if args.dataset_run:  # 검토 대기열 (P-030). 실패해도 결과 파일은 이미 저장됨
        import review_queue  # eval/review_queue.py
        items = review_queue.plan(results, args.dataset_run)
        print()
        review_queue.print_plan(items)
        if lf:
            try:
                r = review_queue.build(lf, args.dataset_run, items, source=out.name)
                print(f"랭퓨즈 대기열 '{r['queue']}'에 {r['added']}개 넣음 (꼭 확인 {r['must']}개 먼저) · 코멘트 {r['commented']}개")
            except Exception as e:
                print(f"(검토 대기열 만들기 실패: {type(e).__name__}: {e}. "
                      f"python scripts/langfuse_setup.py --result {out.relative_to(ROOT)} --run {args.dataset_run} 로 다시 만들 수 있습니다)")


if __name__ == "__main__":
    main()
