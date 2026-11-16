"""노드 5 답변 생성 (LLM, 의도별 지침).

- 용어 사전 조회 결과(term_info)를 근거로 답한다
- 사전에 없는 용어는 일반 설명 → grounded에 "사전 근거 없음".
  사전 밖 안내 첫 문장은 LLM이 쓰지 않고 코드가 사용자가 쓴 말 그대로 붙인다 (P-094, "'상폐'는 사전에 등록되지 않은 용어라…")
- LLM이 뜻을 모르면 "[모름]"만 내고, 코드가 되묻기 문장으로 바꾼다 (P-092). 다음 턴은 되묻기 뒤 턴으로 다룬다
- 매매 판단 요청은 판단 불가 안내(R1)를 맨 앞에
- 검수(노드 6)에서 걸려 돌아온 경우: 직전 답변과 위반 목록을 지침에 넣고 retry_count를 1 올린다
- 하소연 (P-070): 범위 밖(하소연)이면 LLM은 공감 한 문장만 쓰고, 그 뒤에 서비스 안내와 용어 제안 고정 문장을 붙인다. 검수를 거친다
"""
import re

from ..dictionary import _key
from ..fixed_messages import (COMFORT_FALLBACK, COMFORT_OFFER, COMFORT_OFFER_NONE, COMFORT_TAIL, SAFE_ANSWER, TRADING_NOTICE,
                              UNKNOWN_MARK, clarify_message, ungrounded_notice)
from ..llm import call_llm, format_history, load_prompt
from ..state import AgentState

NODE = "n5_answer"
RETRY_NODE = "n5_answer_retry"  # P-028: 출력 상한에 걸렸을 때 생각을 줄여 다시 쓰는 호출 (지침은 같음)


def _term_block(term_info: list) -> str:
    if not term_info:
        return "(조회한 용어 없음)"
    lines = []
    for t in term_info:
        if t["found"]:
            lines.append(f"- {t['term']}: (사전 근거) {t['description']}")
        else:
            lines.append(f"- {t['term']}: (사전에 없음)")
    return "\n".join(lines)


def _slang_block(norm_log: list) -> str:
    lines = []
    for x in norm_log:
        if x.get("status") == "되묻기" or not x.get("standard"):
            continue
        if x.get("sensitive"):
            lines.append(f"- '{x['expr']}' → '{x['standard']}' (민감 표현: {x.get('note', '')})")
        elif x["type"] == "관용구" and x.get("method") == "사전" and x.get("meaning") and x["meaning"] != x["standard"]:
            lines.append(f"- '{x['expr']}' → 관용구 뜻 '{x['meaning']}', 표준 용어 '{x['standard']}'")
        elif x["type"] == "종목 약어":
            lines.append(f"- '{x['expr']}' → 종목 {x['standard']}")
        elif x.get("user_defined"):
            lines.append(f"- '{x['expr']}' → {x['standard']} (사용자가 설명해 준 뜻)")
        elif x["method"] == "LLM":
            lines.append(f"- '{x['expr']}' → {x['standard']} (LLM 풀이, 사전 근거 없음)")
        elif x.get("via"):
            # 오타: 표준 안내에는 고친 표현을 쓴다 ('게미' → '개미'는 '개인투자자')
            lines.append(f"- '{x['expr']}'(오타, '{x['via']}'로 봄) → '{x['standard']}'. 안내할 때는 '{x['via']}'로 쓴다")
        else:
            lines.append(f"- '{x['expr']}' → '{x['standard']}'")
    return "\n".join(lines) or "(없음)"


def _typo_block(typo_confirm: list) -> str:
    if not typo_confirm:
        return "(없음)"
    return "\n".join(f"- 오타 '{t['typo']}' → '{t['original']}'로 보고 답함" for t in typo_confirm)


def _comfort_offer(norm_log: list) -> str:
    """하소연에 붙일 용어 제안: 질문 속 사전 풀이 표현 하나 (종목 약어·민감 표현 제외)"""
    for x in sorted(norm_log or [], key=lambda x: x.get("pos", 9999)):
        if x.get("method") == "사전" and x.get("type") != "종목 약어" and not x.get("sensitive") and x.get("status") != "되묻기":
            return COMFORT_OFFER.format(expr=x.get("base") or x["expr"])  # P-084: 활용형("물려") 대신 기본형("물리다")
    return COMFORT_OFFER_NONE


