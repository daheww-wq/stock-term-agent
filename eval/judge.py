"""평가용 LLM 채점 (채점용 모델, .env의 JUDGE_MODEL).

사전 밖 용어 채점 (설계도 7번 "사전 밖 용어 채점 기준")
- "사전 근거 없음"으로 나간 답변마다, 사전에 없던 용어별로 채점한다
- 항목: 핵심 의미 일치 / 틀린 사실 없음 / 근거 없음 표시 / 눈높이
- 근거 없음 표시는 문구가 있는지 코드로 확인하고, 나머지 셋은 채점용 모델이 본다
- 평가용 정답 설명이 있으면 함께 넘긴다 (측정용). 개발용은 정답 설명이 없어 채점 모델의 지식으로 비교한다
- 문항의 풀이_정답("정답지 풀이: …")도 평가용 정답으로 넘긴다 (P-039)
- 질문 속 표현 풀이(노드 1·2의 풀이 결과, 예: 부엉이 매매=야간 해외주식 거래(추정))도 넘긴다 (P-051).
  노드 2가 풀어 바꾼 용어는 원래 표현이 아니라서, 원래 표현을 그 뜻으로 푼 근거까지 봐야 지어냄을 잡는다
- 뜻을 설명하지 않고 되물은 용어는 meaning_ok를 "해당 없음"(빈칸)으로 둔다 (P-051). 틀린 사실 없음은 그대로 본다
- 추정이라고 밝힌 뒤 사실처럼 설명한 답은 단정으로 본다. 되물은 답이 조건을 걸고 표준 용어를 안내했으면 hedged_guide (P-055)
- 결과는 LLM 1차 채점이다. 본인이 결과 엑셀에서 전수 확인한다

에이전트 실행과 별개로 부르므로, 비용은 "채점_비용_USD"로 따로 기록한다.
"""
from src import config
from src.llm import call_llm, load_prompt, parse_json

NODE = "judge_unknown_term"
UNGROUNDED_NOTICE = "사전에 등록되지 않은 용어"


def judge_unknown_term(question: str, term: str, answer: str, reference: str | None = None,
                       normalization: str | None = None) -> dict:
    """사전 밖 용어 하나를 채점한다. 반환: meaning_ok, no_false_fact, notice_ok, beginner_ok, asked_back, comment, cost_usd
    normalization: 질문 속 표현 풀이 (노드 1·2, P-051). 되물은 용어는 meaning_ok가 빈칸(해당 없음)"""
    user = (f"[질문]\n{question}\n\n[질문 속 표현 풀이]\n{normalization or '(없음)'}\n\n"
            f"[사전에 없던 용어]\n{term}\n\n"
            f"[평가용 정답]\n{reference or '(없음)'}\n\n[에이전트 답변]\n{answer}")
    text, usage = call_llm(NODE, load_prompt(NODE), user, model=config.JUDGE_MODEL)
    data = parse_json(text) or {}

    def flag(key):
        v = data.get(key)
        if isinstance(v, str):
            v = v.strip().lower() in ("true", "1", "예", "yes")
        return int(bool(v)) if key in data else ""

    asked_back = flag("asked_back")
    hedged_guide = flag("hedged_guide")
    return {
        "meaning_ok": "" if asked_back == 1 else flag("meaning_ok"),  # P-051: 되물었으면 뜻은 해당 없음
        "asked_back": asked_back,
        "hedged_guide": 1 if (asked_back == 1 and hedged_guide == 1) else ("" if hedged_guide == "" else 0),
        "no_false_fact": flag("no_false_fact"),
        "beginner_ok": flag("beginner_ok"),
        "notice_ok": int(UNGROUNDED_NOTICE in answer),
        "comment": str(data.get("comment", "")) if data else f"[채점 형식 깨짐] {text[:120]}",
        "cost_usd": usage.get("cost_usd"),
    }


def judge_row(question: str, unknown_terms: list[str], answer: str, references: dict | None = None,
              normalization: str | None = None) -> dict:
    """한 문항에 사전 밖 용어가 여러 개면 용어별로 채점하고, 하나라도 0이면 0으로 묶는다.
    되물은 용어는 뜻 일치에서 빠진다 (P-051). 모두 되물었으면 뜻 일치는 빈칸"""
    results = [(t, judge_unknown_term(question, t, answer, (references or {}).get(t), normalization))
               for t in unknown_terms]

    def combine(key):
        vals = [r[key] for _, r in results if r[key] != ""]
        return min(vals) if vals else ""

    costs = [r["cost_usd"] for _, r in results if r["cost_usd"] is not None]
    return {
        "사전밖_뜻일치": combine("meaning_ok"),
        "사전밖_틀린사실없음": combine("no_false_fact"),
        "사전밖_표시": combine("notice_ok"),
        "사전밖_눈높이": combine("beginner_ok"),
        "사전밖_되물음": " · ".join(t for t, r in results if r.get("asked_back") == 1),
        "사전밖_조건부안내": " · ".join(t for t, r in results if r.get("hedged_guide") == 1),
        "사전밖_채점메모": " | ".join(f"{t}: {r['comment']}" for t, r in results),
        "채점_비용_USD": round(sum(costs), 6) if costs else "",
    }
