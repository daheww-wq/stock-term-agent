"""그래프: 노드와 화살표 연결 (설계도 1번 그림과 같은 모양).

질문 → 0 재구성 → (설정별) 1 사전 정규화 → 2 LLM 정규화 → 3 의도 분류
  3 → 용어 설명                → 4 용어 조회 → 5 답변 → 6 검수
  3 → 매매 판단 요청 + 용어 있음 → 4 용어 조회 → 5 답변 → 6 검수
  3 → 매매 판단 요청 + 용어 없음 → 5 답변 → 6 검수
  3 → 범위 밖                  → 8 범위 밖 안내 (하소연이면 → 5 공감 한 문장 → 6 검수, P-070)
  2 → 못 푼 표현·애매한 오타    → 9 되묻기
  4 → (설정 D) 사전에 없는 용어가 있고 노드 2를 아직 안 거쳤으면 → 2 LLM 정규화 → 3 → 4 다시 (P-042)
  1 → (설정 D) 앞 턴이 되묻기로 끝났으면 → 2 LLM 정규화부터 (P-045). 노드 9 되묻기와 노드 5가 뜻을 몰라 되물은 답 모두 (P-092)
  2 → 되묻기 뒤 짧은 대답("몰라요", "다른 뜻이에요", 후보 없는 "맞아요")이면 LLM 없이 → 9 (P-092)
  3 안의 매매 판단 안전망: 용어 설명이어도 사고팔기 판단을 묻는 꼴이면 매매 판단 요청으로 (P-044)
  6 → 통과 → 끝 / 실패·재생성 2회 미만 → 5 / 실패·재생성 2회 도달 → 7 안전 답변
모든 끝은 '끝' 노드에서 대화 기억(최근 3턴)에 저장한다.

실험 설정
  A 정규화 없음: 0 → 3 (1·2 건너뜀)
  B 사전만:     0 → 1 → 3
  C 사전+LLM:   0 → 1 → 2 → (9 또는 3). 노드 2를 모든 질문에 돈다
  D 사전 우선+필요 시 LLM: 0 → 1 → 3 → 4, 조회한 용어 중 사전에 없는 것이 있을 때만 → 2 → (9 또는 3 → 4). 노드 2는 한 턴에 한 번만 (P-042)
  되묻기는 노드 2가 있는 C·D에서만 동작
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from . import config
from .nodes import (answer_node, clarify_node, compliance_node, dict_normalize_node,
                    finish_node, intent_node, llm_normalize_node, lookup_node,
                    out_of_scope_node, rewrite_node, safe_answer_node)
from .state import AgentState

# 노드 이름 (랭퓨즈 trace에도 이 이름으로 보인다)
N0, N1, N2, N3, N4 = "n0_rewrite", "n1_dict_normalize", "n2_llm_normalize", "n3_intent", "n4_lookup"
N5, N6, N7, N8, N9 = "n5_answer", "n6_compliance", "n7_safe_answer", "n8_out_of_scope", "n9_clarify"
FINISH = "finish"


def after_rewrite(state: AgentState) -> str:
    """설정 A는 정규화를 건너뛴다. 이때 annotated_query는 노드 0이 채운 재구성 질문 그대로다."""
    return N3 if state["normalizer_mode"] == "A" else N1


def after_dict(state: AgentState) -> str:
    if state["normalizer_mode"] == "C":
        return N2
    # 설정 D (P-045): 앞 턴이 되묻기로 끝났으면 이번 턴은 사용자가 뜻을 설명하는 턴일 수 있어 노드 2부터
    history = state.get("history") or []
    if state["normalizer_mode"] == "D" and history and history[-1].get("clarified"):
        return N2
    # P-097: 앞 턴이 사전에 없는 말을 설명한 턴이고 이번 말이 "…래"로 뜻을 알려 주는 꼴이면 노드 2가 사용자 설명으로 받는다
    if state["normalizer_mode"] == "D" and history and history[-1].get("explained"):
        from .nodes.n2_llm_normalize import TELL_TAIL
        if TELL_TAIL.search((state.get("raw_query") or "").strip()):
            return N2
    return N3


def after_llm_normalize(state: AgentState) -> str:
    return N9 if state["unresolved"] else N3


def after_lookup(state: AgentState) -> str:
    """설정 D (P-042): 사전에 없는 용어가 있으면 그때만 노드 2로. 노드 2는 한 턴에 한 번만 (다시 조회해도 없으면 답변으로)."""
    if (state["normalizer_mode"] == "D" and not any(p.startswith("2 ") for p in state["path"])
            and any(not t.get("found") for t in state.get("term_info") or [])):
        return N2
    return N5


def after_intent(state: AgentState) -> str:
    intent = state["intent"]
    if intent == "범위 밖":
        return N5 if state.get("out_reason") == "하소연" else N8  # P-070 하소연은 공감 한 문장을 쓰러 노드 5로
    if intent == "매매 판단 요청" and not state["terms"]:
        return N5
    return N4


def after_compliance(state: AgentState) -> str:
    if state["compliance"].get("passed"):
        return FINISH
    if state["retry_count"] < config.MAX_RETRY:
        return N5
    return N7


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node(N0, rewrite_node)
    g.add_node(N1, dict_normalize_node)
    g.add_node(N2, llm_normalize_node)
    g.add_node(N3, intent_node)
    g.add_node(N4, lookup_node)
    g.add_node(N5, answer_node)
    g.add_node(N6, compliance_node)
    g.add_node(N7, safe_answer_node)
    g.add_node(N8, out_of_scope_node)
    g.add_node(N9, clarify_node)
    g.add_node(FINISH, finish_node)

    g.add_edge(START, N0)
    g.add_conditional_edges(N0, after_rewrite, [N1, N3])
    g.add_conditional_edges(N1, after_dict, [N2, N3])
    g.add_conditional_edges(N2, after_llm_normalize, [N9, N3])
    g.add_conditional_edges(N3, after_intent, [N4, N5, N8])
    g.add_conditional_edges(N4, after_lookup, [N2, N5])
    g.add_edge(N5, N6)
    g.add_conditional_edges(N6, after_compliance, [FINISH, N5, N7])
    for n in (N7, N8, N9):
        g.add_edge(n, FINISH)
    g.add_edge(FINISH, END)

    # 대화 기억: 같은 thread_id(대화방 번호)로 부르면 history가 이어진다
    return g.compile(checkpointer=checkpointer or MemorySaver())