_NOTICE_SENT = re.compile(r"'[^'\n]+'[은는이가]?\s*사전에 등록되지 않은 (용어|내용)(이)?라 일반적인 설명으로 안내해요\.?[ \t]*")
_REFUSAL_HEAD = re.compile(r"(판단|추천|조언|말씀|알려)\s?(해\s?)?(드릴|할)\s?수\s?없")


def user_surface(term: str, state: AgentState) -> str | None:
    """사전에 없는 용어를 사용자가 질문에 쓴 말로 되돌린다 (P-094). '상장폐지' → '상폐', '최고점' → '정수리에 샀다'.
    질문에 그런 말이 없으면 None ("팔고 나서 다시 사는 걸 뭐라고 불러?"의 '재매수')"""
    k = _key(term)
    query = state.get("rewritten_query") or state["raw_query"]
    if k and k in _key(query):
        return term
    for x in state.get("norm_log") or []:
        if x.get("method") == "LLM" and not x.get("user_defined") and x.get("expr") in query:
            if k and (k in _key(x.get("standard", "")) or k in _key(x["expr"])):
                return x["expr"]
    return None


def with_notice(text: str, surfaces: list, trading: bool) -> str:
    """사전 밖 안내 첫 문장을 코드가 붙인다 (P-094). LLM이 같은 문장을 썼으면 지운다.
    판단 불가 안내나 오타 확인 문구가 첫 줄이면 그 바로 뒤에 둔다"""
    lines = [ln.strip() for ln in _NOTICE_SENT.sub("", text or "").splitlines() if ln.strip()]
    at = 0
    while at < len(lines) and at < 2 and (_REFUSAL_HEAD.search(lines[at]) or "보고 설명드릴게요" in lines[at]):
        at += 1
    if trading and at == 0 and lines and _REFUSAL_HEAD.search(lines[0]):
        at = 1
    lines.insert(at, ungrounded_notice(surfaces))
    return "\n".join(lines)


def comfort_node(state: AgentState, retry: int, prev: dict, is_retry: bool) -> dict:
    """P-070 하소연: 공감 한 문장(LLM) + 서비스 안내 + 용어 제안"""
    sections = [f"[질문]\n{state['rewritten_query'] or state['raw_query']}", "[의도]\n하소연",
                f"[앞 대화]\n{format_history(state.get('history') or [])}"]
    if is_retry:
        v = "\n".join(f"- {x.get('item')}: \"{x.get('sentence')}\" — {x.get('reason')}"
                      for x in prev.get("violations", [])) or "- 판정 형식 오류"
        sections.append(f"[직전 답변]\n{state['draft_answer']}")
        sections.append(f"[검수 위반 — 이 부분을 고쳐 다시 쓴다]\n{v}")
        retry += 1
    text, usage = call_llm(NODE, load_prompt(NODE), "\n\n".join(sections))
    errors = list(state.get("errors") or [])
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    if not first:
        errors.append("n5: 하소연 공감 문장이 비어 고정 문장으로 대체")
        first = COMFORT_FALLBACK
    draft = f"{first}\n{COMFORT_TAIL} {_comfort_offer(state.get('norm_log'))}"
    return {"draft_answer": draft, "grounded": [], "guess_confirm": False, "asked_back": False, "retry_count": retry,
            "usage": state["usage"] + [usage], "errors": errors,
            "path": state["path"] + [f"5 답변 생성(하소연{', 재생성 ' + str(retry) if is_retry else ''})"]}


