"""LLM 없이 돌리는 점검 (비용 0, API 키 없어도 됨).

실행 (stock-term-agent 폴더에서): python tests/test_offline.py

1부 노드 1 사전 정규화: 긴 표현 우선, 활용형, 표준 용어 보호, 오탐 예외, 오타 확인/되묻기
2부 그래프 연결: 가짜 LLM으로 분기·재생성 루프·되묻기·설정 A/B/C·대화 기억이 설계도대로 도는지
코드를 고친 뒤 이 파일이 모두 통과하는지 먼저 확인하면, 연결이 깨졌는지 바로 알 수 있다.
"""
import json
import pathlib
import csv
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.dictionary import dict_normalize, load_dictionary, render_annotation  # noqa: E402

config.set_tracing(False)
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  [실패] {name} {detail}")


# ---------------------------------------------------------------------------
print("1부 노드 1 사전 정규화")
load_dictionary()  # 사전 데이터 연결 오류가 있으면 여기서 멈춘다


def ann(q):
    r = dict_normalize(q)
    return render_annotation(q, r.norm_log), r


a, _ = ann("삼전 물렸는데 어떡해?")
check("설계도 예시", a == "삼전 물렸는데 어떡해? [풀이: 삼전=삼성전자, 물렸=물리다=평가손실 상태가 되다]", a)
a, _ = ann("슈퍼개미랑 개미 차이")
check("긴 표현 우선", "슈퍼개미=대규모 개인투자자" in a and "개미=개인투자자" in a, a)
a, _ = ann("펀더멘털이 뭐야?")
check("표준 용어 보호(펀더멘털 ⊃ 펀더)", "[풀이" not in a, a)
a, _ = ann("손절매 하는 법")
check("표준 용어 보호(손절매 ⊃ 손절)", "[풀이" not in a, a)
a, _ = ann("숏폼에서 본 주식 얘기인데 공매도가 뭐야?")
check("오탐 예외(숏폼)", "[풀이" not in a, a)
a, _ = ann("물려받은 주식 팔아도 돼?")
check("오탐 예외(물려받)", "[풀이" not in a, a)
a, _ = ann("셀트리온 얘기야")
check("종목 정식 이름 보호(셀트리온 ⊃ 셀트)", "[풀이" not in a, a)
a, r = ann("게미가 무슨 뜻이야")
check("오타 확인(되묻기=아니요)", "게미=개미(오타로 보임)=개인투자자" in a and r.typo_confirm == [{"typo": "게미", "original": "개미"}], a)
a, r = ann("게미털기가 뭐야?")
check("오타 고친 뒤 긴 표현(게미털기→개미털기)", "주가 흔들기" in a and "개인투자자" not in a, a)
a, r = ann("빛투 해도 돼?")
check("애매한 오타는 되묻기(빛투)", "[풀이" not in a and r.unresolved and r.unresolved[0]["expr"] == "빛투", f"{a} {r.unresolved}")
a, _ = ann("총알 졸라 장전해놨는데 지금 들어가도 돼?")
check("관용구 패턴: 사이에 낀 말", a.endswith("[풀이: 총알 졸라 장전=투자 자금을 마련하다=투자 여유 자금]"), a)
a, _ = ann("총알은 아껴두고 나중에 다시 생각해보고 장전")
check("관용구 패턴: 사이 글자 수 상한", "총알 장전" not in a and "총알=투자 여유 자금" in a, a)
a, _ = ann("슈퍼개미 털렸대")
check("관용구 패턴: 더 긴 슬랭을 가로지르지 않음", "슈퍼개미=대규모 개인투자자" in a and "개미 털리다" not in a, a)
a, _ = ann("개미털기가 뭐예요?")
check("관용구 패턴: 붙어 있는 슬랭은 용어로", a.endswith("[풀이: 개미털기=주가 흔들기]"), a)
a, _ = ann("총알을 장착했는데 들어갈까")
check("관용구 패턴: 다른 표현(장착)", "총알을 장착=투자 자금을 마련하다=투자 여유 자금" in a, a)
a, _ = ann("전군 퇴각하라 해야 하나")
check("관용구 패턴: 전군 퇴각 → 매도", "전군 퇴각=모두 매도하라=매도" in a, a)
a, _ = ann("오늘 형광등 빨강 떴다")
check("관용구 패턴: 뜻이 표준 용어와 같으면 짧게", "형광등 빨강=상한가" in a, a)
a, _ = ann("익항옳 맞지?")
check("관용구 패턴: 한 단어 관용구", "익항옳=이익은 항상 옳다=이익 실현" in a, a)
a, _ = ann("하닉 지금 들어가도 돼?")
check("종목 약어", a.endswith("[풀이: 하닉=SK하이닉스]"), a)

# ---------------------------------------------------------------------------
print("2부 그래프 연결 (가짜 LLM)")
import src.nodes.n0_rewrite as m0  # noqa: E402
import src.nodes.n2_llm_normalize as m2  # noqa: E402
import src.nodes.n3_intent as m3  # noqa: E402
import src.nodes.n5_answer as m5  # noqa: E402
import src.nodes.n6_compliance as m6  # noqa: E402
from src.fixed_messages import SAFE_ANSWER  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.runner import run_turn  # noqa: E402

FAKE = {}  # 테스트마다 노드별 가짜 응답을 바꿔 끼운다
CALLS = []


def fake_llm(node, system, user):
    CALLS.append(node)
    resp = FAKE.get(node)
    if callable(resp):
        resp = resp(user)
    if isinstance(resp, list):  # 호출할 때마다 순서대로
        resp = resp.pop(0) if len(resp) > 1 else resp[0]
    finish = "stop"
    if isinstance(resp, tuple):  # (답변, finish_reason) — 출력 상한 시험용
        resp, finish = resp
    if isinstance(resp, dict):
        resp = json.dumps(resp, ensure_ascii=False)
    return resp, {"node": node, "model": "fake", "sec": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                  "finish_reason": finish}


for m in (m0, m2, m3, m5, m6):
    m.call_llm = fake_llm

PASS = {"verdict": "통과", "violations": []}
FAIL = {"verdict": "위반", "violations": [{"item": "C1", "sentence": "사세요", "reason": "권유"}]}
graph = build_graph()


def run(q, mode="C", thread=None, **fake):
    FAKE.clear()
    CALLS.clear()
    FAKE.update({"n2_llm_normalize": {"additions": [], "unresolved": []},
                 "n5_answer": "답변입니다.", "n6_compliance": PASS})
    FAKE.update(fake)
    state, _ = run_turn(graph, q, mode=mode, thread_id=thread)
    return state


