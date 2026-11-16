"""노드 1 사전 정규화 (규칙, LLM 없음).

오타 → 종목 약어 → 용어 순서로 사전을 매칭해, 원문은 그대로 두고 [풀이]를 덧붙인다.
세부 규칙은 src/dictionary.py 맨 위 설명 참고.
실험 설정 B, C에서만 돈다.
"""
from ..dictionary import dict_normalize, render_annotation
from ..state import AgentState


def dict_normalize_node(state: AgentState) -> dict:
    query = state["rewritten_query"]
    r = dict_normalize(query)
    return {
        "annotated_query": render_annotation(query, r.norm_log),
        "norm_log": r.norm_log,
        "typo_confirm": r.typo_confirm,
        "unresolved": r.unresolved,
        "path": state["path"] + ["1 사전 정규화"],
    }
