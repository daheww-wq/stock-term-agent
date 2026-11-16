"""한 턴 실행 + 랭퓨즈 기록.

랭퓨즈 trace 하나 = 질문 한 턴. 노드마다 span이, LLM 호출마다 generation이 붙는다.
tag: 실험 설정(설정A/B/C), 모델명, 세트(일반/위험), 문항 구분(개발용/측정용)
session: 같은 대화(멀티턴 시나리오)의 턴들을 묶는다
score: 비용·응답 시간·LLM 호출 수는 자동으로, 채점 결과는 eval 스크립트가 붙인다
"""
import time
import uuid

from . import config
from .state import turn_input


def langfuse_client():
    if not config.tracing_on():
        return None
    from langfuse import get_client
    return get_client()


def run_turn(graph, question: str, *, mode: str = "C", thread_id: str | None = None,
             tags: list[str] | None = None, session_id: str | None = None,
             metadata: dict | None = None, trace_name: str = "stock-term-agent"):
    """질문 한 턴을 그래프에 넣고 (최종 상태, trace_id)를 돌려준다.

    주의: metadata에 "run_id" 키를 넣지 않는다. LangGraph가 쓰는 이름이라 대화 기억이 끊긴다.

    thread_id가 같으면 앞 턴의 대화 기억(history)이 이어진다.
    """
    thread_id = thread_id or str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}, "run_name": trace_name}

    handler = None
    if config.tracing_on():
        from langfuse.langchain import CallbackHandler
        handler = CallbackHandler()
        cfg["callbacks"] = [handler]
        meta = {
            "langfuse_tags": [f"설정{mode}", config.current_model(), *(tags or [])],
            "normalizer_mode": mode,
            "model": config.current_model(),
            **(metadata or {}),
        }
        if session_id:
            meta["langfuse_session_id"] = session_id
        cfg["metadata"] = meta

    t0 = time.time()
    state = graph.invoke(turn_input(question, mode), cfg)
    # P-025: 호출 간격 조절·한도 초과로 기다린 시간은 응답 시간에서 빼고 따로 적는다
    wait = round(sum(u.get("wait_sec") or 0 for u in state.get("usage", [])), 2)
    sec = round(time.time() - t0 - wait, 2)
    state["_latency_sec"] = sec
    state["_wait_sec"] = wait

    trace_id = handler.last_trace_id if handler else None
    lf = langfuse_client()
    if lf and trace_id:
        costs = [u["cost_usd"] for u in state.get("usage", []) if u.get("cost_usd") is not None]
        lf.create_score(trace_id=trace_id, name="latency_sec", value=sec)
        lf.create_score(trace_id=trace_id, name="llm_calls", value=len(state.get("usage", [])))
        if costs:
            lf.create_score(trace_id=trace_id, name="cost_usd", value=round(sum(costs), 6))
    return state, trace_id


def flush():
    lf = langfuse_client()
    if lf:
        lf.flush()