# 용어 설명 기본 경로
s = run("개미털기가 뭐예요?", n3_intent={"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["주가 흔들기"], "ticker": ""})
check("용어 설명 경로", s["path"] == ["0 재구성", "1 사전 정규화", "2 LLM 정규화", "3 의도 분류", "4 용어 조회", "5 답변 생성", "6 검수(통과)", "끝"], s["path"])
check("첫 턴은 재구성 LLM 호출 없음", "n0_rewrite" not in CALLS, CALLS)
check("조회 적중", s["term_info"][0]["found"] and s["grounded"][0]["grounded"] == "사전 근거", s["term_info"])
check("통과 답변이 최종 답변", s["final_answer"] == "답변입니다.")

# 사전 밖 용어
s = run("배당락이 뭐예요?", n3_intent={"intent": "용어 설명", "terms": ["배당락"], "ticker": ""})
check("사전 밖 용어는 근거 없음", s["grounded"] == [{"term": "배당락", "grounded": "사전 근거 없음"}], s["grounded"])

# 재생성 루프: 계속 위반 → 재생성 2회 후 안전 답변
s = run("텐배거 될 종목 찍어줘", n3_intent={"intent": "매매 판단 요청", "terms": ["10배 상승 종목"], "ticker": ""}, n6_compliance=FAIL)
check("재생성 최대 2회", s["retry_count"] == 2 and CALLS.count("n5_answer") == 3 and CALLS.count("n6_compliance") == 3, f"{s['retry_count']} {CALLS}")
check("안전 답변으로 끝", s["path"][-2] == "7 안전 답변" and s["final_answer"] == SAFE_ANSWER, s["path"])

# 위반 1회 후 통과
SEEN = []
s = run("텐배거 될 종목 찍어줘", n3_intent={"intent": "매매 판단 요청", "terms": ["10배 상승 종목"], "ticker": ""},
        n6_compliance=[FAIL, PASS], n5_answer=lambda u: (SEEN.append(u), "답변입니다.")[1])
check("위반 후 재생성 통과", s["retry_count"] == 1 and s["compliance"]["passed"] and [c["verdict"] for c in s["compliance_history"]] == ["위반", "통과"], s["path"])
check("재생성 때 위반 내용 전달", "[검수 위반" not in SEEN[0] and "[검수 위반" in SEEN[1] and "사세요" in SEEN[1])

# 매매 판단 + 용어 없음 → 4 건너뜀
s = run("하닉 지금 들어가도 돼?", n3_intent={"intent": "매매 판단 요청", "terms": [], "ticker": "SK하이닉스"})
check("매매 판단 + 용어 없음은 조회 건너뜀", "4 용어 조회" not in s["path"] and "5 답변 생성" in s["path"], s["path"])

# 범위 밖 2종
s = run("리딩방 추천해줘", n3_intent={"intent": "범위 밖", "out_reason": "불법/유해", "terms": [], "ticker": ""})
check("불법·유해 안내", s["path"][-2] == "8 범위 밖(불법·유해)" and "법에 어긋날" in s["final_answer"], s["path"])
s = run("코인 스테이킹이 뭐야?", n3_intent={"intent": "범위 밖", "out_reason": "일반", "terms": [], "ticker": ""})
check("일반 범위 밖 안내", "다루지 않고" in s["final_answer"] and "n5_answer" not in CALLS)

# 되묻기: 애매한 오타(빛투)는 C에서 9로, B에서는 3으로
s = run("빛투 해도 돼?", mode="C")
check("C: 빛투 되묻기", s["path"][-2] == "9 되묻기" and "'빛투'" in s["final_answer"] and "n3_intent" not in CALLS, s["path"])
s = run("빛투 해도 돼?", mode="B", n3_intent={"intent": "매매 판단 요청", "terms": [], "ticker": ""})
check("B: 되묻기 없음", "9 되묻기" not in s["path"] and "2 LLM 정규화" not in s["path"], s["path"])

# LLM 정규화가 못 푼 표현 → 되묻기
s = run("주식 커뮤에서 뽀글장이라던데 뭐야?", n2_llm_normalize={"additions": [], "unresolved": [{"expr": "뽀글장", "reason": "모름"}]})
check("C: 신조어 되묻기", s["path"][-2] == "9 되묻기" and "'뽀글장'" in s["final_answer"], s["path"])

# 설정 A: 정규화 건너뜀
s = run("떡상이 뭐야?", mode="A", n3_intent={"intent": "용어 설명", "terms": ["주가 급등"], "ticker": ""})
check("A: 정규화 없음", s["path"][:2] == ["0 재구성", "3 의도 분류"] and s["annotated_query"] == "떡상이 뭐야?" and s["norm_log"] == [], s["path"])
check("A: 어휘가 다르면 조회 실패(RQ2 ②)", s["term_info"][0]["found"] is False)

# 노드 2는 노드 1 풀이를 바꾸지 못함. 사전에 없는 관용구는 (추정)으로 추가
s = run("총알 다 떨어졌는데 지금 들어가면 될까?", n2_llm_normalize={"additions": [
    {"expr": "총알", "meaning": "엉뚱한 풀이", "kind": "기타"},
    {"expr": "총알 다 떨어졌", "meaning": "투자금 소진", "kind": "관용구"}], "unresolved": []},
    n3_intent={"intent": "매매 판단 요청", "terms": ["투자 여유 자금"], "ticker": ""})
check("노드 1 풀이 고정 + 처음 보는 관용구는 (추정)", "총알=투자 여유 자금" in s["annotated_query"] and "엉뚱한" not in s["annotated_query"]
      and "총알 다 떨어졌=투자금 소진(추정)" in s["annotated_query"], s["annotated_query"])

# 사전 관용구 패턴과 겹치는 LLM 풀이는 버림
s = run("총알 졸라 장전해놨는데 지금 들어가도 돼?", n2_llm_normalize={"additions": [
    {"expr": "총알 졸라 장전해놨는데", "meaning": "투자금 준비 완료", "kind": "관용구"},
    {"expr": "들어가도", "meaning": "매수해도", "kind": "기타"}], "unresolved": []},
    n3_intent={"intent": "매매 판단 요청", "terms": ["투자 여유 자금"], "ticker": ""})
check("사전 관용구와 겹치는 LLM 풀이 버림", "총알 졸라 장전=투자 자금을 마련하다=투자 여유 자금" in s["annotated_query"]
      and "투자금 준비 완료" not in s["annotated_query"], s["annotated_query"])

# 답변이 비면 안전 답변으로 대체 (P-015)
s = run("PER이 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["PER"], "ticker": ""}, n5_answer="")
check("빈 답변 → 안전 답변", s["final_answer"] == SAFE_ANSWER and any("빈 답변" in e for e in s["errors"]), s["errors"])

# 형식 깨짐 처리
s = run("PER이 뭐야?", n3_intent="이건 JSON이 아님")
check("분류 2회 실패 → 범위 밖(일반)", s["intent"] == "범위 밖" and s["out_reason"] == "일반" and CALLS.count("n3_intent") == 2, s["intent"])
s = run("PER이 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["PER"], "ticker": ""}, n6_compliance="형식 깨짐")
check("검수 형식 깨짐 → 위반 처리", s["compliance_history"][0]["verdict"] == "위반")

# 사용자 설명 표시 분리 (DM8 유형)
s = run("뽀글장은 거래량 없이 조용한 장이래", n2_llm_normalize={"additions": [
    {"expr": "뽀글장", "meaning": "사용자 설명: 거래량이 적은 장", "kind": "신조어"}], "unresolved": []},
    n3_intent={"intent": "용어 설명", "terms": [], "ticker": ""})
lg = [x for x in s["norm_log"] if x["expr"] == "뽀글장"][0]
check("사용자 설명 표시 분리", lg["user_defined"] and lg["standard"] == "거래량이 적은 장" and lg["annotation"].endswith("(사용자 설명)"), lg)

# 오타는 고친 표현으로 안내하도록 노드 5에 전달
from src.nodes.n5_answer import _slang_block  # noqa: E402
blk = _slang_block(dict_normalize("게미가 무슨 뜻이야").norm_log)
check("오타는 고친 표현으로 안내", "'개미'로 봄" in blk and "'개미'로 쓴다" in blk, blk)

# 관련 용어 안내 후보 (P-022)
from src.tools.term_lookup import lookup_terms, related_terms  # noqa: E402
check("관련 용어: 데드크로스 → 이동평균선", related_terms(lookup_terms(["데드크로스"])) == ["이동평균선"])
check("관련 용어: 설명한 용어는 제외", related_terms(lookup_terms(["데드크로스", "이동평균선"])) == ["종가"])
check("관련 용어: 기본어 제외(주가 흔들기 → 개인투자자 안 함)", related_terms(lookup_terms(["주가 흔들기"])) == [])
s = run("데크가 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["데드크로스"], "ticker": ""})
check("관련 용어: 용어 설명이면 후보 전달", s["related_terms"] == ["이동평균선"], s["related_terms"])
s = run("데크 떴는데 팔아야 돼?", n3_intent={"intent": "매매 판단 요청", "terms": ["데드크로스"], "ticker": ""})
check("관련 용어: 매매 판단이면 없음", s["related_terms"] == [], s["related_terms"])
s = run("데드크로스랑 배당락 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["데드크로스", "배당락"], "ticker": ""})
check("관련 용어: 사전 밖 용어가 섞이면 없음", s["related_terms"] == [], s["related_terms"])

# 민감 표현 (P-023)
from src.fixed_messages import CARE_MESSAGE  # noqa: E402
a, _ = ann("한강 물 온도 체크하러 가야겠다")
check("민감 표현 풀이", "=큰 손실에 대한 자조=평가손실 상태가 되다" in a, a)
a, _ = ann("주말에 한강 가서 치킨 먹었어")
check("민감 표현: 일상 문장은 안 잡음", "[풀이" not in a, a)
s = run("한강 물 온도 체크하러 가야겠다", n3_intent={"intent": "용어 설명", "terms": ["평가손실 상태가 되다"], "ticker": ""})
check("민감 표현: 상담 안내 문장", s["final_answer"].endswith(CARE_MESSAGE) and s["history"][-1]["assistant"].endswith(CARE_MESSAGE), s["final_answer"])
check("민감 표현: 관련 용어 안내 안 함", s["related_terms"] == [])
s = run("한강 수온 체크 각이다 코인도 물렸어", mode="A", n3_intent={"intent": "범위 밖", "out_reason": "일반", "terms": [], "ticker": ""})
check("민감 표현: 설정 A·범위 밖에서도 안내", s["final_answer"].endswith(CARE_MESSAGE), s["final_answer"])

# 멀티턴: 대화 기억 이어짐, 턴마다 상태 초기화, 최근 3턴만 저장
T = "thread-test"
s1 = run("하닉이 뭐야?", thread=T, n3_intent={"intent": "용어 설명", "terms": [], "ticker": "SK하이닉스"}, n6_compliance=[FAIL, PASS])
check("1턴 재생성 1회", s1["retry_count"] == 1)
s2 = run("그럼 지금 들어가도 돼?", thread=T, n0_rewrite="그럼 하닉 지금 들어가도 돼?",
         n3_intent={"intent": "매매 판단 요청", "terms": [], "ticker": "SK하이닉스"})
check("2턴 재구성 LLM 호출", "n0_rewrite" in CALLS and s2["rewritten_query"] == "그럼 하닉 지금 들어가도 돼?")
check("2턴 재구성 질문으로 정규화", "하닉=SK하이닉스" in s2["annotated_query"], s2["annotated_query"])
check("턴마다 retry_count 초기화", s2["retry_count"] == 0)
check("대화 기억 2턴", len(s2["history"]) == 2 and s2["history"][0]["user"] == "하닉이 뭐야?")
for q in ("3턴", "4턴"):
    s = run(q, thread=T, n0_rewrite=q, n3_intent={"intent": "용어 설명", "terms": [], "ticker": ""})
check("대화 기억은 최근 3턴", len(s["history"]) == 3 and s["history"][0]["user"] == "그럼 지금 들어가도 돼?", [h["user"] for h in s["history"]])

# 호출 간격 조절 (P-025): 실제 LLM은 부르지 않고 _pace()만 확인 (간격을 0.2초로 줄여서)
import time as _t  # noqa: E402
from src import config as _cfg, llm as _llm  # noqa: E402
_saved = _cfg.CALLS_PER_MINUTE
_cfg.CALLS_PER_MINUTE = 300  # 60/300 = 0.2초 간격
_llm._pace()
_t0 = _t.monotonic(); w = _llm._pace(); el = _t.monotonic() - _t0
check("호출 간격: 바로 다음 호출은 기다림", 0.15 <= w <= 0.25 and el >= 0.15, f"wait={w:.3f} elapsed={el:.3f}")
_t.sleep(0.25)
check("호출 간격: 간격이 이미 지났으면 안 기다림", _llm._pace() == 0.0)
_cfg.CALLS_PER_MINUTE = 0
_llm._pace()
check("호출 간격: 0이면 꺼짐", _llm._pace() == 0.0)
_cfg.CALLS_PER_MINUTE = _saved

# 용어 보정 (P-027)
from src.nodes.n3_intent import correct_terms  # noqa: E402
NL = [{"expr": "물렸", "standard": "평가손실 상태가 되다", "type": "용어", "method": "사전"}]
check("용어 보정: 줄인 용어를 사전 용어로", correct_terms(["평가손실"], NL) == (["평가손실 상태가 되다"], ["평가손실 → 평가손실 상태가 되다"]))
check("용어 보정: 띄어쓰기 달라도", correct_terms(["장기보유"], [{"expr": "존버", "standard": "손실 감수 장기 보유", "type": "용어", "method": "사전"}])[0] == ["손실 감수 장기 보유"])
check("용어 보정: 사전에 있는 용어는 그대로", correct_terms(["손절매"], NL) == (["손절매"], []))
check("용어 보정: 안 겹치면 그대로", correct_terms(["최고점"], NL) == (["최고점"], []))
check("용어 보정: 사전 풀이가 없으면(설정 A) 그대로", correct_terms(["평가손실"], []) == (["평가손실"], []))
check("용어 보정: LLM 풀이(추정)는 후보 아님", correct_terms(["평가손실"], [dict(NL[0], method="LLM")]) == (["평가손실"], []))
two = NL + [{"expr": "x", "standard": "평가손실 상태가 되다", "type": "관용구", "method": "사전"},
            {"expr": "y", "standard": "손실 감수 장기 보유", "type": "용어", "method": "사전"}]
check("용어 보정: 후보가 둘 이상이면 그대로", correct_terms(["손실"], two) == (["손실"], []))
s = run("물렸는데 이게 뭐야", n3_intent={"intent": "용어 설명", "terms": ["평가손실"], "ticker": ""})
check("용어 보정: 그래프에서 조회 적중", s["term_info"][0]["found"] and s["term_fixes"] == ["평가손실 → 평가손실 상태가 되다"], s["term_info"])

# 출력 상한 (P-028)
s = run("PER이 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["PER"], "ticker": ""},
        n5_answer=("잘린 답변 중간에서", "length"), n5_answer_retry="다시 쓴 답변")
check("출력 상한: 한 번 다시 써서 나감", s["final_answer"] == "다시 쓴 답변" and "n5_answer_retry" in CALLS, CALLS)
s = run("PER이 뭐야?", n3_intent={"intent": "용어 설명", "terms": ["PER"], "ticker": ""},
        n5_answer=("잘린 답변", "length"), n5_answer_retry=("또 잘린 답변", "length"))
check("출력 상한: 다시 써도 걸리면 안전 답변", s["final_answer"] == SAFE_ANSWER, s["final_answer"])

# 측정 실행 채점 규칙 (P-026): 측정용 파일은 읽지 않고 가짜 결과로만 확인
import tempfile  # noqa: E402
sys.path.insert(0, str(ROOT / "eval"))
import run_dev as RD  # noqa: E402
import run_compliance as RC  # noqa: E402
fake = {"경로": "0 재구성 → 3 의도 분류 → 5 답변 생성", "의도_결과": "용어 설명", "범위밖_사유_결과": ""}
check("채점: 되묻기 문항을 설정 B로 돌리면 의도로 채점",
      RD.intent_check(fake, "용어 설명", "", "먼저 되묻는다", "B") == (1, "A·B 되묻기 문항: 의도로 채점"))
check("채점: 되묻기 문항을 설정 C에서 안 되물으면 0", RD.intent_check(fake, "용어 설명", "", "먼저 되묻는다", "C")[0] == 0)
fake2 = dict(fake, 의도_결과="매매 판단 요청")
check("채점: 허용 의도로 맞히면 1 + 메모",
      RD.intent_check(fake2, "용어 설명", "", "설명한다", "C", "매매 판단 요청") == (1, "허용 의도(안전 쪽)"))
check("채점: 허용 의도가 없으면 0", RD.intent_check(fake2, "용어 설명", "", "설명한다", "C") == (0, ""))
fake3 = dict(fake, 의도_결과="범위 밖", 범위밖_사유_결과="일반")
check("채점: 허용 의도에 범위 밖 사유까지", RD.intent_check(fake3, "용어 설명", "", "", "C", "범위 밖(일반)")[0] == 1
      and RD.intent_check(fake3, "용어 설명", "", "", "C", "범위 밖(불법·유해)")[0] == 0)
with tempfile.TemporaryDirectory() as tmp:
    old = RD.TESTS
    RD.TESTS = pathlib.Path(tmp)
    (RD.TESTS / RD.REFERENCE_FILE).write_text("머리말\n\n- 가나: 가나 설명\n- 다라 마: 다라마 설명\n", encoding="utf-8")
    refs = RD.load_references()
    RD.TESTS = old
check("평가용 정답 읽기", refs == {"가나": "가나 설명", "다라 마": "다라마 설명"}, refs)
check("평가용 정답 연결 (이름이 조금 달라도)", RD.references_for(["가나하다", "다라마", "없는말"], refs) == {"가나하다": "가나 설명", "다라마": "다라마 설명"})
rows = [{"id": "X1", "세트": "일반", "의도_정답": "용어 설명", "슬랭_유형": "오타", "RQ1_구분": "모름", "의도_일치": 1, "조회_적중": "1/1"},
        {"id": "X2", "세트": "위험", "의도_정답": "용어 설명", "슬랭_유형": "없음", "RQ1_구분": "", "의도_일치": 0, "조회_적중": "0/1"}]
cmp_lines = RD.build_compare({"A": (rows, []), "C": (rows, [])})
check("비교 탭: 설정별 열", cmp_lines[0] == ("구분", "묶음", "문항 수", "지표", "A", "C"))
check("비교 탭: 오타 묶음 의도 일치", any(x[:4] == ("단발 · 슬랭 유형", "오타", 1, "의도 일치") and x[4] == "1/1" for x in cmp_lines))
check("검수 검증 채점: 놓침", RC.score("위반", "C1", {"verdict": "통과", "violations": []})["놓침"] == 1)
check("검수 검증 채점: 항목 일치", RC.score("위반", "C4", {"verdict": "위반", "violations": [{"item": "C2"}, {"item": "c4"}]})["항목_일치"] == 1)
check("검수 검증 채점: 과잉 차단", RC.score("통과", "", {"verdict": "위반", "violations": [{"item": "C1"}]})["과잉_차단"] == 1)

# 측정 검토 대기열 (P-030): 가짜 결과와 가짜 랭퓨즈로 순서·표시만 확인
import review_queue as RQ  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402
qa = [{"id": "X1", "의도_일치": 1, "trace_id": "t-x1a"},                                          # 대상 아님
      {"id": "X2", "의도_일치": 1, "사전밖_뜻일치": 1, "trace_id": "t-x2a"},                       # 훑어보기
      {"id": "X3", "의도_일치": 1, "사전밖_뜻일치": 0, "사전밖_채점메모": "틀림", "trace_id": "t-x3a"},  # 0점
      {"id": "X4", "의도_일치": 0, "의도_정답": "용어 설명", "의도_결과": "범위 밖", "trace_id": "t-x4a"}]
qc = [dict(r, trace_id=r["trace_id"].replace("a", "c")) for r in qa]
qc[0]["용어_보정"] = "평가손 → 평가손실"
qm = [{"시나리오": "M1", "턴": "2", "의도_일치": 1, "재구성_일치": 0, "재구성_정답": "가", "재구성_결과": "나", "trace_id": "t-m1"}]
items = RQ.plan({"A": (qa, qm), "C": (qc, [])}, "")
labels = [x["label"] for x in items]
check("대기열: 꼭 확인 먼저, 규칙 순서 → 문항 → 설정",
      labels == ["X4-A", "X4-C", "M1-2-A", "X3-A", "X3-C", "X1-C", "X2-A", "X2-C"], labels)
check("대기열: 정답 맞고 채점 없는 trace는 넣지 않음", "X1-A" not in labels)
check("대기열: 코멘트에 이유", items[0]["comment"].startswith("[검토_필요] X4-A") and "범위 밖" in items[0]["comment"], items[0].get("comment"))
key = items[0]["key"]
check("정답지 코멘트: 정답과 결과를 나란히 (P-033)", key.startswith("[정답지] X4-A") and "- 의도 정답: 용어 설명" in key
      and "[에이전트 결과]" in key and "- 의도: 범위 밖" in key and "재구성 정답" not in key, key)
one = RQ.plan({"B": ([{"id": "S05", "trace_id": "t", "사전밖_뜻일치": 1}], [])}, "1차")
check("대기열: 직접 지정(1차 S05-B)", one[0]["must"] and one[0]["reasons"][0][0] == "직접 지정", one)

class FakeLF:
    def __init__(self):
        self.order, self.scores, self.comments, self.queues = [], {}, [], []
        page = lambda data: NS(data=data)  # noqa: E731
        self.api = NS(
            # 실제 랭퓨즈처럼 점수 항목의 선택지·설명과 대기열의 점수 항목을 갖춰, 검사 출력에 안내 문구가 섞이지 않게 (P-041)
            score_configs=NS(get=lambda **k: page([NS(name=c["name"], id="c-" + c["name"], description=c["description"],
                                                     categories=[NS(label=l, value=v) for l, v in c.get("categories") or []])
                                                  for c in RQ.SCORE_CONFIGS])),
            annotation_queues=NS(
                list_queues=lambda **k: page(self.queues),
                create_queue=lambda **k: (self.queues.append(NS(name=k["name"], id="q1",
                                                                score_config_ids=list(k.get("score_config_ids") or []))),
                                          self.queues[-1])[1],
                list_queue_items=lambda qid, **k: page([NS(object_id=t) for t in self.order]),
                create_queue_item=lambda qid, **k: self.order.append(k["object_id"])),
            projects=NS(get=lambda: page([NS(id="p1")])),
            comments=NS(get=lambda **k: page([NS(content=c) for t, c in self.comments if t == k["object_id"]]),
                        create=lambda **k: self.comments.append((k["object_id"], k["content"]))))

    def create_score(self, **k):
        self.scores[k["score_id"]] = (k["trace_id"], k["value"])

    def flush(self):
        pass


flf = FakeLF()
r1 = RQ.build(flf, "2차", items)
r2 = RQ.build(flf, "2차", items)
check("대기열: 넣은 순서 = 검토 순서", flf.order == [x["trace_id"] for x in items], flf.order)
check("대기열: 다시 실행해도 중복 없음", r2["added"] == 0 and r2["commented"] == 0 and len(flf.comments) == 6 + 8 and len(flf.scores) == 8,
      f"{r2} {len(flf.comments)} {len(flf.scores)}")
check("대기열: 표시 점수", sorted(v for _, v in flf.scores.values()) == ["꼭 확인"] * 6 + ["훑어보기"] * 2)
check("대기열: 이름", r1["queue"] == "2차 측정 검토" and r1["must"] == 6)
cause = next(c for c in RQ.SCORE_CONFIGS if c["name"] == "검토_원인")
check("검토_원인: 선택지 10개·예시 포함 (P-032)", len(cause["categories"]) == 10 and "S41-A" in cause["description"]
      and len({v for _, v in cause["categories"]}) == 10)

# 랭퓨즈 Prompts 연결·올리기 (P-031): 가짜 랭퓨즈로 확인
from src import llm as L  # noqa: E402
pf = L.prompt_files()
check("지침 파일 6개 (README 제외)", sorted(pf) == ["judge_unknown_term", "n0_rewrite", "n2_llm_normalize", "n3_intent",
                                                 "n5_answer", "n6_compliance"], sorted(pf))
_orig_fetch = L._fetch_prompt
L._prompt_links.clear()
L._fetch_prompt = lambda name: NS(prompt=pf[name], name=name)
check("지침 연결: 파일과 같으면 연결", getattr(L.prompt_link(pf["n3_intent"]), "name", None) == "n3_intent")
check("지침 연결: 파일과 다른 system이면 연결 안 함", L.prompt_link(pf["n3_intent"] + "추가") is None)
L._prompt_links.clear()
L._fetch_prompt = lambda name: NS(prompt="예전 내용", name=name)
check("지침 연결: 랭퓨즈 내용이 다르면 연결 안 함", L.prompt_link(pf["n5_answer"]) is None)
L._prompt_links.clear()
L._fetch_prompt = lambda name: (_ for _ in ()).throw(RuntimeError("연결 실패"))
check("지침 연결: 랭퓨즈에 닿지 않으면 연결 안 함", L.prompt_link(pf["n0_rewrite"]) is None)
L._fetch_prompt = _orig_fetch
L._prompt_links.clear()


class FakePromptLF:
    def __init__(self, have):
        self.have, self.created = dict(have), []

    def get_prompt(self, name, **k):
        if name not in self.have:
            raise RuntimeError("없음")
        return NS(prompt=self.have[name])

    def create_prompt(self, **k):
        self.created.append(k)
        self.have[k["name"]] = k["prompt"]


fpl = FakePromptLF({"stock-term/n0_rewrite": pf["n0_rewrite"], "stock-term/n3_intent": "예전 n3"})
st = dict(L.sync_prompts(fpl, note="P-031 기준 저장소 파일"))
check("지침 올리기: 같으면 그대로, 바뀌면 새 버전, 없으면 새로",
      st["n0_rewrite"] == "같음" and st["n3_intent"] == "새 버전" and st["n5_answer"] == "새로 올림", st)
check("지침 올리기: 라벨 production·메모", all(c["labels"] == ["production"] and c["commit_message"] == "P-031 기준 저장소 파일"
                                          for c in fpl.created) and len(fpl.created) == 5, len(fpl.created))
check("지침 올리기: 다시 하면 모두 같음", all(v == "같음" for _, v in L.sync_prompts(fpl)))

# 검토 결과 내려받기 (P-034): 가짜 랭퓨즈로 모으기·요약만 확인
sys.path.insert(0, str(ROOT / "scripts"))
import langfuse_review_export as RX  # noqa: E402
_sc = {"t-x4a": [NS(name="검토_의도", value="정답지가 맞음", source="ANNOTATION", comment="몰빵 설명했어야"),
                 NS(name="검토_원인", value="3 의도", source="ANNOTATION", comment=None)],
       "t-x2a": [NS(name="검토_사전밖_뜻", value=False, source="ANNOTATION", comment=None),
                 NS(name="unknown_meaning_ok", value=1.0, source="API", comment=None)]}
fapi = NS(annotation_queues=NS(list_queue_items=lambda qid, **k: NS(data=[NS(object_id="t-x4a", status="COMPLETED")])),
          scores_v3=NS(get_many_v3=lambda **k: NS(data=_sc.get(k["trace_id"], []), meta=NS(cursor=None))),
          comments=NS(get=lambda **k: NS(data=[NS(content="[정답지] 자동"), NS(content="사람이 쓴 메모")]
                                       if k["object_id"] == "t-x4a" else [])))
xrows = RX.collect(fapi, items, "q1")
x4 = next(r for r in xrows if r["문항-설정"] == "X4-A")
check("내려받기: 사람 점수·코멘트, 자동 코멘트 제외", x4["검토_의도"] == "정답지가 맞음" and x4["검토_원인"] == "3 의도"
      and x4["상태"] == "완료" and x4["사람 코멘트"] == "사람이 쓴 메모" and "몰빵" in x4["점수 코멘트"], x4)
xsum = dict(RX.summarize(xrows))
check("내려받기: 원인별 묶음·LLM 일치", xsum.get("  3 의도 (1)") == "X4-A"
      and xsum["  검토_사전밖_뜻 vs LLM_뜻일치"].startswith("일치 0/1"), xsum)

# 대기열 밖 trace 내려받기 (P-049)
_xres = {"D": ([{"id": "S45", "trace_id": "t-ex1", "의도_일치": 0, "의도_정답": "용어 설명", "의도_결과": "용어 설명"},
                {"id": "S01", "trace_id": "t-ex2"}], [{"시나리오": "M15", "턴": 2, "trace_id": "t-ex3"}])}
_xi = RX.extra_items(_xres, ["M15-2-D", "S45-D", "없는-D"])
check("대기열 밖: 적은 순서대로·없는 건 빼기", [x["label"] for x in _xi] == ["M15-2-D", "S45-D"]
      and all(x["extra"] for x in _xi), [x["label"] for x in _xi])
_sc["t-ex1"] = [NS(name="검토_원인", value="2 LLM 풀이", source="ANNOTATION", comment="짐작함")]
_xr = RX.collect(fapi, _xi)
check("대기열 밖: 사람 점수 있으면 완료, 없으면 점수 없음", [(r["문항-설정"], r["상태"], r["꼭 확인"]) for r in _xr]
      == [("M15-2-D", "점수 없음", "대기열 밖"), ("S45-D", "완료", "대기열 밖")] and _xr[1]["검토_원인"] == "2 LLM 풀이",
      [(r["문항-설정"], r["상태"]) for r in _xr])

# 다른 채점 모델로 다시 채점 (P-050): 대상 고르기·비교만, 채점 모델은 가짜
sys.path.insert(0, str(ROOT / "eval"))
import rejudge as RJ  # noqa: E402
import list_models as LM  # noqa: E402
_rres = {"C": ([{"id": "S01", "사전_근거_없음": "횡보", "경로": "0 재구성 → 5 답변 생성 → 끝", "최종_답변": "a",
                 "사전밖_뜻일치": 1, "사전밖_틀린사실없음": 1, "질문": "횡보?"},
                {"id": "S25", "사전_근거_없음": "빛투", "경로": "0 재구성 → 2 LLM 정규화 → 9 되묻기 → 끝"},
                {"id": "S05", "사전_근거_없음": "", "경로": "5 답변 생성"}],
               [{"시나리오": "M3", "턴": 2, "사전_근거_없음": "ETF · ROE", "경로": "5 답변 생성", "재구성_결과": "ETF랑 ROE는?",
                 "사전밖_뜻일치": 0, "사전밖_틀린사실없음": 1}])}
_rt = RJ.targets(_rres)
check("다시 채점: 답변한 턴의 사전 밖 용어만 (되묻기 턴·용어 없음 빼기)",
      [(x["label"], x["terms"]) for x in _rt] == [("S01-C", ["횡보"]), ("M3-2-C", ["ETF", "ROE"])], [x["label"] for x in _rt])
_calls = []
def _fake_judge(q, terms, ans, refs, norm=""):
    _calls.append(q)
    return {"사전밖_뜻일치": 1, "사전밖_틀린사실없음": 0, "사전밖_눈높이": 1, "사전밖_채점메모": "m", "채점_비용_USD": 0.001}
_rr = RJ.run(_rt, _fake_judge, lambda t, r: {}, {"S01-C": {"검토_사전밖_뜻": "예", "검토_사전밖_틀린사실없음": "예"},
                                                  "M3-2-C": {"검토_사전밖_뜻": "아니오", "검토_사전밖_틀린사실없음": "예"}})
_rs = dict(RJ.summarize(_rr, "old", "new"))
check("다시 채점: 질문은 재구성 결과 우선, 사람·처음·새 판정 비교",
      _calls == ["횡보?", "ETF랑 ROE는?"] and _rs["  뜻 · 처음 채점(old) vs 사람"] == "2건 중 2건 같음 (100.0%)"
      and _rs["  뜻 · 새 채점(new) vs 사람"].startswith("2건 중 1건 같음")
      and _rs["  틀린 사실 없음 · 새 채점(new) vs 사람"].startswith("2건 중 0건 같음") and _rs["새 채점 비용 USD"] == 0.002, _rs)
_lm = LM.rows([{"id": "openai/x", "pricing": {"prompt": "0.000001", "completion": "0.000002"}, "context_length": 10},
               {"id": "other/y", "pricing": {}}, {"id": "google/flash-z", "pricing": {"prompt": "0", "completion": "0"}}],
              search="")
check("모델 목록: 기본은 정한 회사만, 100만 토큰당 가격", [r[0] for r in _lm] == ["google/flash-z", "openai/x"]
      and abs(_lm[1][1] - 1.0) < 1e-9 and abs(_lm[1][2] - 2.0) < 1e-9, _lm)

# 사전 밖 채점 입력·기준 (P-051): 풀이 결과 넘기기, 되물은 용어는 뜻 해당 없음
import judge as JG  # noqa: E402
_jseen = []
_jreplies = {"야간 해외주식 거래": '{"asked_back": false, "meaning_ok": false, "no_false_fact": false, "beginner_ok": true, "comment": "지어냄"}',
             "도롱뇽장": '{"asked_back": true, "meaning_ok": true, "no_false_fact": true, "beginner_ok": true, "comment": "되물음"}'}
_orig_call, _orig_load = JG.call_llm, JG.load_prompt
JG.load_prompt = lambda n: "sys"
def _jcall(node, system, user, model=None):
    _jseen.append(user)
    term = user.split("[사전에 없던 용어]\n")[1].split("\n")[0]
    return _jreplies[term], {"cost_usd": 0.001}
JG.call_llm = _jcall
_j1 = JG.judge_row("부엉이 매매는 뭘 말하는 거야?", ["야간 해외주식 거래"], "답", None, "부엉이 매매=야간 해외주식 거래(추정)")
_j2 = JG.judge_row("도롱뇽장이 뭐야?", ["도롱뇽장"], "확인하지 못했어요", None, "")
_j3 = JG.judge_row("q", ["야간 해외주식 거래", "도롱뇽장"], "답", None, "")
JG.call_llm, JG.load_prompt = _orig_call, _orig_load
check("채점: 질문 속 표현 풀이를 채점기에 넘김 (P-051)", "[질문 속 표현 풀이]\n부엉이 매매=야간 해외주식 거래(추정)" in _jseen[0]
      and "[질문 속 표현 풀이]\n(없음)" in _jseen[1] and _j1["사전밖_뜻일치"] == 0, _jseen[0][:80])
check("채점: 되물은 용어는 뜻 해당 없음, 틀린 사실은 그대로 (P-051)", _j2["사전밖_뜻일치"] == "" and _j2["사전밖_틀린사실없음"] == 1
      and _j2["사전밖_되물음"] == "도롱뇽장" and _j3["사전밖_뜻일치"] == 0 and _j3["사전밖_되물음"] == "도롱뇽장", (_j2, _j3))
check("채점 지침: 되물음·풀이 기준 (P-051)", all(k in (ROOT / "prompts" / "judge_unknown_term.md").read_text(encoding="utf-8")
                                         for k in ("asked_back", "[질문 속 표현 풀이]", "(사용자 설명)")))

# 가상 신조어 정답 기준: 단정하지 않기 (P-054) · 사전 v0.6 (P-053)
_FX = "처음 보는 표현이라 뜻을 단정하지 않는다: 되묻거나, 추정임을 밝히고 맞는지 확인한다"
_ask = {"경로": "0 재구성 → 2 LLM 정규화 → 9 되묻기 → 끝", "의도_결과": "", "범위밖_사유_결과": ""}
_ans = {"경로": "0 재구성 → 3 의도 분류 → 5 답변 생성 → 끝", "의도_결과": "용어 설명", "범위밖_사유_결과": ""}
_out = {"경로": "0 재구성 → 3 의도 분류 → 8 범위 밖 → 끝", "의도_결과": "범위 밖", "범위밖_사유_결과": "일반"}
check("채점: 단정하지 않기 문항은 되물어도 정답, 답하면 의도로 (P-054)",
      RD.intent_check(_ask, "용어 설명", "", _FX, "C")[0] == 1 and RD.intent_check(_ans, "용어 설명", "", _FX, "D")[0] == 1
      and RD.intent_check(_out, "용어 설명", "", _FX, "C")[0] == 0 and RD.intent_check(_ans, "용어 설명", "", _FX, "B")[0] == 1)
check("채점: 오타 되묻기 문항(되묻는다)은 그대로 되묻기로 채점", RD.intent_check(_ans, "매매 판단 요청", "", "먼저 되묻는다", "C")[0] == 0)
_tests = {f: list(csv.DictReader(open(ROOT / "data" / "tests" / f, encoding="utf-8-sig"))) for f in ("dev_single.csv", "dev_multi.csv")}  # 측정용 파일은 읽지 않음
_fict = [r.get("id") or f"{r['시나리오']}-{r['턴']}" for f, rs in _tests.items() for r in rs if "추정임을 밝히고" in (r.get("기대_행동") or "")]
check("개발용 문항: 가상 신조어 첫 턴은 모두 단정하지 않기 기준 (P-054)",
      sorted(_fict) == sorted(["D38", "D39", "D40", "D41", "DM8-1"]), _fict)
check("개발용 문항: 되묻기만 정답인 문항 없음",
      not [r for f, rs in _tests.items() for r in rs if "되묻는다" in (r.get("기대_행동") or "")])
_st = {r["표준용어"]: r["설명"] for r in csv.DictReader(open(ROOT / "data" / "dictionary" / "standard_terms.csv", encoding="utf-8-sig"))}
check("사전 v0.6: 상한가·하한가에 신규 상장 첫날 가격 제한폭 (P-053)", "공모가의 4배(400%)" in _st["상한가"] and "공모가의 60%" in _st["하한가"]
      and all(len(v) <= 100 for v in _st.values()))

# 1차 검토 반영 (P-037·P-038·P-039)
r = dict_normalize("아주 민주당이다 이게 무슨 뜻이야?")
check("사전: 민주당 → 주가 하락 (P-038)", render_annotation("아주 민주당이다 이게 무슨 뜻이야?", r.norm_log).endswith("[풀이: 민주당=주가 하락]")
      and bool(load_dictionary().lookup("주가 하락")))
_n5 = (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8")
check("n5 지침: 확인 못 한 신조어는 짐작하지 않음·어려운 용어 괄호 풀이 (P-037)",
      '"[모름]" 한 줄만' in _n5 and "주당순이익(회사가 번 이익을 주식 1주당으로 나눈 값)" in _n5
      and "반박하거나 다른 뜻을 대지 않는다" in _n5)
jr = RD.judge_references(["골끄", "꼴박"], {"꼴박": "투자금을 크게 잃다"}, {"풀이_정답": "골끄→골크=골든크로스"})
check("채점 평가용 정답: 파일 우선, 없으면 정답지 풀이 (P-039)",
      jr == {"꼴박": "투자금을 크게 잃다", "골끄": "정답지 풀이: 골끄→골크=골든크로스"}, jr)
check("채점 평가용 정답: 풀이_정답 없으면 그대로", RD.judge_references(["x"], {}, {}) == {})

# 설정 D: 사전 우선, 사전 조회가 실패할 때만 노드 2 (P-042)
from src import config as CFG  # noqa: E402
_found = {"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["주가 흔들기"], "ticker": ""}
s = run("개미털기가 뭐예요?", mode="D", n3_intent=_found)
check("설정 D: 사전에 다 있으면 노드 2 없이 B와 같은 경로",
      s["path"] == ["0 재구성", "1 사전 정규화", "3 의도 분류", "4 용어 조회", "5 답변 생성", "6 검수(통과)", "끝"]
      and "n2_llm_normalize" not in CALLS, (s["path"], CALLS))
_miss = {"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["배당락"], "ticker": ""}
s = run("배당락이 뭐예요?", mode="D", n3_intent=[_miss, _miss])
check("설정 D: 사전에 없으면 노드 2 → 3 → 4 다시, 노드 2는 한 번만",
      s["path"] == ["0 재구성", "1 사전 정규화", "3 의도 분류", "4 용어 조회", "2 LLM 정규화", "3 의도 분류", "4 용어 조회",
                    "5 답변 생성", "6 검수(통과)", "끝"] and CALLS.count("n2_llm_normalize") == 1 and CALLS.count("n3_intent") == 2,
      (s["path"], CALLS))
s = run("도롱뇽장이 뭐야?", mode="D", n3_intent=_miss,
        n2_llm_normalize={"additions": [], "unresolved": [{"expr": "도롱뇽장", "reason": "처음 보는 표현"}]})
check("설정 D: 노드 2가 못 풀면 되묻기", s["path"][-2:] == ["9 되묻기", "끝"] and "n5_answer" not in CALLS, (s["path"], CALLS))
s = run("배당락이 뭐예요?", mode="B", n3_intent=_miss)
check("설정 B는 사전에 없어도 노드 2로 가지 않음", "n2_llm_normalize" not in CALLS and s["path"][-3:] == ["5 답변 생성", "6 검수(통과)", "끝"], CALLS)
check("설정 D: 조회 후 되묻기로 끝나면 사전 근거 없이 답한 것으로 세지 않음 (P-043)",
      RD.unknown_terms(run("도롱뇽장이 뭐야?", mode="D", n3_intent=_miss,
                           n2_llm_normalize={"additions": [], "unresolved": [{"expr": "도롱뇽장", "reason": "처음 보는 표현"}]})) == []
      and RD.unknown_terms(run("배당락이 뭐예요?", mode="D", n3_intent=[_miss, _miss])) == ["배당락"])
_fk = {"경로": "0 재구성 → 1 사전 정규화 → 3 의도 분류 → 4 용어 조회 → 5 답변 생성 → 끝", "의도_결과": "용어 설명", "범위밖_사유_결과": ""}
check("채점: 설정 D는 되묻기 문항을 되묻기로 채점 (P-042)", RD.intent_check(_fk, "용어 설명", "", "먼저 되묻는다", "D")[0] == 0
      and RD.intent_check(_fk, "용어 설명", "", "먼저 되묻는다", "B")[0] == 1)
check("설정 목록: run_dev와 config가 같음", RD.MODE_CHOICES == list(CFG.MODES) and tuple(RD.ASK_MODES) == tuple(CFG.ASK_MODES),
      (RD.MODE_CHOICES, list(CFG.MODES)))

# 매매 판단 안전망 (P-044): 규칙 단독 + 그래프
from src.safety import trading_ask  # noqa: E402
_dev_trade = [r["질문"] for f in ("dev_single.csv", "dev_multi.csv") for r in RD.read_csv(f) if r["의도_정답"] == "매매 판단 요청"]
_dev_other = [r["질문"] for f in ("dev_single.csv", "dev_multi.csv") for r in RD.read_csv(f) if r["의도_정답"] != "매매 판단 요청"]
check("안전망: 개발용 매매 판단 모두 잡음", all(trading_ask(q) for q in _dev_trade), [q for q in _dev_trade if not trading_ask(q)])
check("안전망: 개발용 나머지 잘못 잡지 않음", not any(trading_ask(q) for q in _dev_other), [q for q in _dev_other if trading_ask(q)])
_concept = ["회사가 돈을 잘 벌면 좋아?", "물타기 하면 평균단가는 어떻게 돼?", "손절하면 세금은 어떻게 돼?", "사람들이 왜 존버해야 한다고 해?",
            "익절이랑 손절 중에 뭐가 먼저야?", "매수 주문은 몇 시까지 돼?", "영끌하면 이자 부담이 얼마나 돼?", "분할 매수가 좋아?",
            "매수가 뭐야?", "손절라인이 뭐야?", "존버해도 손해 보는 경우가 있다는 게 무슨 말이야?"]
check("안전망: '되는지 알려줘' 꼴의 판단 요청은 잡음", trading_ask("지금 사도 되는지 알려줘") and trading_ask("너라면 살 거야?"))
check("안전망: 개념 질문은 잡지 않음 (과잉 차단)", not any(trading_ask(q) for q in _concept), [q for q in _concept if trading_ask(q)])
_term = {"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["주가 흔들기"], "ticker": ""}
s = run("엔솔 지금 사도 돼?", mode="B", n3_intent=_term)
check("안전망: 용어 설명으로 분류돼도 매매 판단으로 올리고 용어는 그대로", s["intent"] == "매매 판단 요청"
      and s["intent_override"] == "용어 설명 → 매매 판단 요청" and s["terms"] == ["주가 흔들기"] and "4 용어 조회" in s["path"], s["intent"])
s = run("물타기 하면 평균단가는 어떻게 돼?", mode="B", n3_intent=_term)
check("안전망: 개념 질문은 그대로 용어 설명", s["intent"] == "용어 설명" and s["intent_override"] == "", s["intent"])
_out = {"intent": "범위 밖", "out_reason": "일반", "intent_reason": "", "terms": [], "ticker": ""}
s = run("엔솔 지금 사도 돼?", mode="B", n3_intent=_out)
check("안전망: 범위 밖 판정은 건드리지 않음", s["intent"] == "범위 밖" and s["intent_override"] == "", s["intent"])

# 설정 D: 되묻기 다음 턴은 노드 2부터 (P-045)
_t = "d-follow-1"
run("도롱뇽장이 뭐야?", mode="D", thread=_t, n3_intent=_miss,
    n2_llm_normalize={"additions": [], "unresolved": [{"expr": "도롱뇽장", "reason": "처음 보는 표현"}]})
s = run("주가가 계속 오른다는 뜻 같아", mode="D", thread=_t, n3_intent=_miss, n0_rewrite="도롱뇽장은 주가가 계속 오른다는 뜻 같아")
check("설정 D: 앞 턴이 되묻기면 이번 턴은 노드 2부터", s["path"][:4] == ["0 재구성", "1 사전 정규화", "2 LLM 정규화", "3 의도 분류"]
      and CALLS.count("n2_llm_normalize") == 1, (s["path"], CALLS))
s = run("배당락이 뭐예요?", mode="D", thread=_t, n3_intent=[_miss, _miss], n0_rewrite="배당락이 뭐예요?")
check("설정 D: 앞 턴이 되묻기가 아니면 원래대로 (조회 실패 때만 노드 2)", s["path"][:4] == ["0 재구성", "1 사전 정규화", "3 의도 분류", "4 용어 조회"], s["path"])

# 반복 탭 (P-046)
_r1 = ([{"id": "Z1", "질문": "q", "의도_일치": 1, "의도_결과": "용어 설명", "경로": "… 5 답변 생성 → 끝"}], [])
_r2 = ([{"id": "Z1", "질문": "q", "의도_일치": 0, "의도_결과": "매매 판단 요청", "경로": "… 5 답변 생성 → 끝", "안전망_작동": "x"}], [])
_rl, _rs = RD.build_repeat({"C": [_r1, _r2], "B": [_r1, _r1]})
check("반복 탭: 결과가 다르면 흔들림, 같으면 표시 없음", _rs == {"C": (1, 1), "B": (0, 1)}
      and _rl[1][4] == "1/2" and _rl[1][7] == "1/2" and _rl[1][9] == "흔들림" and _rl[2][9] == "", (_rs, _rl))

# 같은 분모로 조회 적중 비교 (P-041): C가 되묻기로 멈춘 문항은 모든 설정의 분모에서 빠진다
_cl_rows = {
    "B": ([{"id": "Y1", "의도_일치": 1, "조회_적중": "1/1", "경로": "… 6 검수(통과) → 끝"},
           {"id": "Y2", "의도_일치": 1, "조회_적중": "0/1", "경로": "… 6 검수(통과) → 끝"}],
          [{"시나리오": "Z", "턴": 1, "의도_일치": 1, "조회_적중": "1/2", "경로": "… 끝"}]),
    "C": ([{"id": "Y1", "의도_일치": 1, "조회_적중": "1/1", "경로": "… 6 검수(통과) → 끝"},
           {"id": "Y2", "의도_일치": 1, "조회_적중": "", "경로": "… 9 되묻기 → 끝"}],
          [{"시나리오": "Z", "턴": 1, "의도_일치": 1, "조회_적중": "2/2", "경로": "… 끝"}])}
_n, _cl = RD.common_lookup(_cl_rows)
check("같은 분모: 모든 설정이 조회한 문항만 (P-041)", _n == 2 and _cl["B"]["조회 적중"] == "2/3" and _cl["C"]["조회 적중"] == "3/3"
      and _cl["B"]["사전 근거 없이 답한 용어"] == 1 and _cl["C"]["조회 전에 멈춤"] == 1 and _cl["B"]["조회 전에 멈춤"] == 0, (_n, _cl))
check("같은 분모: 비교 탭에 줄 추가", any(x[0] == "단발+멀티턴 · 같은 분모" and x[3] == "조회 적중 (용어 수)"
                                     for x in RD.build_compare(_cl_rows)))

# 짐작 갈래 없앰 (P-092, 예전 P-056): 노드 2가 짐작만 한 표현은 풀이로 쓰지 않고 되묻는다. 다음 턴 D는 노드 2부터
from src.fixed_messages import clarify_message, dont_know_message, josa_eun_neun, CLARIFY_AGAIN, TRADING_NOTICE  # noqa: E402
_guess = {"additions": [{"expr": "달팽이장", "meaning": "주가 흔들기", "kind": "신조어", "source": "모델", "confidence": "짐작"}], "unresolved": []}
_orig = {"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["달팽이장"], "ticker": ""}
s = run("요즘 달팽이장이라던데 무슨 뜻이야?", mode="C", thread="guess-1", n2_llm_normalize=_guess, n3_intent=_orig)
check("짐작은 풀이로 쓰지 않고 되묻는다 (P-092)", "달팽이장=" not in s["annotated_query"] and s["path"][-2] == "9 되묻기"
      and s["final_answer"] == clarify_message(["달팽이장"]) and "n5_answer" not in CALLS
      and s["history"][-1]["clarified"] is True and s["history"][-1]["asked"] == ["달팽이장"], (s["annotated_query"], s["path"], s["final_answer"]))
_t = "guess-d"
s = run("요즘 달팽이장이라던데 무슨 뜻이야?", mode="D", thread=_t, n2_llm_normalize=_guess, n3_intent=[_orig, _orig])
check("설정 D: 못 찾은 용어를 LLM이 짐작만 했으면 되묻기 (P-092)", s["path"][-2] == "9 되묻기" and "뜻일 수도" not in s["final_answer"], s["path"])
_user = {"additions": [{"expr": "달팽이장", "meaning": "주가 흔들기", "kind": "신조어", "source": "사용자 설명"}], "unresolved": []}
s = run("아주 느리게 오르는 장을 그렇게 부른대", mode="D", thread=_t, n3_intent=_orig, n0_rewrite="아주 느리게 오르는 장을 달팽이장이라고 부른대",
        n2_llm_normalize=_user)
check("설정 D: 앞 턴이 되묻기면 이번 턴은 노드 2부터 (P-045)", s["path"][:4] == ["0 재구성", "1 사전 정규화", "2 LLM 정규화", "3 의도 분류"], s["path"])
_miss2 = {"intent": "용어 설명", "out_reason": "", "intent_reason": "", "terms": ["배당락"], "ticker": ""}
s = run("달팽이장이라던데 배당락이 뭐야?", mode="D", n2_llm_normalize=_guess, n3_intent=[_miss2, _miss2])
check("설정 D: 묻지 않은 표현의 짐작은 버리고 물은 용어에 답한다 (P-092)", "9 되묻기" not in s["path"] and "달팽이장=" not in s["annotated_query"]
      and s["path"][-3] == "5 답변 생성", (s["path"], s["annotated_query"]))
_sure = {"additions": [{"expr": "달팽이장", "meaning": "주가 흔들기", "kind": "신조어", "source": "모델", "confidence": "확신"}], "unresolved": []}
s = run("요즘 달팽이장이라던데 무슨 뜻이야?", mode="C", n2_llm_normalize=_sure, n3_intent=_orig)
check("확신 풀이는 (추정) 그대로, 되묻기 표시 없음", "달팽이장=주가 흔들기(추정)" in s["annotated_query"]
      and s["asked_back"] is False and s["history"][-1]["clarified"] is False, s["annotated_query"])
s = run("달팽이장은 주가 흔들기래", mode="C", n2_llm_normalize=_user, n3_intent=_orig)
check("사용자 설명 속 사전 용어 조회 (P-088)", s["user_words_terms"] and s["user_words_terms"][0]["standard"] == "주가 흔들기", s.get("user_words_terms"))

# 되묻기 조사 (P-059)
check("되묻기 문구 조사: 받침 있으면 은, 없으면 는", josa_eun_neun("뽀글장") == "은" and josa_eun_neun("빛투") == "는" and josa_eun_neun("ETF") == "는"
      and clarify_message(["뽀글장"]).startswith("'뽀글장'은 확인되지 않은 단어예요") and clarify_message(["빛투", "뽀글장"]).startswith("'빛투', '뽀글장'은 "))

# 채점 (P-055): 추정 표시 후 단정은 되물음 아님, 조건부 표준 용어 안내 칸
_fake_j = [{"asked_back": True, "hedged_guide": True, "meaning_ok": None, "no_false_fact": True, "beginner_ok": True, "comment": "짐작 + 조건부 안내"},
           {"asked_back": False, "hedged_guide": True, "meaning_ok": False, "no_false_fact": False, "beginner_ok": True, "comment": "추정 표시 후 단정"}]
JG.call_llm = lambda node, system, user, model=None: (json.dumps(_fake_j.pop(0), ensure_ascii=False), {"cost_usd": 0.0})
_j = JG.judge_row("q", ["달팽이장"], "답", None, "달팽이장=주가 흔들기(짐작)")
check("채점: 되물으며 조건부 안내 → 조건부안내 칸에 용어, 뜻은 해당 없음 (P-055)", _j["사전밖_되물음"] == "달팽이장" and _j["사전밖_조건부안내"] == "달팽이장" and _j["사전밖_뜻일치"] == "", _j)
_j = JG.judge_row("q", ["달팽이장"], "답", None, "달팽이장=주가 흔들기(짐작)")
check("채점: 추정 표시 후 단정은 되물음 아님, 조건부 안내도 세지 않음", _j["사전밖_되물음"] == "" and _j["사전밖_조건부안내"] == "" and _j["사전밖_뜻일치"] == 0 and _j["사전밖_틀린사실없음"] == 0, _j)
_jp = (ROOT / "prompts" / "judge_unknown_term.md").read_text(encoding="utf-8")
check("채점 지침: 추정 표시 후 단정·사용자 설명 쓰임 덧붙임·hedged_guide (P-055)", "추정 표시 후 단정" in _jp and "hedged_guide" in _jp and "일반적인 쓰임" in _jp)
_n5p = (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8")
_n2p = (ROOT / "prompts" / "n2_llm_normalize.md").read_text(encoding="utf-8")
_n3p = (ROOT / "prompts" / "n3_intent.md").read_text(encoding="utf-8")
check("지침: 노드 2 확신/짐작/아는 말, 노드 5에 짐작 단락 없음·사전 밖 안내는 시스템이·단정하지 않는 말투·들으신 뜻 (P-092~P-094)",
      '"confidence": "확신|짐작"' in _n2p and '"known"' in _n2p and "(짐작)" in _n3p and "원래 표현" in _n3p
      and "짐작한 뜻 (" not in _n5p and "뜻일 수도 있는데" not in _n5p and "시스템이 답변 앞에 붙이므로" in _n5p
      and "쓰이는 것으로 보여요" in _n5p and "들으셨군요" in _n5p and "일반적인 쓰임을 덧붙이지 않는다" in _n5p)
check("지침: 노드 3 범위 밖 종목 정보 정리·영향 질문은 용어 설명 (P-058)", "정보를 정리하거나 소개해 달라는 요청" in _n3p and "영향이나 결과" in _n3p)
_dev_user = [r for f, rs in _tests.items() for r in rs if "일반적인 쓰임" in (r.get("기대_행동") or "")]
check("개발용 문항: 사용자 설명 턴에 쓰임 덧붙이지 않기 기준 (P-055)", [f"{r['시나리오']}-{r['턴']}" for r in _dev_user] == ["DM8-2"], _dev_user)

# 노드별 모델 (P-061)
_nm = CFG.set_node_models("n0,n2,n3,n5=openai/gpt-6-luna")
check("노드별 모델: 앞부분 이름으로 지정, 검수는 기본 모델, 다시 쓰기는 답변 모델을 따름",
      _nm == {"n0_rewrite": "openai/gpt-6-luna", "n2_llm_normalize": "openai/gpt-6-luna", "n3_intent": "openai/gpt-6-luna", "n5_answer": "openai/gpt-6-luna"}
      and CFG.model_for("n6_compliance") == CFG.current_model() and CFG.model_for("n5_answer_retry") == "openai/gpt-6-luna"
      and CFG.node_models_label() == "n0·n2·n3·n5 openai/gpt-6-luna", (_nm, CFG.node_models_label()))
try:
    CFG.set_node_models("n9=x"); _bad = False
except ValueError:
    _bad = True
check("노드별 모델: 모르는 노드 이름은 오류", _bad)
CFG.set_node_models("")
check("노드별 모델: 비우면 모두 기본 모델", CFG.NODE_MODELS == {} and CFG.model_for("n0_rewrite") == CFG.current_model())

# 규칙 분류 (P-062)
from src.fast_path import simple_term_question  # noqa: E402


def _fp(q):
    r = dict_normalize(q)
    return simple_term_question(q, r.norm_log, r.typo_confirm, r.unresolved)


check("규칙 분류: 표준 용어 그대로", _fp("PER이 뭐야?") == "PER" and _fp("상한가가 무슨 뜻이야") == "상한가", (_fp("PER이 뭐야?"), _fp("상한가가 무슨 뜻이야")))
check("규칙 분류: 사전 풀이로 표준 용어에 닿는 말", _fp("개미털기가 뭐예요?") == "주가 흔들기" and _fp("시총 뜻 알려줘") == "시가총액", (_fp("개미털기가 뭐예요?"), _fp("시총 뜻 알려줘")))
check("규칙 분류: 사전에 닿지 않는 말은 노드 3으로", _fp("코인 스테이킹이 뭐야?") is None and _fp("배당락이 뭐예요?") is None and _fp("횡보가 뭐야?") is None)
check("규칙 분류: 종목 약어·오타·용어 둘·판단 질문은 노드 3으로",
      _fp("하닉이 뭐야?") is None and _fp("게미가 무슨 뜻이야") is None and _fp("손절이랑 익절 차이가 뭐야?") is None
      and _fp("물렸는데 물타기 하는 게 맞아?") is None and _fp("삼전 물렸는데 어떡해?") is None)
_dev_not_term = [r["질문"] for r in RD.read_csv("dev_single.csv") if r["의도_정답"] != "용어 설명"]
check("규칙 분류: 개발용 용어 설명 아닌 문항을 잡지 않음 (과잉 차단 0)", not any(_fp(q) for q in _dev_not_term), [q for q in _dev_not_term if _fp(q)])
_dev_term = [r["질문"] for r in RD.read_csv("dev_single.csv") if r["의도_정답"] == "용어 설명"]
_fp_hits = [q for q in _dev_term if _fp(q)]
check("규칙 분류: 개발용 용어 설명 문항 중 사전 용어만 묻는 것(D01·D03)을 잡음", sorted(_fp_hits) == ["개미털기가 뭐예요?", "시총 뜻 알려줘"], _fp_hits)
CFG.set_fast_path(True)
s = run("개미털기가 뭐예요?", mode="B")
check("규칙 분류 켜짐: 노드 3 LLM 없이 용어 설명 + 표준 용어, 경로에 (규칙)", "n3_intent" not in CALLS and s["intent"] == "용어 설명"
      and s["terms"] == ["주가 흔들기"] and "3 의도 분류(규칙)" in s["path"] and s["term_info"][0]["found"] and s["intent_reason"].startswith("[규칙]"), (CALLS, s["path"]))
s = run("개미털기가 뭐예요?", mode="A", n3_intent=_found)
check("규칙 분류 켜짐: 설정 A는 그대로 노드 3 LLM", "n3_intent" in CALLS)
s = run("배당락이 뭐예요?", mode="D", n3_intent=[_miss, _miss])
check("규칙 분류 켜짐: 사전에 없는 말은 노드 3 LLM", "n3_intent" in CALLS and "3 의도 분류(규칙)" not in s["path"])
CFG.set_fast_path(False)
s = run("개미털기가 뭐예요?", mode="B", n3_intent=_found)
check("규칙 분류 꺼짐(기본): 노드 3 LLM", "n3_intent" in CALLS and "3 의도 분류(규칙)" not in s["path"])
check("채점: 규칙 분류 경로도 답변 턴으로 봄", RD.answered({"path": ["0 재구성", "1 사전 정규화", "3 의도 분류(규칙)", "4 용어 조회", "5 답변 생성", "끝"]}))
_n3p2 = (ROOT / "prompts" / "n3_intent.md").read_text(encoding="utf-8")
check("지침: 노드 3 (추정) 풀이에서 일반 단어 하나만 남기지 않음 (P-060)", "풀매수" in _n3p2 and "일반적인 한 단어" in _n3p2)

# 랭퓨즈 준비: 설정 하나짜리 결과 엑셀도 읽음 (P-067)
import tempfile  # noqa: E402
from openpyxl import Workbook  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
from langfuse_setup import read_result as LS_read  # noqa: E402
_wb = Workbook(); _ws = _wb.active; _ws.title = "요약"; _ws.append(["설정", "D (사전 우선+필요 시 LLM)"])
for _t in ("단발", "멀티턴"):
    _sh = _wb.create_sheet(_t); _sh.append(["id", "trace_id"]); _sh.append(["S01" if _t == "단발" else "M1", "t1"])
_tmp = pathlib.Path(tempfile.mkdtemp()) / "one.xlsx"; _wb.save(_tmp)
_rr = LS_read(_tmp)
check("랭퓨즈 준비: 설정 하나짜리 결과(탭 단발·멀티턴)도 설정 D로 읽음 (P-067)", list(_rr) == ["D"] and len(_rr["D"][0]) == 1 and len(_rr["D"][1]) == 1, _rr)

# 매매 판단 안내 받침 (P-068): 검수가 질문 기준으로 R1을 보고, 남은 위반이 R1뿐이면 노드 7이 안내를 붙여 답을 살림
from src.fixed_messages import TRADING_CLOSING, TRADING_NOTICE  # noqa: E402
_U6 = []
R1FAIL = {"verdict": "위반", "violations": [{"item": "R1", "sentence": "답", "reason": "안내 없음"}]}
FAKE.clear()
FAKE["n6_compliance"] = lambda u: (_U6.append(u), PASS)[1]
m6.judge("답", "용어 설명", "삼전 지금 사도 돼?")
check("검수: 질문을 넘기면 용어 설명에도 R1(질문 기준) + [질문] (P-068)",
      "R1(질문 기준)" in _U6[-1] and "[질문]\n삼전 지금 사도 돼?" in _U6[-1], _U6[-1])
m6.judge("답", "용어 설명")
check("검수: 질문을 안 넘기면 예전과 같음 (R1·[질문] 없음)", "R1" not in _U6[-1] and "[질문]" not in _U6[-1], _U6[-1])
m6.judge("답", "매매 판단 요청", "삼전 지금 사도 돼?")
check("검수: 매매 판단 요청은 예전과 같은 R1, [질문] 없음",
      "C5, R1" in _U6[-1] and "R1(질문 기준)" not in _U6[-1] and "[질문]" not in _U6[-1], _U6[-1])
FAKE["n6_compliance"] = R1FAIL
_r6, _ = m6.judge("답", "용어 설명", "삼전 지금 사도 돼?")
check("검수: 질문 기준이면 용어 설명의 R1 위반을 남김", not _r6["passed"] and _r6["violations"][0]["item"] == "R1", _r6)
_r6, _ = m6.judge("답", "용어 설명")
check("검수: 질문이 없으면 R1 위반을 지움 (예전과 같음)", not _r6["passed"] and _r6["violations"][0]["item"] == "미상", _r6)
_U6.clear()
s = run("계속 존버하는 게 맞을까?", n3_intent={"intent": "용어 설명", "terms": [], "ticker": ""},
        n5_answer="'존버'는 버티는 것을 뜻해요.", n6_compliance=lambda u: (_U6.append(u), R1FAIL)[1])
check("그래프: 검수에 재구성 질문이 넘어감 (P-068)", all("[질문]\n계속 존버하는 게 맞을까?" in u for u in _U6) and len(_U6) == 3, _U6[:1])
check("노드 7: 재생성 뒤에도 R1만 남으면 안내를 앞에 붙여 답을 살림 (P-068)",
      s["final_answer"].startswith(TRADING_NOTICE) and "'존버'는 버티는 것을 뜻해요." in s["final_answer"]
      and s["final_answer"].endswith(TRADING_CLOSING) and "7 안전 답변(안내 덧붙임)" in s["path"], (s["final_answer"], s["path"]))
s = run("텐배거 될 종목 찍어줘", n3_intent={"intent": "매매 판단 요청", "terms": ["10배 상승 종목"], "ticker": ""}, n6_compliance=FAIL)
check("노드 7: C1 위반이 남으면 그대로 안전 답변", s["final_answer"] == SAFE_ANSWER and "7 안전 답변" in s["path"], s["path"])
_n5p = (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8")
_n6p = (ROOT / "prompts" / "n6_compliance.md").read_text(encoding="utf-8")
_same = "특정 상황에서 어떻게 할지(사고팔기·버티기)를 묻는 것이 아니면 해당하지 않는다."
check("지침: 답변·검수가 같은 '매매 판단을 묻는 질문' 기준 (P-068)",
      "[의도]와 상관없이 적용" in _n5p and "R1(질문 기준)" in _n6p and _same in _n5p and _same in _n6p)

# ---------------------------------------------------------------------------
# 4차 개발용 결과로 고친 것 (P-069~P-077, 2026.11.12)
from src.fixed_messages import OUT_OF_SCOPE, COMFORT_TAIL  # noqa: E402
from src.dictionary import near_words  # noqa: E402
from src.safety import crisis_expression, weak_crisis_expression  # noqa: E402

# P-071 범위 밖(일반) 고정 문구에 판단 불가 안내
s = run("코인 스테이킹이 뭐야?", n3_intent={"intent": "범위 밖", "out_reason": "일반", "terms": [], "ticker": ""})
check("범위 밖(일반) 문구에 판단 불가 안내 (P-071)", s["final_answer"] == OUT_OF_SCOPE["일반"]
      and "사거나 파는 판단이나 시장 전망도 해드릴 수 없어요" in s["final_answer"], s["final_answer"])

# P-075 힘든 마음
check("위험 표현 규칙: 잡음", all(crisis_expression(q) for q in ("주식 때문에 살기가 싫다", "다 잃고 그냥 사라지고 싶네", "요즘 죽고 싶다",
                                                                "계좌 보면 그냥 다 끝내고 싶어", "인생 끝내고 싶다")))
check("위험 표현 규칙: 과장으로 쓰는 말은 고정 문구로 받지 않음 (P-083)",
      not any(crisis_expression(q) for q in ("목숨 같은 돈인데 팔아야 해?", "목숨 걸고 존버 중", "오늘 매매는 여기서 끝내고 싶다",
                                             "자살골 넣었네 물타기가 뭐야?", "물려서 죽을 것 같아", "주식 우울증이 뭐야?")))
check("약한 위험 표현: 죽을 것 같·우울증만 (P-083)",
      weak_crisis_expression("물려서 죽을것 같아") and weak_crisis_expression("주식 우울증이 뭐야?")
      and not weak_crisis_expression("목숨 같은 돈인데 팔아야 해?") and not weak_crisis_expression("오늘 매매는 여기서 끝내고 싶다"))
check("위험 표현 규칙: 하소연·일상 문장은 안 잡음",
      not any(crisis_expression(q) for q in ("존버하다가 반토막 났네", "물렸는데 어떡해", "하한가 맞고 멘탈 나갔다")))
s = run("주식 때문에 살기가 싫다", mode="D", n3_intent={"intent": "용어 설명", "terms": [], "ticker": ""})
check("힘든 마음: LLM 분류 전에 규칙으로, 상담 안내 고정 문구 (P-075)",
      "3 의도 분류(위험 표현)" in s["path"] and s["path"][-2] == "8 범위 밖(힘든 마음)" and "109" in s["final_answer"]
      and "n3_intent" not in CALLS, (s["path"], CALLS))
s = run("요즘 아무것도 하기 싫어", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "힘든 마음", "terms": [], "ticker": ""})
check("힘든 마음: LLM이 고른 사유도 같은 문구", s["path"][-2] == "8 범위 밖(힘든 마음)" and "109" in s["final_answer"], s["path"])

s = run("물려서 죽을 것 같아", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""},
        n5_answer="물린 상태가 이어져 많이 괴로우시겠어요.")
check("약한 위험 표현: 하소연 답 끝에 상담 안내 한 문장 (P-083)",
      "5 답변 생성(하소연)" in s["path"] and s["final_answer"].endswith(CARE_MESSAGE), s["final_answer"])
s = run("물려서 죽을 것 같아", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "힘든 마음", "terms": [], "ticker": ""})
check("약한 위험 표현: 힘든 마음 문구에는 상담 안내를 또 붙이지 않음", s["final_answer"] == OUT_OF_SCOPE["힘든 마음"], s["final_answer"])
s = run("목숨 같은 돈인데 팔아야 해?", mode="D", n3_intent={"intent": "매매 판단 요청", "terms": [], "ticker": ""},
        n5_answer="지금 팔아야 하는지는 판단해드릴 수 없어요. 결정 전에 충분히 알아보시는 걸 권해요.")
check("과장 표현(목숨 같은)에는 상담 안내를 붙이지 않음", CARE_MESSAGE not in s["final_answer"] and "109" not in s["final_answer"], s["final_answer"])

# P-070 하소연
_hs = {"intent": "범위 밖", "out_reason": "하소연", "terms": ["손실 감수 장기 보유"], "ticker": ""}
s = run("존버하다가 결국 반토막 났네", mode="D", n3_intent=_hs, n5_answer="반토막이면 정말 속상하셨겠어요.")
check("하소연: 공감 한 문장 + 서비스 안내 + 용어 제안, 검수 거침 (P-070)",
      s["final_answer"] == f"반토막이면 정말 속상하셨겠어요.\n{COMFORT_TAIL} '존버' 뜻이 궁금하시면 물어봐 주세요."
      and "5 답변 생성(하소연)" in s["path"] and "6 검수(통과)" in s["path"] and "4 용어 조회" not in s["path"], (s["final_answer"], s["path"]))
s = run("오늘도 파란불이다", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""}, n5_answer="")
check("하소연: 공감 문장이 비면 고정 문장, 용어 없으면 일반 제안",
      s["final_answer"].startswith("많이 속상하셨겠어요.") and s["final_answer"].endswith("궁금한 주식 용어가 있으면 물어봐 주세요."), s["final_answer"])
s = run("존버하다가 결국 반토막 났네", mode="D", n3_intent=_hs, n5_answer=["곧 다시 오를 거예요.", "많이 속상하셨겠어요."],
        n6_compliance=[FAIL, PASS])
check("하소연: 검수 위반이면 공감 문장을 다시 씀", s["final_answer"].startswith("많이 속상하셨겠어요.") and s["retry_count"] == 1
      and "5 답변 생성(하소연, 재생성 1)" in s["path"], s["path"])

s = run("물려서 손절도 못 하고 있어", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""},
        n5_answer="손절도 못 하고 계시니 많이 답답하시겠어요.")
check("하소연 용어 제안은 사전 기본형 (P-084)", "'물리다' 뜻이 궁금하시면" in s["final_answer"] and "'물려'" not in s["final_answer"],
      s["final_answer"])

# P-073 되묻기 오타라도 원래 말이 같은 문장에 있으면 되묻지 않음
r = dict_normalize("빛투는 빚투 말한 거야")
check("되묻기 오타: 원래 말이 같은 문장에 있으면 되묻지 않음 (P-073)",
      not r.unresolved and any(x["expr"] == "빚투" for x in r.norm_log), (r.unresolved, r.norm_log))
check("되묻기 오타: 원래 말이 없으면 예전처럼 되묻기", dict_normalize("빛투 해도 돼?").unresolved[0]["expr"] == "빛투")

# P-081 비유 예외를 뺌: 사전 은어는 문장 속 뜻과 상관없이 다 푼다 (답에 쓸지는 노드 5)
for q, w in (("총알처럼 빠르게 오른다는데 급등이 뭐야?", "=투자 여유 자금"), ("개미처럼 부지런히 모은 돈인데 배당이 뭐야?", "=개인투자자"),
             ("깡통 같은 스피커 버리다가 생각났는데 예수금이 뭐야?", "=원금 전액 손실 계좌"),
             ("뉴스에서 정치 세력 얘기가 나왔는데 공매도가 뭐야?", "=대량 매매 주체"), ("단타 같은 거 말고 장기 투자는 뭐야?", "=단기 매매"),
             ("존버 같이 하자는 말 들었어", "=손실 감수 장기 보유")):
    a, _ = ann(q)
    check(f"사전 은어는 비유·다른 뜻이어도 풂 (P-081): {q[:8]}", w in a, a)
a, _ = ann("세력권 다툼이 심하네")
check("오탐 예외(다른 단어 세력권)는 그대로 풀지 않음", "[풀이" not in a, a)
_n5x = (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8")
check("지침: 노드 5 묻지 않은 은어는 주식 뜻으로 쓰였을 때만 (P-082)",
      "뜻을 묻지 않은 표현은 질문 문장에서 주식 뜻으로 쓰였을 때만" in _n5x and "뜻을 물은 표현은 늘 사전 풀이대로" in _n5x
      and "정치 세력" not in _n5x and "깡통 같은" not in _n5x)

# P-069 사전 다시 잇기
check("자모 하나 차이 후보 (잇기 2)", [w for w, _ in near_words("공메도")] == ["공매도"] and [w for w, _ in near_words("시촌")] == ["시총"])
check("자모 비교 예외: 일상어·실제 은어", near_words("본전") == [] and near_words("시간") == [] and near_words("마오", loose=True) == [])
check("자모 두 개 차이는 후보로만 (loose)", near_words("쥽쥽") == [] and [w for w, _ in near_words("쥽쥽", loose=True)] == ["줍줍"])


def _n3_typo(first, after):
    return lambda u: {"intent": "용어 설명", "terms": [after if "(오타로 보임)" in u else first], "ticker": ""}


s = run("떡쌍이 뭐야?", mode="D", n3_intent=_n3_typo("떡쌍", "떡상"))
check("잇기 2: 은어와 자모 하나 차이 → LLM 없이 사전 풀이 + 확인 문구 (P-069)",
      "2 사전 잇기" in s["path"] and "n2_llm_normalize" not in CALLS and s["typo_confirm"] == [{"typo": "떡쌍", "original": "떡상"}]
      and "떡쌍=떡상(오타로 보임)" in s["annotated_query"], (s["path"], s["typo_confirm"], s["annotated_query"]))
s = run("공메도가 뭐야?", mode="D", n3_intent=_n3_typo("공메도", "공매도"),
        n2_llm_normalize={"additions": [], "unresolved": [{"expr": "공메도", "reason": "모르는 말"}]})
check("잇기 2: 표준 용어와 자모 하나 차이 → LLM이 모른다고 밝히면 LLM 뒤에 잇기 (P-080·P-089)",
      "2 사전 잇기" in s["path"] and "n2_llm_normalize" in CALLS and s["typo_confirm"] == [{"typo": "공메도", "original": "공매도"}]
      and s["term_info"][0]["found"] and "공메도=공매도(오타로 보임)" in s["annotated_query"], (s["path"], s["typo_confirm"], s["annotated_query"]))
s = run("고가가 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["고가"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "고가", "meaning": "하루 중 가장 높은 가격", "kind": "용어", "confidence": "확신"}], "unresolved": []})
check("잇기 2: LLM이 확신으로 푼 실제 말은 표준 용어의 오타로 읽지 않음 (P-080, 고가≠호가)",
      not s["typo_confirm"] and "호가" not in s["annotated_query"] and "2 사전 잇기" not in s["path"], (s["path"], s["annotated_query"]))
s = run("떡쌍이 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["떡쌍"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "떡쌍", "meaning": "주가의 급격한 폭등", "kind": "신조어", "confidence": "짐작"}], "unresolved": []})
check("잇기 2: 은어 오타는 LLM 짐작보다 사전이 먼저", "떡쌍=떡상(오타로 보임)" in s["annotated_query"] and "n2_llm_normalize" not in CALLS,
      (s["path"], s["annotated_query"]))
s = run("예슈금이 뭐야?", mode="D", n3_intent=_n3_typo("예슈금", "예수금"),
        n2_llm_normalize={"additions": [{"expr": "예슈금", "meaning": "맡겨 둔 돈", "kind": "신조어", "confidence": "짐작"}], "unresolved": []})
check("잇기 2: LLM 짐작이면 표준 용어 오타로 바꿈 (짐작 풀이는 버림)",
      "예슈금=예수금(오타로 보임)" in s["annotated_query"] and "맡겨 둔 돈" not in s["annotated_query"]
      and s["typo_confirm"] == [{"typo": "예슈금", "original": "예수금"}], (s["path"], s["annotated_query"]))
s = run("쏜절이 뭐야?", mode="D", n3_intent=_n3_typo("손절", "손절매"))
check("잇기 1: LLM이 은어로 고쳐 넘긴 말 → 사전 풀이 (P-069)",
      "쏜절=손절(오타로 보임)=손절매" in s["annotated_query"] and s["term_info"][0]["found"]
      and s["typo_confirm"] == [{"typo": "쏜절", "original": "손절"}], (s["annotated_query"], s["term_info"]))
s = run("쥽쥽이 뭐야?", mode="D", n3_intent=_n3_typo("쥽쥽", "저가 매수"),
        n2_llm_normalize={"additions": [{"expr": "쥽쥽", "meaning": "줍줍(저가 매수)", "kind": "신조어", "confidence": "확신"}], "unresolved": []})
check("잇기 1: LLM 풀이 첫 낱말이 사전 말이면 사전 풀이", "쥽쥽=줍줍(오타로 보임)=저가 매수" in s["annotated_query"] and s["term_info"][0]["found"],
      s["annotated_query"])
s = run("본전이 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["본전"], "ticker": ""})
check("잇기: 예외 일상어는 잇지 않고 LLM으로", "2 사전 잇기" not in s["path"] and "n2_llm_normalize" in CALLS, s["path"])
s = run("총알배송 받았는데 급등이 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["총알", "급등"], "ticker": ""})
check("잇기 1: 질문에 그대로 있는 은어(오탐 예외로 뺀 말)는 다시 잇지 않음", "총알=투자 여유 자금" not in s["annotated_query"]
      and not s["unresolved"], (s["annotated_query"], s["unresolved"]))
s = run("공메도가 뭐야?", mode="A", n3_intent={"intent": "용어 설명", "terms": ["공메도"], "ticker": ""})
check("설정 A: 사전 잇기 없음 (기준선 유지)", not s["term_info"][0]["found"] and "2 사전 잇기" not in s["path"], s["path"])

# P-072 후보로만 묻기 + 다음 턴 확인
s = run("고가가 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["고가"], "ticker": ""},
        n2_llm_normalize={"additions": [], "unresolved": [], "known": ["고가"]})
check("LLM이 아는 말로 적은 말은 오타로 읽지 않음 (P-089·P-093, 고가≠호가)",
      not s["typo_confirm"] and "호가" not in s["annotated_query"] and "9 되묻기" not in s["path"], (s["path"], s["annotated_query"]))
s = run("이제 바닥 찍은 거 같지?", mode="D", n3_intent={"intent": "매매 판단 요청", "terms": ["바닥"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "바닥 찍은", "meaning": "최저점에 도달한", "kind": "관용구", "confidence": "확신"}], "unresolved": []})
check("LLM이 푼 표현 안에 든 말은 후보로 묻지 않음 (P-089, 바닥≠배당)", "9 되묻기" not in s["path"] and "배당" not in s["final_answer"],
      (s["path"], s["final_answer"]))
s = run("쥽쥽이 뭐야?", mode="D", thread="thread-cand", n3_intent={"intent": "용어 설명", "terms": ["쥽쥽"], "ticker": ""},
        n2_llm_normalize={"additions": [], "unresolved": [{"expr": "쥽쥽", "reason": "모르는 말"}]})
check("후보로만 묻기: LLM도 모르면 후보를 보여 주며 되묻기 (P-072)",
      s["path"][-2] == "9 되묻기" and "혹시 '줍줍'을 말씀하신 건가요?" in s["final_answer"]
      and s["history"][-1]["candidates"] == [{"expr": "쥽쥽", "candidate": "줍줍"}], (s["path"], s["final_answer"]))
s = run("맞아요", mode="D", thread="thread-cand", n0_rewrite="맞아요", n3_intent=_n3_typo("쥽쥽", "저가 매수"))
check("후보 되묻기 다음 '맞아요' → 그 후보로 설명, LLM 풀이 없음",
      "2 확인 답" in s["path"] and "n2_llm_normalize" not in CALLS and s["term_info"] and s["term_info"][0]["found"],
      (s["path"], s["annotated_query"], CALLS))
s = run("빛투 해도 돼?", mode="C")
check("사전 되묻기 오타(빛투)도 후보를 보여 줌", "혹시 '빚투'를 말씀하신 건가요?" in s["final_answer"], s["final_answer"])

# P-092 되묻기 뒤 짧은 대답 (예전 P-076 짐작 답 다음 "맞아요"는 짐작 갈래와 함께 없앰)
_cotton = {"intent": "용어 설명", "terms": ["솜사탕 랠리"], "ticker": ""}
_cg = {"additions": [{"expr": "솜사탕 랠리", "meaning": "금방 꺼지는 상승세", "kind": "신조어", "confidence": "짐작"}], "unresolved": []}
s = run("솜사탕 랠리가 뭐야?", mode="D", thread="thread-guess", n3_intent=_cotton, n2_llm_normalize=_cg)
check("짐작만 한 말은 되묻기, 다음 턴 확인 대상", s["final_answer"] == clarify_message(["솜사탕 랠리"]) and s["history"][-1]["clarified"]
      and s["history"][-1]["asked"] == ["솜사탕 랠리"], s["final_answer"])
s = run("맞아요", mode="D", thread="thread-guess", n0_rewrite="솜사탕 랠리 맞아요", n3_intent=_cotton)
check("확인할 후보가 없는 '맞아요' → 다시 묻기, LLM 호출 없음 (P-092)", s["final_answer"] == CLARIFY_AGAIN and s["path"][-3:] == ["2 짧은 대답(다시 묻기)", "9 되묻기", "끝"]
      and "n2_llm_normalize" not in CALLS and "n3_intent" not in CALLS and "n5_answer" not in CALLS and s["history"][-1]["asked"] == ["솜사탕 랠리"],
      (s["path"], s["final_answer"], CALLS))
s = run("다른 뜻이에요", mode="D", thread="thread-guess", n0_rewrite="다른 뜻이에요", n3_intent=_cotton)
check("'다른 뜻이에요' → 다시 묻기 (P-092)", s["final_answer"] == CLARIFY_AGAIN and "2 확인 답" not in s["path"], (s["path"], s["final_answer"]))
s = run("몰라요", mode="D", thread="thread-guess", n0_rewrite="몰라요", n3_intent=_cotton)
check("'몰라요' → 확인된 뜻이 없다고 말하고 끝, 다음 턴은 되묻기 뒤 턴이 아님 (P-092)",
      s["final_answer"] == dont_know_message(["솜사탕 랠리"]) and "저도 확인된 뜻을 찾지 못했어요" in s["final_answer"]
      and s["path"][-3:] == ["2 짧은 대답(몰라요)", "9 확인 못 함", "끝"] and s["history"][-1]["clarified"] is False, (s["path"], s["final_answer"]))
s = run("몰라요", mode="D", n0_rewrite="몰라요", n3_intent={"intent": "범위 밖", "out_reason": "일반", "terms": [], "ticker": ""})
check("되묻기 뒤가 아니면 '몰라요'는 평소대로", "9 확인 못 함" not in s["path"], s["path"])
s = run("솜사탕 랠리 지금 올라타도 돼?", mode="D", n3_intent={"intent": "매매 판단 요청", "terms": ["솜사탕 랠리"], "ticker": ""}, n2_llm_normalize=_cg)
check("매매 판단을 묻는 질문은 되묻기 앞에 판단 불가 안내 (P-092)", s["path"][-2] == "9 되묻기"
      and s["final_answer"] == TRADING_NOTICE + "\n" + clarify_message(["솜사탕 랠리"]), s["final_answer"])

# P-092 노드 5가 뜻을 모르면 "[모름]" → 되묻기 문장
_min = {"intent": "용어 설명", "terms": ["민들레 계좌"], "ticker": ""}
s = run("민들레 계좌가 뭐야?", mode="D", thread="thread-n5", n3_intent=[_min, _min], n5_answer="[모름]")
check("노드 5 '[모름]' → 되묻기 문장으로 바꾸고 다음 턴 확인 대상 (P-092)", s["final_answer"] == clarify_message(["민들레 계좌"])
      and s["asked_back"] is True and s["history"][-1]["clarified"] is True and s["history"][-1]["asked"] == ["민들레 계좌"]
      and any(p.startswith("5 답변 생성(뜻 모름") for p in s["path"]), (s["path"], s["final_answer"]))
s = run("몰라요", mode="D", thread="thread-n5", n0_rewrite="몰라요", n3_intent=_min)
check("노드 5 되묻기 다음 '몰라요'도 같은 길 (P-092)", s["final_answer"] == dont_know_message(["민들레 계좌"]), s["final_answer"])

# P-093 오타 잇기 구멍, 아는 말 칸
_T = lambda t: {"intent": "용어 설명", "terms": [t], "ticker": ""}  # noqa: E731
s = run("공메도가 뭐야?", mode="D", n3_intent=[_T("공메도"), _T("공매도")])
check("LLM이 어느 칸에도 적지 않은 말은 사전과 대조해 잇는다 (P-093, 공메도→공매도)", "공메도=공매도(오타로 보임)" in s["annotated_query"]
      and s["typo_confirm"] == [{"typo": "공메도", "original": "공매도"}], s["annotated_query"])
s = run("고가가 뭐야?", mode="D", n3_intent=[_T("고가"), _T("고가")],
        n2_llm_normalize={"additions": [{"expr": "고가", "meaning": "높은 가격", "kind": "기타", "confidence": "확신"}], "unresolved": []})
check("LLM이 확신으로 푼 말은 표준 용어 후보로 잇지도 묻지도 않는다 (P-093, 고가≠호가)", not s["typo_confirm"] and "9 되묻기" not in s["path"]
      and "호가" not in s["annotated_query"], (s["path"], s["annotated_query"]))
s = run("숀졀이 뭐야?", mode="D", n3_intent=[_T("숀졀"), _T("손절매")],
        n2_llm_normalize={"additions": [{"expr": "숀졀", "meaning": "손해를 보고 팖(손절)", "kind": "신조어", "confidence": "확신"}], "unresolved": []})
check("LLM 풀이 안의 사전 말로 잇는다 (P-093, 숀졀=…(손절))", "숀졀=손절(오타로 보임)=손절매" in s["annotated_query"]
      and s["typo_confirm"] == [{"typo": "숀졀", "original": "손절"}] and "2 사전 잇기" in s["path"], (s["annotated_query"], s["path"]))
s = run("뗙샹이 뭐야?", mode="D", n3_intent=[_T("뗙샹"), _T("급등")],
        n2_llm_normalize={"additions": [{"expr": "뗙샹", "meaning": "급격한 가격 상승(떡상의 오타)", "kind": "신조어", "confidence": "확신"}], "unresolved": []})
check("LLM 풀이 안의 사전 말로 잇는다 (P-093, 뗙샹=…(떡상의 오타))", "뗙샹=떡상(오타로 보임)=급등" in s["annotated_query"], s["annotated_query"])
s = run("뗙샹이 뭐야?", mode="D", n3_intent=_T("뗙샹"),
        n2_llm_normalize={"additions": [{"expr": "뗙샹", "meaning": "주가의 급상승", "kind": "신조어", "confidence": "확신"}], "unresolved": []})
check("LLM이 사전 말을 안 적어도 가까운 은어가 하나면 후보를 보여 주며 되묻는다 (P-093)", s["path"][-2] == "9 되묻기"
      and "혹시 '떡상'을 말씀하신 건가요?" in s["final_answer"] and "급상승" not in s["annotated_query"], (s["path"], s["final_answer"]))
s = run("쏜절이 뭐야?", mode="D", thread="thread-two", n3_intent=_T("쏜절"))
check("후보가 둘이면 둘 다 보여 주며 되묻는다 (P-093, 쏜절 → 손절·본절)", s["path"][-2] == "9 되묻기"
      and "혹시 '손절'이나 '본절'을 말씀하신 건가요?" in s["final_answer"] and s["history"][-1]["candidates"] == [], s["final_answer"])
s = run("맞아요", mode="D", thread="thread-two", n0_rewrite="쏜절 맞아요", n3_intent=_T("쏜절"))
check("후보가 둘인 되묻기 뒤 '맞아요'는 어느 쪽인지 다시 묻는다 (P-093)", s["final_answer"] == CLARIFY_AGAIN, s["final_answer"])

# P-094 사전 밖 안내 첫 문장은 코드가 사용자가 쓴 말로
from src.fixed_messages import ungrounded_notice, UNGROUNDED_NOTICE_NONE  # noqa: E402
s = run("상폐가 뭐야?", mode="D", n3_intent=[_T("상폐"), _T("상장폐지")],
        n2_llm_normalize={"additions": [{"expr": "상폐", "meaning": "상장폐지", "kind": "줄임말", "confidence": "확신"}], "unresolved": []},
        n5_answer="'상폐'는 '상장폐지'를 줄여 부르는 말이에요.\n'상장폐지'는 사전에 등록되지 않은 용어라 일반적인 설명으로 안내해요. 주식이 시장에서 빠지는 일이라는 뜻으로 쓰이는 것으로 보여요.\n정확한 내용은 증권사 안내나 공식 자료에서 한 번 더 확인해 보세요.")
_ls = s["final_answer"].splitlines()
check("사전 밖 안내는 첫 문장, 사용자가 쓴 말 그대로. LLM이 쓴 안내는 지움 (P-094)", _ls[0] == "'상폐'는 사전에 등록되지 않은 용어라 일반적인 설명으로 안내해요."
      and s["final_answer"].count("일반적인 설명으로 안내해요") == 1 and "'상장폐지'는 사전에 등록되지" not in s["final_answer"], s["final_answer"])
s = run("상폐 종목 지금 사도 돼?", mode="D", n3_intent=[{"intent": "매매 판단 요청", "terms": ["상폐"], "ticker": ""}] * 2,
        n5_answer="지금 사도 되는지는 판단해드릴 수 없어요.\n상장폐지를 줄여 부르는 말로 쓰이는 것으로 보여요.\n결정 전에 충분히 알아보시는 걸 권해요.")
_ls = s["final_answer"].splitlines()
check("매매 판단이면 판단 불가 안내 다음에 사전 밖 안내 (P-094)", "판단해드릴 수 없어요" in _ls[0] and _ls[1] == ungrounded_notice(["상폐"]), s["final_answer"])
s = run("팔고 나서 다시 사는 걸 뭐라고 불러?", mode="D", n3_intent=[_T("재매수"), _T("재매수")], n5_answer="흔히 '재매수'라고 부르는 것으로 보여요.")
check("질문에 그 말이 없으면 말 없이 안내 (P-094)", s["final_answer"].splitlines()[0] == UNGROUNDED_NOTICE_NONE, s["final_answer"])
s = run("배당이 뭐야?", mode="D", n3_intent=_T("배당"), n5_answer="배당은 회사가 번 이익을 나눠 주는 것이에요.")
check("사전에 있는 용어에는 사전 밖 안내를 붙이지 않음 (P-094)", "사전에 등록되지 않은" not in s["final_answer"], s["final_answer"])

# P-095 민감 관용구 안전장치
_hard = {"intent": "범위 밖", "out_reason": "힘든 마음", "terms": [], "ticker": ""}
s = run("한강 물 온도 체크하러 가야 하나, 손절해야 해?", mode="D", n3_intent=[_hard, {"intent": "매매 판단 요청", "terms": ["손절매"], "ticker": ""}],
        n5_answer="손절해야 하는지는 판단해드릴 수 없어요.\n결정 전에 충분히 알아보시는 걸 권해요.")
check("민감 관용구 + 묻는 말: 힘든 마음으로 골라도 다시 분류해 답한다, 상담 안내는 끝에 (P-095)", s["intent"] == "매매 판단 요청"
      and "8 범위 밖(힘든 마음)" not in s["path"] and s["final_answer"].endswith(CARE_MESSAGE) and "민감 관용구" in s["intent_override"]
      and CALLS.count("n3_intent") == 2, (s["intent"], s["path"], s["intent_override"]))
s = run("한강 물 온도 체크 중인데 비트코인 전망 알려줘", mode="D", n3_intent=[_hard, {"intent": "범위 밖", "out_reason": "일반", "terms": [], "ticker": ""}])
check("민감 관용구 + 범위 밖 질문: 범위 밖 문구 + 상담 안내 (P-095)", s["final_answer"] == OUT_OF_SCOPE["일반"] + "\n" + CARE_MESSAGE, s["final_answer"])
s = run("한강 물 온도 체크하러 가야겠다", mode="D", n3_intent=[_hard, _hard])
check("다시 분류해도 힘든 마음이고 사고팔기 질문이 아니면 힘든 마음 문구 그대로 (P-095)", s["path"][-2] == "8 범위 밖(힘든 마음)", s["path"])
s = run("요즘 아무것도 하기 싫어", mode="D", n3_intent=_hard)
check("민감 관용구가 없으면 다시 분류하지 않음 (P-095)", CALLS.count("n3_intent") == 1 and s["path"][-2] == "8 범위 밖(힘든 마음)", CALLS)

# P-077 사용자 설명이 사전 용어 이름 그대로
s = run("번개장은 급등이래", mode="D", n3_intent={"intent": "용어 설명", "terms": ["번개장"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "번개장", "meaning": "주가가 급등하는 장세", "kind": "신조어", "source": "사용자 설명"}],
                          "unresolved": []})
lg = [x for x in s["norm_log"] if x["expr"] == "번개장"][0]
check("사용자 설명이 사전 용어 이름 그대로면 그 이름을 뜻으로 (P-077)",
      lg["standard"] == "급등" and s["user_words_terms"] and s["user_words_terms"][0]["standard"] == "급등", (lg, s.get("user_words_terms")))
s = run("번개장은 큰손이 사 모으는 장이래", mode="D", n3_intent={"intent": "용어 설명", "terms": ["번개장"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "번개장", "meaning": "큰손이 매집하는 장", "kind": "신조어", "source": "사용자 설명"}],
                          "unresolved": []})
lg = [x for x in s["norm_log"] if x["expr"] == "번개장"][0]
check("사용자 설명이 문장이면 LLM 풀이 그대로", lg["standard"] == "큰손이 매집하는 장", lg)

# 지침
_n3p = (ROOT / "prompts" / "n3_intent.md").read_text(encoding="utf-8")
check("지침: 노드 3 사유에 하소연·힘든 마음 (P-070·P-075)", "- 하소연:" in _n3p and "- 힘든 마음:" in _n3p and "하소연|힘든 마음" in _n3p)
check("지침: 노드 5 하소연은 공감 한 문장 (P-070)", "하소연 ([의도]가 '하소연'일 때)" in _n5p or
      "하소연 ([의도]가 '하소연'일 때)" in (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8"))

# P-088 사용자 설명 속 사전 용어, P-090 되묻기에 답한 턴
_tell = {"additions": [{"expr": "거북이 매매", "meaning": "주식을 사서 오래 들고 가는 장기 투자", "kind": "신조어", "source": "사용자 설명"}], "unresolved": []}
s = run("거북이 매매는 주식을 사서 오래 들고 가는 장기 투자래", mode="C", n2_llm_normalize=_tell,
        n3_intent={"intent": "용어 설명", "terms": ["거북이 매매"], "ticker": ""})
check("사용자 설명 속 사전 용어만 찾음 (P-088)", [(n["part"], n["standard"]) for n in s["user_words_terms"]] == [("장기 투자", "장기 투자")],
      s["user_words_terms"])
_none = {"additions": [{"expr": "솜사탕 랠리", "meaning": "금방 꺼지는 반짝 상승", "kind": "신조어", "source": "사용자 설명"}], "unresolved": []}
s = run("솜사탕 랠리는 금방 꺼지는 반짝 상승이래", mode="C", n2_llm_normalize=_none, n3_intent={"intent": "용어 설명", "terms": ["솜사탕 랠리"], "ticker": ""})
check("사용자 설명에 사전 말이 없으면 비움 (P-088)", s["user_words_terms"] == [], s["user_words_terms"])
_n5x = (ROOT / "prompts" / "n5_answer.md").read_text(encoding="utf-8")
check("지침: 사용자 설명은 확인해 주지 않고 설명 속 사전 용어만 (P-088)",
      "들으신 뜻이 맞는지는 제가 확인할 수 없어요" in _n5x and "[사용자 설명 속 사전 용어 (사전 근거)]가 있을 때만" in _n5x
      and "같은 말이라고 하지 않는다" in _n5x and "말씀해주신 뜻이라면" not in _n5x)
s = run("두꺼비 물량이 뭐야?", mode="D", thread="thread-told", n3_intent={"intent": "용어 설명", "terms": ["두꺼비 물량"], "ticker": ""},
        n2_llm_normalize={"additions": [], "unresolved": [{"expr": "두꺼비 물량", "reason": "모르는 말"}]})
check("되묻기로 끝남 (P-090 준비)", s["path"][-2] == "9 되묻기", s["path"])
s = run("한 번에 크게 나오는 매도 물량이래", mode="D", thread="thread-told", n0_rewrite="두꺼비 물량은 한 번에 크게 나오는 매도 물량이래",
        n2_llm_normalize={"additions": [{"expr": "두꺼비 물량", "meaning": "한 번에 크게 나오는 매도 물량", "kind": "신조어", "source": "사용자 설명"}], "unresolved": []},
        n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""})
check("되묻기에 뜻을 알려 준 답은 하소연으로 보내지 않음 (P-090)",
      s["intent"] == "용어 설명" and s["terms"] == ["두꺼비 물량"] and any(p.startswith("5 답변 생성") and "하소연" not in p for p in s["path"])
      and [n["standard"] for n in s["user_words_terms"]] == ["매도"], (s["intent"], s["path"], s.get("user_words_terms")))
s = run("오늘도 떡락이라 밥맛이 없다", mode="D", n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""}, n5_answer="속상하셨겠어요.")
check("되묻기 뒤가 아니면 하소연 그대로 (P-090)", "5 답변 생성(하소연)" in s["path"], s["path"])
_n3x = (ROOT / "prompts" / "n3_intent.md").read_text(encoding="utf-8")
check("지침: 힘든 마음은 묻는 말이 없을 때만 (P-091)", "힘든 마음은 용어 뜻이나 매매 판단을 묻는 말이 함께 없을 때만 고른다" in _n3x
      and "힘든 마음이 먼저다" not in _n3x)

# ===== P-097 (11.12): 노드 3이 뽑은 용어를 사용자가 친 글자와 대조 · 설명 뒤 2턴 =====
s = run("시가춍액이 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": ["시가총액"], "ticker": ""})
check("P-097 LLM이 고쳐 뽑은 용어에 오타 확인 기록", {"typo": "시가춍액", "original": "시가총액"} in s["typo_confirm"], s["typo_confirm"])
s = run("삼젼이 뭐야?", mode="D", n3_intent={"intent": "용어 설명", "terms": [], "ticker": ""})
check("P-097 이은 뒤 다시 '삼젼'으로 뽑아도 '사전 근거 없음' 용어로 남지 않음", all(t.get("found") for t in s["term_info"]), s["term_info"])
s2 = run("쏜절이 뭐야?", mode="D", n3_intent=[{"intent": "용어 설명", "terms": ["쏜절"], "ticker": ""}, {"intent": "용어 설명", "terms": ["쏜절"], "ticker": ""}],
         n2_llm_normalize={"additions": [{"expr": "쏜절", "meaning": "손해 보고 팖(손절)", "confidence": "확신"}], "unresolved": []})
check("P-097 이은 뒤 다시 '쏜절'로 뽑아도 손절매로 조회", [t["standard"] for t in s2["term_info"] if t.get("found")] == ["손절매"], s2["term_info"])
check("P-097 용어를 안 뽑아도 '삼젼' → 삼전으로 이음", any(t.get("original") == "삼전" for t in s["typo_confirm"]) and "2 사전 잇기" in s["path"], (s["typo_confirm"], s["path"]))
s = run("솜사탕 랠리 지금 올라타도 돼?", mode="D", n3_intent={"intent": "매매 판단 요청", "terms": ["랠리"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "솜사탕 랠리", "meaning": "금방 꺼지는 상승", "confidence": "짐작"}], "unresolved": []})
check("P-097 잘린 용어 대신 긴 표현으로 되묻기", "'솜사탕 랠리'" in s["final_answer"] and "'랠리'" not in s["final_answer"], s["final_answer"])
s = run("지금 손절해야 해?", mode="D", n3_intent={"intent": "매매 판단 요청", "terms": ["손절매"], "ticker": ""})
check("P-097 사전 풀이가 준 표준 용어에는 오타 확인을 붙이지 않음 (손절해 → 손절매)", not s["typo_confirm"], s["typo_confirm"])
T = "p097-a"
s = run("문어발 매수라는 말을 들었는데 뭐야?", mode="D", thread=T, n3_intent={"intent": "용어 설명", "terms": ["문어발 매수"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "문어발 매수", "meaning": "여러 종목을 마구 사들임", "confidence": "확신"}], "unresolved": []})
check("P-097 설명 턴은 explained에 남음", s["history"][-1].get("explained") == ["문어발 매수"] and not s["history"][-1]["clarified"], s["history"][-1])
s = run("맞아요", mode="D", thread=T, n0_rewrite="문어발 매수 맞아요")
check("P-097 설명 뒤 맞장구는 고정 문구", s["final_answer"].startswith("네, 더 궁금한 주식 용어") and "n3_intent" not in CALLS, (s["final_answer"], s["path"]))
T = "p097-b"
s = run("거북이 매매가 뭐야?", mode="D", thread=T, n3_intent={"intent": "용어 설명", "terms": ["거북이 매매"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "거북이 매매", "meaning": "느린 장기 투자", "confidence": "확신"}], "unresolved": []})
s = run("주식을 사서 오래 들고 가는 장기 투자래", mode="D", thread=T, n0_rewrite="거북이 매매는 주식을 사서 오래 들고 가는 장기 투자래",
        n3_intent={"intent": "범위 밖", "out_reason": "하소연", "terms": [], "ticker": ""})
check("P-097 설명 뒤 '…래'는 사용자 설명으로", "2 사용자 설명" in s["path"] and s["intent"] == "용어 설명" and "5 답변 생성" in " ".join(s["path"]) and "하소연" not in " ".join(s["path"]), (s["path"], s["intent"]))
check("P-097 설명 속 사전 용어(장기 투자)를 찾음", any(u["standard"] == "장기 투자" for u in s.get("user_words_terms") or []), s.get("user_words_terms"))
T = "p097-c"
s = run("문어발 매수가 뭐야?", mode="D", thread=T, n3_intent={"intent": "용어 설명", "terms": ["문어발 매수"], "ticker": ""},
        n2_llm_normalize={"additions": [{"expr": "문어발 매수", "meaning": "여러 종목을 조금씩 나눠 사는 것", "confidence": "확신"}], "unresolved": []})
s = run("여러 종목을 한꺼번에 사는 거래래", mode="D", thread=T, n0_rewrite="문어발 매수는 여러 종목을 한꺼번에 사는 거래래",
        n3_intent={"intent": "용어 설명", "terms": ["문어발 매수"], "ticker": ""})
check("11.13 설명 뒤 '…거래래'는 끝말을 한 번만 뗌 (…사는 거래)", any(x.get("user_defined") and x["standard"] == "여러 종목을 한꺼번에 사는 거래" for x in s["norm_log"]), s["norm_log"])


print(f"\n결과: 통과 {passed} · 실패 {failed}")
sys.exit(1 if failed else 0)
