"""상태: 단계를 지나며 들고 다니는 항목 (설계도 2번 표와 같은 이름).

history만 턴이 바뀌어도 남고, 나머지는 매 턴 turn_input()으로 비우고 시작한다.
LangGraph 대화 기억(체크포인터)은 같은 thread_id의 상태를 이어 저장하기 때문에,
비우지 않으면 앞 턴의 retry_count나 unresolved가 다음 턴으로 넘어온다.
"""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # 대화 기억 (최근 3턴: user, rewritten, assistant)
    history: list[dict]

    # 입력
    raw_query: str
    normalizer_mode: str  # "A" 정규화 없음 / "B" 사전만 / "C" 사전+LLM / "D" 사전 우선+필요 시 LLM (P-042)

    # 0 질문 재구성
    rewritten_query: str

    # 1·2 정규화
    annotated_query: str
    norm_log: list[dict]      # {expr, standard, type, method, via?, annotation, status?}
    unresolved: list[dict]    # {expr, reason, candidate?, candidates?}
    clarify_kind: str         # 되묻기 뒤 짧은 대답 (P-092): "" / "다시"(맞아요·다른 뜻이에요) / "모름"(몰라요)
    typo_confirm: list[dict]  # {typo, original}

    # 3 의도 분류
    intent: str               # 용어 설명 / 매매 판단 요청 / 범위 밖
    out_reason: str           # 일반 / 불법·유해 / 하소연 / 힘든 마음 (범위 밖일 때만, P-070·P-075)
    intent_reason: str
    terms: list[str]
    term_fixes: list[str]     # 용어 보정 기록 (P-027): "평가손실 → 평가손실 상태가 되다"
    intent_override: str      # 매매 판단 안전망이 의도를 바꿨으면 기록 (P-044)
    ticker: str

    # 4 용어 사전 조회
    term_info: list[dict]     # {term, found, standard, description}
    related_terms: list[str]  # 관련 용어 안내 후보 (P-022)

    # 4 용어 조회 (P-056): 짐작·사용자 설명 풀이의 뜻이 사전 표준 용어와 글자까지 같을 때만 함께 조회한 것
    near_terms: list[dict]     # {term: 원래 표현, standard, description}
    user_words_terms: list[dict]  # P-088 {term, part: 사용자가 쓴 말, standard, description}

    # 5 답변 생성
    draft_answer: str
    guess_confirm: bool       # (P-092부터 쓰지 않음, 늘 False) 짐작 갈래를 없앴다. 결과 칸 이름을 지키려고 남겨 둠
    asked_back: bool          # 노드 5가 뜻을 몰라 되묻기 문장으로 끝낸 답변 (P-092). 다음 턴 설정 D가 노드 2부터 가게
    grounded: list[dict]      # {term, grounded: 사전 근거 / 사전 근거 없음}

    # 6 컴플라이언스 검수
    compliance: dict          # {passed, verdict, violations: [{item, sentence, reason}], raw?}
    compliance_history: list[dict]  # 재생성 포함 모든 검수 결과 (평가용)
    retry_count: int

    # 출력
    final_answer: str

    # 실행 기록 (평가·디버깅용)
    path: list[str]           # 지나간 노드 순서
    usage: list[dict]         # LLM 호출별 모델·시간·토큰·비용
    errors: list[str]         # 형식 깨짐 등 노드 안에서 처리한 오류


def turn_input(raw_query: str, mode: str = "C") -> dict[str, Any]:
    """한 턴을 시작할 때 넣는 입력. history를 뺀 모든 항목을 비운다."""
    return {
        "raw_query": raw_query,
        "normalizer_mode": mode,
        "rewritten_query": "",
        "annotated_query": "",
        "norm_log": [],
        "unresolved": [],
        "clarify_kind": "",
        "typo_confirm": [],
        "intent": "",
        "out_reason": "",
        "intent_reason": "",
        "terms": [],
        "term_fixes": [],
        "intent_override": "",
        "ticker": "",
        "term_info": [],
        "related_terms": [],
        "near_terms": [],
        "user_words_terms": [],
        "draft_answer": "",
        "guess_confirm": False,
        "asked_back": False,
        "grounded": [],
        "compliance": {},
        "compliance_history": [],
        "retry_count": 0,
        "final_answer": "",
        "path": [],
        "usage": [],
        "errors": [],
    }
