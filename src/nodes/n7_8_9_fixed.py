"""노드 7·8·9 고정 문구, 그리고 턴 마무리(대화 기억 저장).

7 안전 답변: 재생성 2회 후에도 검수에 걸렸을 때
  (P-068) 남은 위반이 판단 불가 안내 누락(R1)뿐이면 답을 버리지 않고 고정 안내 문장을 앞에 붙여 내보낸다
8 범위 밖 안내: 사유(일반 / 불법·유해 / 힘든 마음)별 문구. 하소연은 노드 5로 간다 (P-070)
9 되묻기: 풀지 못한 표현을 넣은 문구. 사전 말 후보가 있으면 후보를 보여 주며 묻는다 (P-072). 후보가 둘이면 둘 다 (P-093)
  되묻기 뒤 짧은 대답 (P-092): "몰라요" → 확인된 뜻이 없다고 말하고 끝 (경로 "9 확인 못 함"), "맞아요"(후보 없음)·"다른 뜻이에요" → 다시 묻기
  매매 판단을 묻는 질문이면 되묻기 앞에 판단 불가 안내를 붙인다 (P-092, 안내 없이 되묻기로 끝나던 빈틈)
"""
from .. import config
from ..dictionary import has_sensitive_expression
from ..safety import trading_ask, weak_crisis_expression
from ..fixed_messages import (CARE_MESSAGE, CLARIFY_AGAIN, OUT_OF_SCOPE, SAFE_ANSWER, TRADING_CLOSING, TRADING_NOTICE,
                              clarify_message, dont_know_message)
from ..state import AgentState


def safe_answer_node(state: AgentState) -> dict:
    last = state.get("compliance") or {}
    items = [str(v.get("item", "")).upper() for v in last.get("violations", [])]
    draft = (state.get("draft_answer") or "").strip()
    if items and all(i.startswith("R1") for i in items) and draft and draft != SAFE_ANSWER:
        # P-068: 마지막 검수에서 C1~C5는 통과했고 안내만 빠진 답 → 안내를 앞에 붙여 내보낸다
        final = f"{TRADING_NOTICE}\n{draft}"
        if TRADING_CLOSING not in draft:
            final += f"\n{TRADING_CLOSING}"
        return {"final_answer": final, "path": state["path"] + ["7 안전 답변(안내 덧붙임)"]}
    return {"final_answer": SAFE_ANSWER, "path": state["path"] + ["7 안전 답변"]}


def out_of_scope_node(state: AgentState) -> dict:
    reason = state.get("out_reason") or "일반"
    return {"final_answer": OUT_OF_SCOPE.get(reason, OUT_OF_SCOPE["일반"]),
            "path": state["path"] + [f"8 범위 밖({reason})"]}


def clarify_node(state: AgentState) -> dict:
    exprs = [u["expr"] for u in state["unresolved"]]
    kind = state.get("clarify_kind") or ""
    if kind == "모름":  # P-092 "몰라요": 다시 묻지 않고 끝낸다
        return {"final_answer": dont_know_message(exprs), "path": state["path"] + ["9 확인 못 함"]}
    if kind == "다시":  # P-092 "맞아요"(확인할 후보 없음) · "다른 뜻이에요"
        return {"final_answer": CLARIFY_AGAIN, "path": state["path"] + ["9 되묻기"]}
    first = state["unresolved"][0] if len(state["unresolved"]) == 1 else {}
    cands = first.get("candidates") or ([first["candidate"]] if first.get("candidate") else [])
    final = clarify_message(exprs, candidates=cands)
    # P-092: 사고팔기 판단을 묻는 질문이면 되묻기로 끝나도 판단 불가 안내가 먼저 나가게 한다
    if state.get("intent") == "매매 판단 요청" or trading_ask(state.get("rewritten_query") or state["raw_query"]):
        final = f"{TRADING_NOTICE}\n{final}"
    return {"final_answer": final, "path": state["path"] + ["9 되묻기"]}


def finish_node(state: AgentState) -> dict:
    """나간 답변을 대화 기억에 저장하고 최근 3턴만 남긴다.

    민감 표현이 질문에 있으면 걱정 한 문장(CARE_MESSAGE)을 끝에 붙인다 (P-023).
    과장으로도 쓰는 힘든 마음 표현(죽을 것 같다, 우울증)도 같다 (P-083). 이미 109 안내가 있는 답에는 붙이지 않는다.
    사전 정규화를 건너뛰는 설정 A에서도 붙도록 원문을 직접 확인한다.
    """
    final = state["final_answer"]
    sensitive = has_sensitive_expression(state["raw_query"]) or any(
        x.get("sensitive") for x in state.get("norm_log") or [])
    sensitive = sensitive or weak_crisis_expression(state["raw_query"])
    if sensitive and CARE_MESSAGE not in final and "(109)" not in final:
        final = f"{final}\n{CARE_MESSAGE}"
    history = list(state.get("history") or [])
    asked_node9 = "9 되묻기" in state["path"]
    clarified = asked_node9 or bool(state.get("asked_back"))
    history.append({"user": state["raw_query"], "rewritten": state["rewritten_query"],
                    "assistant": final,
                    # 다음 턴에 설정 D가 노드 2부터 거치게 (P-045). 노드 5가 뜻을 몰라 되물은 답도 같다 (P-092)
                    "clarified": clarified,
                    # P-097: 이번 턴이 사전에 없는 말을 설명한 턴이면 그 말. 다음 턴 "…래"를 사용자 설명으로 받는다
                    "explained": [] if clarified or not any(p.startswith("5 답변 생성") for p in state["path"]) else
                                 [t["term"] for t in state.get("term_info") or [] if not t.get("found")],
                    # P-092: 무엇을 되물었는지. 다음 턴의 "몰라요"·"다른 뜻이에요"가 이 표현을 가리킨다
                    "asked": [u["expr"] for u in state.get("unresolved") or []] if clarified else [],
                    # P-072: 후보 하나를 보여 주며 되물었으면 다음 턴 "맞아요"를 그 후보로 받는다 (노드 2). 후보가 둘이면 받지 않는다
                    "candidates": [{"expr": u["expr"], "candidate": u["candidate"]} for u in state.get("unresolved") or []
                                   if u.get("candidate") and len(u.get("candidates") or [1]) == 1] if asked_node9 else []})
    out = {"history": history[-config.HISTORY_TURNS:], "path": state["path"] + ["끝"]}
    if final != state["final_answer"]:
        out["final_answer"] = final
    return out
