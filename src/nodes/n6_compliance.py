"""노드 6 컴플라이언스 검수 (LLM 판정, 체크리스트).

- 노드 5가 만든 모든 답변을 본다. C1~C5는 항상, R1은 매매 판단 요청일 때
- (P-068) 의도가 매매 판단 요청이 아니어도 질문을 함께 넘기면 R1을 '질문 기준'으로 적용한다:
  검수가 질문을 보고 매매 판단을 묻는 질문이면 판단 불가 안내를 확인한다 (의도 분류가 놓친 매매 질문을 받침).
  질문을 넘기지 않으면 예전과 같다 (검수 검증셋 기본 실행)
- 판정 값은 통과 / 위반. 위반이면 항목·문장·이유를 남겨 노드 5가 고치게 한다
- 판정 출력 형식이 깨지면 위반으로 본다 (안전 우선)
- 통과하면 draft_answer를 final_answer로 내보낸다
"""
from ..llm import call_llm, load_prompt, parse_json
from ..state import AgentState

NODE = "n6_compliance"


def judge(draft: str, intent: str, question: str | None = None) -> tuple[dict, dict]:
    """검수 판정만 따로 부를 수 있게 분리 (검수 노드 검증셋 20개에서 재사용).

    question을 주고 의도가 매매 판단 요청이 아니면 R1을 '질문 기준'으로 적용한다 (P-068).
    """
    by_question = bool((question or "").strip()) and intent != "매매 판단 요청"
    if intent == "매매 판단 요청":
        items = "C1, C2, C3, C4, C5, R1"
    elif by_question:
        items = "C1, C2, C3, C4, C5, R1(질문 기준)"
    else:
        items = "C1, C2, C3, C4, C5"
    parts = [f"[의도]\n{intent}"]
    if by_question:
        parts.append(f"[질문]\n{question.strip()}")
    parts += [f"[적용 항목]\n{items}", f"[답변]\n{draft}"]
    user = "\n\n".join(parts)
    text, usage = call_llm(NODE, load_prompt(NODE), user)
    data = parse_json(text)

    verdict = (data or {}).get("verdict", "").strip() if isinstance(data, dict) else ""
    if verdict not in ("통과", "위반"):
        return {"passed": False, "verdict": "위반",
                "violations": [{"item": "형식", "sentence": "", "reason": "판정 형식이 깨짐 (안전 우선으로 위반 처리)"}],
                "raw": text[:300]}, usage

    violations = [v for v in (data.get("violations") or []) if isinstance(v, dict)]
    if intent != "매매 판단 요청" and not by_question:
        violations = [v for v in violations if not str(v.get("item", "")).upper().startswith("R1")]
    passed = verdict == "통과"
    if not passed and not violations:
        violations = [{"item": "미상", "sentence": "", "reason": "위반 판정이지만 항목을 적지 않음"}]
    return {"passed": passed, "verdict": verdict, "violations": [] if passed else violations}, usage


def compliance_node(state: AgentState) -> dict:
    result, usage = judge(state["draft_answer"], state["intent"], state.get("rewritten_query") or state.get("raw_query"))
    out = {
        "compliance": result,
        "compliance_history": state["compliance_history"] + [result],
        "usage": state["usage"] + [usage],
        "path": state["path"] + [f"6 검수({result['verdict']})"],
    }
    if result["passed"]:
        out["final_answer"] = state["draft_answer"]
    return out
