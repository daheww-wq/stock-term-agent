"""노드 0 질문 재구성 (LLM).

앞 대화(최근 3턴)를 보고 지시어·생략만 채운다. 슬랭·약어·오타는 원문 그대로 둔다.
앞 대화가 없으면 LLM을 부르지 않고 원문을 그대로 쓴다 (비용·시간 절약).
세 실험 설정(A/B/C) 모두에서 돈다.
"""
from ..llm import call_llm, format_history, load_prompt
from ..state import AgentState

NODE = "n0_rewrite"


def rewrite_node(state: AgentState) -> dict:
    raw = state["raw_query"]
    history = state.get("history") or []
    out = {"path": state["path"] + ["0 재구성"]}

    if not history:
        out["rewritten_query"] = out["annotated_query"] = raw
        return out

    user = f"[앞 대화]\n{format_history(history)}\n\n[현재 질문]\n{raw}"
    text, usage = call_llm(NODE, load_prompt(NODE), user)
    line = text.strip().splitlines()[0].strip().strip('"“”') if text.strip() else ""
    out["rewritten_query"] = line or raw
    out["annotated_query"] = out["rewritten_query"]  # 설정 A는 이 값이 그대로 의도 분류로 간다
    out["usage"] = state["usage"] + [usage]
    if not line:
        out["errors"] = state["errors"] + ["n0: 빈 출력 → 원문 사용"]
    return out
