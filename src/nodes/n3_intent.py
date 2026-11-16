"""노드 3 의도 분류 (LLM, 정해진 라벨로만).

이름 메모 (2026.11.16): 기획서·README에서는 범위 밖 사유 '힘든 마음'을 '자살·자해 위험 표현', '맞장구'를 '설명 뒤 짧은 수긍'이라고 부른다.
  코드 이름은 바꾸지 않는다. '힘든 마음'은 지침(prompts/n3_intent.md)에서 LLM이 고르는 사유 이름이라 바꾸면 분류가 달라질 수 있고,
  1~4차 측정과 결과 파일 · 랭퓨즈 기록의 경로('8 범위 밖(힘든 마음)', '8 범위 밖(맞장구)')도 이 이름으로 남아 있다.
  매매 판단 '안전망'(P-044, 아래)은 기획서·README에서 '규칙 가드레일'이라고 부른다. 결과 파일 칸('안전망_작동')도 이 이름이라 그대로 둔다.

매매 판단 안전망 (P-044): LLM이 '용어 설명'으로 분류해도 질문이 사고팔기 판단을 묻는 꼴이면
'매매 판단 요청'으로 올린다 (src/safety.py). 뽑은 용어는 그대로 두어 용어 설명도 함께 나간다.

라벨: 용어 설명 / 매매 판단 요청 / 범위 밖. 범위 밖이면 사유(일반 / 불법·유해 / 하소연 / 힘든 마음).
마음이 크게 힘들다는 표현 (P-075): LLM보다 먼저 규칙으로 보고(src/safety.py), 잡히면 범위 밖(힘든 마음)으로 정한다. 경로 "3 의도 분류(위험 표현)".
민감 관용구 안전장치 (P-095): LLM이 힘든 마음으로 골랐는데 그 근거가 사전의 민감 관용구(한강 물 온도 등)뿐이면 힘든 마음을 빼고 한 번 다시 분류한다.
  손실을 자조적으로 이르는 말에 질문이 붙은 경우 질문의 답이 빠지지 않게. 상담 안내 한 문장은 끝 노드가 붙인다
설명할 용어(terms)와 종목명(ticker)도 함께 뽑는다.
라벨 밖 출력이면 1회 다시 요청하고, 그래도 실패하면 범위 밖(일반)으로 처리한다.

표준 용어 목록은 지침에 넣지 않는다. 넣으면 설정 A(정규화 없음)도 어휘가 맞춰져서
사전의 효과(RQ2 ② 조회 적중)를 잴 수 없다. 표준 용어는 [풀이]를 통해서만 들어온다.

용어 보정 (P-027): LLM이 사전 풀이의 표준 용어를 줄이거나 바꿔 쓰면("평가손실 상태가 되다" → "평가손실")
조회가 실패한다. 뽑은 용어가 사전에 없고, 이 질문의 사전 풀이 표준 용어 하나와만 겹치면 그 표준 용어로 되돌린다.
사전 풀이가 있을 때만 작동하므로 설정 A(정규화 없음)에는 영향이 없다.

규칙 분류 (P-062, config.FAST_PATH가 켜졌을 때, 설정 A 제외): "○○가 뭐야?"처럼 뜻만 묻고 ○○가 사전 표준 용어에 닿으면
LLM을 부르지 않고 용어 설명 + 그 표준 용어로 정한다 (src/fast_path.py). 경로에는 "3 의도 분류(규칙)"로 남는다.
"""
from .. import config
from ..dictionary import _key, has_sensitive_expression, load_dictionary
from ..fast_path import _MULTI, _PATTERN, simple_term_question
from ..llm import call_llm, load_prompt, parse_json
from ..safety import crisis_expression, trading_ask, weak_crisis_expression
from ..state import AgentState

NODE = "n3_intent"
LABELS = ("용어 설명", "매매 판단 요청", "범위 밖")


def _clean_reason(value: str) -> str:
    value = (value or "").strip()
    if "불법" in value or "유해" in value:
        return "불법·유해"
    if "힘든" in value or "위기" in value:
        return "힘든 마음"
    if "하소연" in value:
        return "하소연"
    return "일반"