def answer_node(state: AgentState) -> dict:
    retry = state.get("retry_count", 0)
    prev = state.get("compliance") or {}
    is_retry = bool(prev) and not prev.get("passed", True)
    if state.get("intent") == "범위 밖" and state.get("out_reason") == "하소연":
        return comfort_node(state, retry, prev, is_retry)

    sections = [
        f"[질문]\n{state['annotated_query'] or state['rewritten_query']}",
        f"[의도]\n{state['intent']}",
        f"[종목]\n{state['ticker'] or '(없음)'}",
        f"[용어 사전 조회]\n{_term_block(state['term_info'])}",
        f"[질문 속 비표준 표현 → 표준 표현]\n{_slang_block(state['norm_log'])}",
        f"[오타 확인]\n{_typo_block(state['typo_confirm'])}",
        f"[앞 대화]\n{format_history(state.get('history') or [])}",
    ]
    if state.get("user_words_terms"):  # P-088: 사용자 설명 안에 든 사전 말 (사전 근거)
        sections.append("[사용자 설명 속 사전 용어 (사전 근거)]\n" + "\n".join(
            f"- 사용자 설명의 '{n['part']}' → '{n['standard']}': {n['description']}" for n in state["user_words_terms"]))
    if state.get("related_terms"):
        sections.append("[함께 궁금해할 만한 용어 (사전에 있음)]\n" + "\n".join(f"- {t}" for t in state["related_terms"]))
    if is_retry:
        v = "\n".join(f"- {x.get('item')}: \"{x.get('sentence')}\" — {x.get('reason')}"
                      for x in prev.get("violations", [])) or "- 판정 형식 오류"
        sections.append(f"[직전 답변]\n{state['draft_answer']}")
        sections.append(f"[검수 위반 — 이 부분을 고쳐 다시 쓴다]\n{v}")
        retry += 1

    user = "\n\n".join(sections)
    text, usage = call_llm(NODE, load_prompt(NODE), user)
    usages = [usage]
    errors = list(state.get("errors") or [])
    if usage.get("finish_reason") == "length":
        # P-028: 출력 상한에 걸리면 답이 중간에 잘린 채 나갈 수 있다 → 생각을 줄여 한 번 다시 쓴다
        errors.append("n5: 출력 상한에 걸림 → 생각을 줄여 한 번 다시 씀")
        text, usage = call_llm(RETRY_NODE, load_prompt(NODE), user)
        usages.append(usage)
        if usage.get("finish_reason") == "length":
            errors.append("n5: 다시 써도 출력 상한에 걸림 → 안전 답변으로 대체")
            text = SAFE_ANSWER
    if not text.strip():
        # P-015: 생각에 토큰을 다 써서 답이 비면 빈 답을 내보내지 않고 안전 답변으로 대신한다
        errors.append("n5: 빈 답변 → 안전 답변으로 대체")
        text = SAFE_ANSWER

    grounded = [{"term": t["term"], "grounded": "사전 근거" if t["found"] else "사전 근거 없음"}
                for t in state["term_info"]]
    # 사전에 없는 용어 가운데 사용자가 뜻을 알려 준 것은 따로 답한다 ("들으신 뜻" 문장, 사전 밖 안내 없음)
    told = {_key(x["expr"]) for x in state.get("norm_log") or [] if x.get("user_defined")}
    unknown = [t["term"] for t in state["term_info"] if not t["found"] and _key(t["term"]) not in told]
    trading = state.get("intent") == "매매 판단 요청"
    out = {"guess_confirm": False, "asked_back": False}
    label = "5 답변 생성"
    if UNKNOWN_MARK in text and text != SAFE_ANSWER:
        # P-092: LLM이 뜻을 모른다고 표시 → 지어내지 않고 되묻기 문장으로 바꾼다
        exprs = [user_surface(t, state) or t for t in unknown] or [t["term"] for t in state["term_info"] if not t["found"]]
        if exprs:
            text = clarify_message(list(dict.fromkeys(exprs)))
            if trading:
                text = f"{TRADING_NOTICE}\n{text}"
            out = {"guess_confirm": False, "asked_back": True,
                   "unresolved": [{"expr": e, "reason": "노드 5도 뜻을 모름"} for e in dict.fromkeys(exprs)]}
            label = "5 답변 생성(뜻 모름 → 되묻기)"
        else:
            text = text.replace(UNKNOWN_MARK, "").strip() or SAFE_ANSWER
    elif unknown and text != SAFE_ANSWER:
        # P-094: 사전 밖 안내 첫 문장은 코드가 사용자가 쓴 말 그대로 붙인다
        text = with_notice(text, [s for s in (user_surface(t, state) for t in unknown) if s], trading)
    return {
        "draft_answer": text,
        "grounded": grounded,
        **out,
        "retry_count": retry,
        "usage": state["usage"] + usages,
        "errors": errors,
        "path": state["path"] + [f"{label}{' (재생성 ' + str(retry) + ')' if is_retry else ''}"],
    }