def correct_terms(terms: list, norm_log: list) -> tuple[list, list]:
    """P-027 용어 보정. (보정한 terms, 보정 기록)을 돌려준다.

    - 사전에 그대로 있는 용어는 그대로 둔다
    - 사전에 없으면, 노드 1(사전) 풀이의 표준 용어 중 띄어쓰기를 무시하고 한쪽이 다른 쪽 안에 통째로 들어가는 것을 찾는다
    - 그런 표준 용어가 딱 하나면 그것으로 바꾸고, 없거나 둘 이상이면 손대지 않는다
    - LLM 풀이((추정)), 되묻기 대상, 종목 약어는 후보에서 뺀다. 두 글자 미만은 비교하지 않는다
    """
    d = load_dictionary()
    candidates = list(dict.fromkeys(
        x["standard"] for x in norm_log or []
        if x.get("method") == "사전" and x.get("status") != "되묻기"
        and x.get("type") != "종목 약어" and x.get("standard") and d.lookup(x["standard"])))
    fixed, notes = [], []
    for t in terms:
        k = _key(t)
        if d.lookup(t) or len(k) < 2:
            fixed.append(t)
            continue
        hits = [c for c in candidates if k in _key(c) or _key(c) in k]
        if len(hits) == 1:
            fixed.append(hits[0])
            notes.append(f"{t} → {hits[0]}")
        else:
            fixed.append(t)
    return list(dict.fromkeys(fixed)), notes


def _valid(data) -> bool:
    return isinstance(data, dict) and (data.get("intent") or "").strip() in LABELS


def intent_node(state: AgentState) -> dict:
    # P-075 마음이 크게 힘들다는 표현은 LLM 분류보다 먼저 (모든 실험 설정)
    if crisis_expression(state["raw_query"]) or crisis_expression(state.get("rewritten_query") or ""):
        return {"intent": "범위 밖", "intent_override": "", "out_reason": "힘든 마음",
                "intent_reason": "[규칙] 마음이 크게 힘들다는 표현", "terms": [], "term_fixes": [], "ticker": "",
                "path": state["path"] + ["3 의도 분류(위험 표현)"]}
    # P-097 맞장구: 앞 턴이 되묻기가 아니라 설명으로 끝났는데 이번 말이 "맞아요"·"네"뿐이면 LLM을 부르지 않고 고정 문구로
    #   (재구성이 "문어발 매수 맞아요"로 채워 새 질문처럼 다시 돌던 것을 막는다. 되묻기 뒤 "맞아요"는 노드 2가 먼저 받는다)
    hist0 = state.get("history") or []
    if hist0 and not hist0[-1].get("clarified"):
        from .n2_llm_normalize import is_confirm
        if is_confirm(state["raw_query"]):
            return {"intent": "범위 밖", "intent_override": "", "out_reason": "맞장구",
                    "intent_reason": "[규칙] 설명 뒤 맞장구", "terms": [], "term_fixes": [], "ticker": "",
                    "path": state["path"] + ["3 의도 분류(맞장구)"]}
    # P-062 규칙 분류: 뜻만 묻는 단순 질문 + 사전 용어 → LLM 없이
    if config.FAST_PATH and state["normalizer_mode"] != "A":
        term = simple_term_question(state["rewritten_query"], state.get("norm_log") or [],
                                    state.get("typo_confirm") or [], state.get("unresolved") or [])
        if term:
            return {"intent": "용어 설명", "intent_override": "", "out_reason": "",
                    "intent_reason": f"[규칙] 뜻만 묻는 질문 + 사전 용어 ({term})",
                    "terms": [term], "term_fixes": [], "ticker": "",
                    "path": state["path"] + ["3 의도 분류(규칙)"]}
    system = load_prompt(NODE)
    user = f"[질문]\n{state['annotated_query'] or state['rewritten_query']}"
    usage, errors = list(state["usage"]), list(state["errors"])

    data = None
    for attempt in range(2):
        prompt = user if attempt == 0 else user + "\n\n(직전 출력이 형식에 맞지 않았다. 정해진 JSON 형식과 라벨로만 다시 답한다.)"
        text, u = call_llm(NODE, system, prompt)
        usage.append(u)
        data = parse_json(text)
        if _valid(data):
            break
        errors.append(f"n3: 라벨 밖 출력 (시도 {attempt + 1}) ({text[:80]})")

    if not _valid(data):
        return {"intent": "범위 밖", "out_reason": "일반", "intent_reason": "분류 실패 → 범위 밖(일반) 처리",
                "terms": [], "ticker": "", "usage": usage, "errors": errors,
                "path": state["path"] + ["3 의도 분류"]}

    # P-095 민감 관용구 안전장치: 위험 표현 규칙(위)에 안 걸렸고 민감 관용구만 있는데 LLM이 힘든 마음으로 골랐으면 다시 분류
    reclass = ""
    raw = state["raw_query"]
    idiom_only = (has_sensitive_expression(raw) or any(x.get("sensitive") for x in state.get("norm_log") or [])) \
        and not weak_crisis_expression(raw)
    if data["intent"].strip() == "범위 밖" and _clean_reason(data.get("out_reason")) == "힘든 마음" and idiom_only:
        note = "\n\n(이 질문의 표현은 큰 손실을 자조적으로 이르는 관용구다. 사유 '힘든 마음'은 고르지 않고, 나머지 라벨과 사유 가운데서 다시 분류한다.)"
        text, u = call_llm(NODE, system, user + note)
        usage.append(u)
        again = parse_json(text)
        if _valid(again) and not (again["intent"].strip() == "범위 밖" and _clean_reason(again.get("out_reason")) == "힘든 마음"):
            data, reclass = again, "힘든 마음 → 다시 분류 (민감 관용구)"
        elif trading_ask(state["rewritten_query"]):
            data = {**data, "intent": "매매 판단 요청", "out_reason": ""}
            reclass = "힘든 마음 → 매매 판단 요청 (민감 관용구 + 사고팔기 질문)"

    intent = data["intent"].strip()
    terms = data.get("terms") or []
    if isinstance(terms, str):
        terms = [t.strip() for t in terms.split(",")]
    terms = [t.strip() for t in terms if isinstance(t, str) and t.strip()]
    ticker = data.get("ticker") or ""
    if isinstance(ticker, list):
        ticker = ", ".join(str(t) for t in ticker)

    terms, term_fixes = correct_terms(list(dict.fromkeys(terms)), state.get("norm_log") or [])

    # P-097 사전이 이미 오타로 이은 표현("삼젼=삼전(오타로 보임)")을 용어로 다시 뽑으면 고친 사전 말로 바꾼다
    #   (그대로 두면 다시 조회해도 없어서 사전에 있는 말에 "사전에 등록되지 않은 용어" 안내가 붙는다)
    #   종목 약어("삼젼=삼전=삼성전자")는 용어로 조회하지 않으므로 뺀다 (종목 약어 풀이는 답변 노드가 풀이에서 읽는다)
    dd = load_dictionary()
    linked = {}
    for x in state.get("norm_log") or []:
        if x.get("method") == "사전" and x.get("type") == "오타" and x.get("standard"):
            kind = (dd.near_targets.get(_key(x.get("via") or "")) or ("", ""))[1]
            linked[_key(x["expr"])] = None if kind == "종목 약어" or not dd.lookup(x["standard"]) else x["standard"]
    if linked:
        swapped = [linked.get(_key(t), t) for t in terms]
        if swapped != terms:
            term_fixes = term_fixes + [f"{a} → {b or '(종목 약어라 뺌)'} (사전이 이은 말)" for a, b in zip(terms, swapped) if a != b]
            terms = list(dict.fromkeys(t for t in swapped if t))

    # P-097 뽑은 용어를 사용자가 친 글자와 대조한다 (LLM이 뽑은 용어를 그대로 믿지 않는다)
    typo_confirm = list(state.get("typo_confirm") or [])
    q0 = state["rewritten_query"]
    d0 = load_dictionary()
    #  ① 용어를 하나도 안 뽑았는데 "○○이 뭐야?" 꼴이면 ○○을 용어로 ("삼젼이 뭐야?" → 삼젼 → 조회 실패 → 노드 2가 사전으로 잇는다)
    if intent == "용어 설명" and not terms:
        qq = q0.strip().rstrip("?!. ").strip()
        m0 = None if _MULTI.search(qq) else _PATTERN.match(qq)
        if m0 and m0.group("expr").strip():
            e0 = m0.group("expr").strip()
            terms = [t for t in [linked.get(_key(e0), e0)] if t]  # 사전이 이미 이은 표현이면 고친 사전 말로 (종목 약어는 뺌)
            if terms:
                term_fixes = term_fixes + [f"(용어 없음) → {terms[0]}"]
    #  ② 뽑은 용어가 사전에 있는데 질문에는 그 글자가 없고, 질문에 그 말과 오타 관계인 글자가 있으면 고쳐 읽은 것으로 적는다
    #     ("시가춍액이 뭐야?" → 시가총액). 오타 확인 문구가 붙는다
    from .n2_llm_normalize import _raw_form
    #     사전 풀이가 준 표준 용어("손절해야 해?"의 손절 → 손절매)는 LLM이 고쳐 뽑은 것이 아니므로 뺀다
    #     (4차 개발용 3회에서 "'손절해'를 '손절매'로 보고 설명드릴게요"가 2턴 잘못 붙음)
    dict_stds = {_key(x.get("standard") or "") for x in state.get("norm_log") or [] if x.get("method") == "사전"}
    for t in terms:
        kt = _key(t)
        if len(kt) < 2 or kt in _key(q0) or not d0.lookup(t) or kt in dict_stds:
            continue
        rawf = _raw_form(kt, q0)
        if rawf and _key(rawf) != kt and not d0.lookup(rawf) and _key(rawf) not in d0.near_targets \
                and _key(rawf) not in d0.near_exceptions and not any(x["typo"] == rawf for x in typo_confirm):
            typo_confirm.append({"typo": rawf, "original": t})
            term_fixes = term_fixes + [f"{rawf} → {t} (오타로 읽음)"]

    # 매매 판단 안전망 (P-044): 용어 설명으로 분류했어도 질문이 사고팔기 판단을 묻는 꼴이면 매매 판단 요청으로 올린다
    override = reclass
    if intent == "용어 설명" and trading_ask(state["rewritten_query"]):
        intent, override = "매매 판단 요청", (reclass + " / " if reclass else "") + "용어 설명 → 매매 판단 요청"

    out_reason = _clean_reason(data.get("out_reason")) if intent == "범위 밖" else ""
    reason = str(data.get("intent_reason") or "")
    # P-090: 앞 턴이 되묻기·짐작 확인으로 끝났고 이번 말이 그 표현의 뜻을 알려 준 것(사용자 설명)이면
    #   하소연·범위 밖(일반)으로 보내지 않고 그 표현의 설명으로 잇는다 ("급등이래", "한 번에 크게 나오는 매도 물량이래")
    history = state.get("history") or []
    told = [x["expr"] for x in state.get("norm_log") or [] if x.get("user_defined")]
    if intent == "범위 밖" and out_reason in ("하소연", "일반") and history and (history[-1].get("clarified") or history[-1].get("explained")) and told:
        intent, out_reason, override = "용어 설명", "", "범위 밖 → 용어 설명 (되묻기에 답함)"
        terms = [told[0]]
        reason = "[규칙] 앞 턴 되묻기에 뜻을 알려 준 답"

    return {
        "intent": intent,
        "intent_override": override,
        "out_reason": out_reason,
        "intent_reason": reason,
        "terms": terms,
        "term_fixes": term_fixes,
        "typo_confirm": typo_confirm,
        "ticker": str(ticker).strip(),
        "usage": usage,
        "errors": errors,
        "path": state["path"] + ["3 의도 분류"],
    }
