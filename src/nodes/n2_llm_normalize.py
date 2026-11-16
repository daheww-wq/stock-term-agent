"""노드 2 LLM 정규화.

이름 메모 (2026.11.16): 기획서·README에서는 known("아는 말")을 '기본 어휘'라고 부른다.
  known은 지침(prompts/n2_llm_normalize.md)의 출력 칸 이름이라 바꾸지 않는다 (바꾸면 LLM 출력이 달라질 수 있음).

사전이 못 푼 관용구·신조어에 LLM이 풀이를 덧붙인다.
- 노드 1이 붙인 풀이는 바꾸지 않는다 (같은 표현이면 버림)
- LLM은 뜻을 세 갈래로 적는다 (P-056): 확신(그 뜻으로 쓰이는 걸 앎) → (추정) 풀이 / 짐작(생김새·비유에서 떠올림) / 모름 → unresolved.
  짐작은 풀이로 쓰지 않는다 (P-092, 11.12 본인 결정): 지어낸 뜻을 말하지 않고 모름과 똑같이 되묻는다
- LLM은 뜻을 묻는 말이 실제로 쓰는 말이라 풀이를 붙이지 않았으면 known("아는 말")에 적는다 (P-093).
  어느 칸에도 없는 말은 사전 말의 오타 후보로 본다 ("고가"는 아는 말, "공메도"는 아무 칸에도 없음)
- 질문 이해에 꼭 필요한데 못 푼 표현만 unresolved로 올린다 → 노드 9 되묻기
- 출력 형식이 깨지면 풀이를 추가하지 않고 넘어간다 (errors에 기록)
실험 설정 C에서는 모든 질문에, 설정 D에서는 사전 조회가 실패했을 때만 돈다 (P-042).

LLM을 부르기 전과 뒤에 사전으로 다시 잇는다 (P-069·P-072·P-076·P-077). 이 노드는 설정 A·B에서 돌지 않으므로 기준선은 그대로다.
- 확인 답 (P-076): 앞 턴이 후보 하나를 보여 준 되묻기로 끝났고 이번 말이 "맞아요"류이면, 후보를 사용자가 확인한 오타로 적고 LLM을 부르지 않는다
- 되묻기 뒤 짧은 대답 (P-092): "몰라요" → 노드 9가 확인된 뜻이 없다고 말하고 끝 / "다른 뜻이에요"·확인할 후보가 없는 "맞아요" → 노드 9가 다시 묻는다.
  LLM을 부르지 않는다 (경로 "2 짧은 대답(…)")
- 잇기 1 (P-069): 노드 4가 못 찾은 용어가 사전의 은어·종목 약어 그대로이면 사전 풀이로 바꾼다 (LLM이 "쏜절"을 "손절"로 고쳐 넘긴 경우).
  LLM 풀이 어디에든 사전 말이 있고 원래 표현과 자모가 가까우면 같은 방법으로 사전 풀이로 바꾼다 (P-093, "숀졀=손해를 보고 팖(손절)")
- 잇기 2 (P-069): 노드 4가 못 찾은 용어가 사전 말 하나와 자모 하나만 다르면 그 말의 오타로 본다 (확인 문구, 확정하지 않음)
  그 사전 말이 표준 용어이면 LLM 뒤로 미룬다 (P-080): LLM이 그 말을 확신으로 풀었거나 아는 말로 적었으면 잇지 않는다 (P-093).
  사전에 없는 실제 말("고가"·"미수"·"배수")을 표준 용어("호가"·"매수")의 오타로 읽지 않게. 은어·종목 약어는 LLM 앞에서 잇는다
- 후보로만 묻기 (P-072): 남은 말이 사전 말과 글자마다 자모 하나까지 다르면 고치지 않고 되묻기에 후보를 함께 보여 준다.
  후보가 둘이면 둘 다 보여 준다 (P-093, "쏜절" → 손절·본절). LLM이 확신으로 푼 말은 은어·종목 약어 후보만 본다 ("고가"를 표준 용어 "호가"로 묻지 않게)
- 사용자 설명이 사전 용어 이름 그대로이면 그 이름을 뜻으로 적는다 (P-077, "급등이래" → 급등). 가까운 표준 용어 조회(P-056)가 되게
잇기 1·2와 확인 답만으로 못 찾은 용어가 모두 풀리면 LLM을 부르지 않는다 (경로 "2 사전 잇기" / "2 확인 답").
"""
import json
import re

from ..dictionary import _key, jamo_gaps, load_dictionary, near_words, render_annotation
from ..llm import call_llm, format_history, load_prompt, parse_json
from ..state import AgentState

NODE = "n2_llm_normalize"

# "맞아요" 빠른 답과 같은 뜻의 짧은 확인 답 (띄어쓰기·문장부호를 뺀 글자로 비교)
CONFIRM_WORDS = {"맞아요", "맞아", "맞습니다", "맞음", "네", "넵", "응", "웅", "예", "ㅇㅇ", "네맞아요", "응맞아", "예맞아요",
                 "그거맞아요", "그거맞아", "그뜻맞아요", "그뜻맞아", "그거예요", "그거야", "네그거예요", "응그거야"}
# 되묻기 뒤 짧은 대답 (P-092)
OTHER_WORDS = {"다른뜻이에요", "다른뜻이야", "다른뜻", "다른거예요", "다른거야", "아니에요", "아니예요", "아니요", "아니야", "아니", "아뇨",
               "그뜻아니에요", "그뜻아니야", "그거아니에요", "그거아니야"}
DONTKNOW_WORDS = {"몰라요", "몰라", "모르겠어요", "모르겠어", "모르겠음", "모름", "잘몰라요", "잘몰라", "잘모르겠어요", "잘모르겠어",
                  "나도몰라", "나도몰라요", "저도몰라요", "저도모르겠어요", "나도모르겠어", "뜻은몰라요", "뜻은몰라", "뜻몰라요", "뜻몰라"}
EXPLAIN_TAIL = re.compile(r"(이)?(래요|래|라고\s*(부른대|부르더라|하더라|해요|해)|라던데|말한\s*거야|말한\s*거예요|이야|야|예요|이에요|요)\s*[.!~]*$")


# P-097 설명 뒤에 사용자가 뜻을 말해 주는 끝말 ("…래", "…라던데", "…라고 부른대")
TELL_TAIL = re.compile(r"(래요|래|라던데요?|라고\s*(부른대|부르더라|하더라|하던데)|부른대|한대)\s*[.!~]*$")


def _short(text: str) -> str:
    return re.sub(r"[\s.,!~?]", "", text or "")


def is_confirm(text: str) -> bool:
    return _short(text) in CONFIRM_WORDS


def is_other(text: str) -> bool:
    return _short(text) in OTHER_WORDS


def is_dontknow(text: str) -> bool:
    return _short(text) in DONTKNOW_WORDS


def _entry_dict(expr: str, word: str, target: str, kind: str, query: str, typo: bool) -> dict:
    """사전 풀이 한 줄 (노드 1이 붙이는 것과 같은 모양)"""
    pos = query.find(expr)
    if typo:
        ann = f"{expr}={word}(오타로 보임)" + (f"={target}" if target != word else "")
        return {"pos": pos if pos >= 0 else 9999, "expr": expr, "standard": target, "type": "오타", "method": "사전",
                "via": word, "annotation": ann, "linked": True}
    ann = f"{expr}={target}" if target != expr else expr
    return {"pos": pos if pos >= 0 else 9999, "expr": expr, "standard": target, "type": kind, "method": "사전",
            "annotation": ann if target != expr else "", "linked": True}


def _typo_like(a: str, b: str) -> bool:
    """두 말이 오타 관계로 보일 만큼 가까운가 (글자 수 같고, 글자마다 자모 하나까지, 모두 합쳐 둘까지)"""
    g = jamo_gaps(_key(a), _key(b))
    return bool(g) and 1 <= sum(g) <= 2 and max(g) <= 1


def _dict_word_in(expr: str, meaning: str, d) -> str | None:
    """LLM 풀이 글 안에 든 사전 말 가운데 원래 표현과 오타 관계인 것 (P-093). 긴 말부터 본다"""
    m = _key(meaning)
    for w in sorted(d.near_targets, key=len, reverse=True):
        if len(w) >= 2 and w in m and _typo_like(expr, w):
            return w
    return None


def _raw_form(word: str, query: str) -> str | None:
    """질문 속에서 사전 말 word로 고쳐 읽힐 원래 글자 (그대로 있으면 그 말, 없으면 자모가 가까운 구간)"""
    if word in query:
        return word
    n = len(word)
    for i in range(len(query) - n + 1):
        win = query[i:i + n]
        if _typo_like(win, word):
            return win
    return None


def link_term(term: str, query: str, d=None, standard: bool = True) -> tuple[dict | None, dict | None]:
    """잇기 1·2. (풀이 한 줄, 오타 확인) 또는 (None, None). standard=False면 잇기 2에서 표준 용어는 잇지 않는다 (P-080)"""
    d = d or load_dictionary()
    key = _key(term)
    if key in d.near_exceptions:
        return None, None
    tgt = d.near_targets.get(key)
    if tgt:  # 잇기 1: 사전 말 그대로
        if key in _key(query):
            return None, None  # 질문에 그대로 있는데 노드 1이 풀지 않은 말(오탐 예외)은 다시 잇지 않는다
        target, kind = tgt
        raw = _raw_form(key, query)
        if raw:
            return _entry_dict(raw, key, target, kind, query, True), {"typo": raw, "original": key}
        return _entry_dict(key, key, target, kind, query, False), None
    hits = near_words(key, d)  # 잇기 2: 자모 하나 차이, 후보가 딱 하나
    if len(hits) == 1:
        word, (target, kind) = hits[0]
        if kind == "표준 용어" and not standard:
            return None, None
        expr = term if term in query else (_raw_form(word, query) or term)
        return _entry_dict(expr, word, target, kind, query, True), {"typo": expr, "original": word}
    return None, None


def llm_normalize_node(state: AgentState) -> dict:
    query = state["rewritten_query"]
    norm_log = list(state["norm_log"])
    unresolved = list(state["unresolved"])
    typo_confirm = list(state.get("typo_confirm") or [])
    errors = list(state["errors"])
    d = load_dictionary()
    history = state.get("history") or []
    last = history[-1] if history else {}
    steps = []

    def has(expr):
        return any(_key(x["expr"]) == _key(expr) for x in norm_log)

    def add_typo(t):
        if t and not any(x["typo"] == t["typo"] for x in typo_confirm):
            typo_confirm.append(t)

    # 되묻기 뒤 짧은 대답 (P-092): "몰라요" → 확인된 뜻 없음으로 끝 / "다른 뜻이에요"·후보 없는 "맞아요" → 다시 묻기
    asked = [e for e in (last.get("asked") or []) if e]
    one_cand = list(last.get("candidates") or [])
    if last.get("clarified") and asked:
        raw = state["raw_query"]
        kind = "모름" if is_dontknow(raw) else "다시" if (is_other(raw) or (is_confirm(raw) and not one_cand)) else ""
        if kind:
            return {"annotated_query": render_annotation(query, norm_log), "norm_log": norm_log,
                    "unresolved": [{"expr": e, "reason": "되묻기에 짧게 답함"} for e in asked], "clarify_kind": kind,
                    "typo_confirm": typo_confirm, "errors": errors,
                    "path": state["path"] + [f"2 짧은 대답({'몰라요' if kind == '모름' else '다시 묻기'})"]}

    # P-097 설명 뒤 사용자 설명: 앞 턴이 사전에 없는 말을 설명한 턴이고 이번 말이 "…래"로 뜻을 알려 주면
    #   되묻기 뒤와 똑같이 사용자 설명으로 받는다 (LLM을 부르지 않는다. 경로 "2 사용자 설명")
    explained = [e for e in (last.get("explained") or []) if e]
    if explained and not last.get("clarified") and TELL_TAIL.search(state["raw_query"].strip()):
        expr = next((e for e in explained if e in query), explained[0])
        said = state["raw_query"].strip()
        said = re.sub(rf"^{re.escape(expr)}\s*(은|는|이|가|이란|란)?\s*", "", said)
        # 끝말은 한 번만 뗀다 (11.13: "…사는 거래래"에서 '래'를 두 번 떼어 "…사는 거"가 되던 것. 4차 개발용 K21-05)
        cut = TELL_TAIL.sub("", said)
        if cut == said:
            cut = EXPLAIN_TAIL.sub("", said)
        said = re.sub(r"(을|를)?\s*그렇게\s*$", "", cut.strip()).strip() or said
        if not has(expr):
            said = d.standard_by_key.get(_key(said)) or said
            pos = query.find(expr)
            norm_log.append({"pos": pos if pos >= 0 else 9999, "expr": expr, "standard": said, "type": "기타",
                             "method": "LLM", "user_defined": True, "guess": False,
                             "annotation": f"{expr}={said}(사용자 설명)"})
            return {"annotated_query": render_annotation(query, norm_log), "norm_log": norm_log, "unresolved": unresolved,
                    "clarify_kind": "", "typo_confirm": typo_confirm, "errors": errors,
                    "path": state["path"] + ["2 사용자 설명"]}

    # 확인 답 (P-076): 앞 턴이 보여 준 후보 하나를 사용자가 "맞아요"로 확인
    confirmed = False
    if last.get("clarified") and is_confirm(state["raw_query"]):
        for c in one_cand:
            tgt = d.near_targets.get(c["candidate"])
            if tgt and not has(c["expr"]):
                norm_log.append(_entry_dict(c["expr"], c["candidate"], tgt[0], tgt[1], query, True))
                unresolved = [u for u in unresolved if u["expr"] != c["expr"]]
                confirmed = True
    if confirmed:
        steps.append("2 확인 답")

    # 잇기 1·2 (P-069): 노드 4가 못 찾은 용어 (설정 D에서 조회 뒤에 올 때만 있음)
    missing = [t["term"] for t in state.get("term_info") or [] if not t.get("found")
               and not any(_key(u["expr"]) == _key(t["term"]) for u in unresolved)]  # 사전 되묻기 오타(빛투)는 잇지 않고 되묻기 그대로
    unlinked = []
    for term in missing:
        if has(term) and any(x.get("linked") for x in norm_log if _key(x["expr"]) == _key(term)):
            continue
        entry, typo = link_term(term, query, d, standard=False)
        if entry and not has(entry["expr"]):
            norm_log.append(entry)
            add_typo(typo)
        elif not entry:
            unlinked.append(term)
    if missing and len(unlinked) < len(missing):
        steps.append("2 사전 잇기")

    if (confirmed and not unlinked) or (missing and not unlinked):
        return {"annotated_query": render_annotation(query, norm_log), "norm_log": norm_log, "unresolved": unresolved,
                "typo_confirm": typo_confirm, "errors": errors, "path": state["path"] + steps}

    existing = [{"표현": x["expr"], "풀이": x.get("standard", ""), "유형": x["type"]}
                for x in norm_log]
    user = (
        f"[현재 질문]\n{render_annotation(query, norm_log)}\n\n"
        f"[이미 붙은 풀이 (바꾸지 않음)]\n{json.dumps(existing, ensure_ascii=False) if existing else '(없음)'}\n\n"
        f"[앞 대화]\n{format_history(history)}"
    )
    text, usage = call_llm(NODE, load_prompt(NODE), user)
    data = parse_json(text)
    llm_unknown = set()  # LLM이 모른다고 밝혔거나 짐작만 한 표현
    llm_known = set()    # LLM이 실제로 쓰는 말이라고 적은 표현 (P-093 "아는 말")
    guessed = []         # LLM이 짐작으로 푼 표현 (P-092: 풀이로 쓰지 않고 되묻는다)
    no_info = data is None

    if data is None:
        errors.append(f"n2: JSON 형식 깨짐 → 풀이 추가 없음 ({text[:80]})")
    else:
        taken = {x["expr"] for x in norm_log}
        # 노드 1(사전) 풀이 구간. LLM 풀이가 이 구간 안에 들어가거나 사전 관용구와 겹치면 버린다 (노드 1 풀이 고정)
        dict_spans = [(x["pos"], x["pos"] + len(x["expr"]), x["type"]) for x in norm_log
                      if x.get("method") == "사전" and x.get("pos", 9999) != 9999 and x.get("annotation")]

        def conflicts(ps, pe):
            for ds, de, typ in dict_spans:
                inside = ds <= ps and pe <= de
                overlap = ps < de and ds < pe
                if inside or (typ == "관용구" and overlap):
                    return True
            return False

        for a in data.get("additions") or []:
            expr, meaning = (a.get("expr") or "").strip(), (a.get("meaning") or "").strip()
            # 노드 1이 이미 푼 표현과 같은 표현이면 버린다 (노드 1 풀이 고정).
            # 처음 보는 관용구가 노드 1의 용어를 품은 경우("총알 다 떨어졌다" ⊃ 총알)는 새 풀이로 받는다
            if not expr or not meaning or expr in taken:
                continue
            # 사용자가 앞 턴에서 설명해 준 뜻이면 표시를 따로 둔다 (풀이 문장에 섞이면 조회할 용어가 깨짐)
            user_defined = (a.get("source") or "").strip() == "사용자 설명"
            guess = (a.get("confidence") or "").strip() == "짐작" and not user_defined
            if meaning.startswith("사용자 설명"):
                user_defined = True
                meaning = meaning.split(":", 1)[-1].strip() if ":" in meaning else meaning[len("사용자 설명"):].strip()
            pos = query.find(expr)
            if pos >= 0 and conflicts(pos, pos + len(expr)):
                continue
            # 잇기 1 (P-069·P-093): LLM 풀이 어디에든 사전 말이 있고 원래 표현과 오타 관계면 사전 풀이로
            #   ("쥽쥽=줍줍(저가 매수)", "숀졀=손해를 보고 팖(손절)", "뗙샹=급격한 가격 상승(떡상의 오타)")
            word = None if user_defined or _key(expr) in d.near_exceptions else _dict_word_in(expr, meaning, d)
            if word:
                tgt = d.near_targets[word]
                norm_log.append(_entry_dict(expr, word, tgt[0], tgt[1], query, True))
                add_typo({"typo": expr, "original": word})
                taken.add(expr)
                if "2 사전 잇기" not in steps:
                    steps.append("2 사전 잇기")
                continue
            # P-092: 짐작은 풀이로 쓰지 않는다. 뜻을 말하지 않고 모름과 똑같이 되묻는다
            if guess:
                guessed.append(expr)
                llm_unknown.add(_key(expr))
                continue
            # 사용자 설명이 사전 용어 이름 그대로면 그 이름을 뜻으로 (P-077)
            if user_defined:
                said = state["raw_query"].strip()
                said = re.sub(rf"^{re.escape(expr)}\s*(은|는|이|가|이란|란)?\s*", "", said)
                said = EXPLAIN_TAIL.sub("", said).strip()
                exact = d.standard_by_key.get(_key(said))
                if exact:
                    meaning = exact
            norm_log.append({
                "pos": pos if pos >= 0 else 9999,
                "expr": expr, "standard": meaning,
                "type": a.get("kind") or "관용구", "method": "LLM",
                "user_defined": user_defined,
                "guess": False,
                # P-016: LLM 풀이는 (추정), 사용자 설명은 (사용자 설명) 표시. 노드 3이 사전 풀이를 우선하게 한다
                "annotation": f"{expr}={meaning}" + ("(사용자 설명)" if user_defined else "(추정)"),
            })
            taken.add(expr)
        for u in data.get("unresolved") or []:
            expr = (u.get("expr") or "").strip()
            if expr:
                llm_unknown.add(_key(expr))
            if expr and expr not in taken and not any(x["expr"] == expr for x in unresolved):
                unresolved.append({"expr": expr, "reason": u.get("reason", "")})
        for k in data.get("known") or []:
            if isinstance(k, str) and k.strip():
                llm_known.add(_key(k))

    # P-093: 못 찾은 용어를 사전 말의 오타로 볼지는 LLM이 그 말을 어떻게 적었는지로 정한다
    #   확신으로 푼 표현 안에 든 말("바닥 찍은"의 "바닥")이나 아는 말로 적은 말("고가")은 오타로 보지 않는다.
    #   모른다고 했거나, 짐작만 했거나, 어느 칸에도 적지 않은 말("공메도")은 사전과 대조한다
    def confident(term):
        k = _key(term)
        return any(k and k in _key(x["expr"]) and x.get("method") == "LLM" and not x.get("user_defined") for x in norm_log)

    def known(term):
        return _key(term) in llm_known

    unlinked = [t for t in unlinked
                if not any(x.get("linked") and _key(x["expr"]) == _key(t) for x in norm_log)]  # LLM 풀이 속 사전 말로 이미 이은 것

    # 잇기 2 뒤로 미룬 것 (P-080): 표준 용어와 자모 하나 차이인 말
    still = []
    for term in unlinked:
        if no_info or confident(term) or known(term):
            still.append(term)
            continue
        entry, typo = link_term(term, query, d)
        if entry and not any(_key(x["expr"]) == _key(entry["expr"]) and x.get("method") == "사전" for x in norm_log):
            gone = {_key(term), _key(entry["expr"])}
            norm_log = [x for x in norm_log if _key(x["expr"]) not in gone]
            unresolved = [u for u in unresolved if _key(u["expr"]) not in gone]
            norm_log.append(entry)
            add_typo(typo)
            if "2 사전 잇기" not in steps:
                steps.append("2 사전 잇기")
        else:
            still.append(term)
    unlinked = still

    # 후보로만 묻기 (P-072·P-093): 자모 하나 차이인데 후보가 둘이거나, 글자마다 자모 하나까지 다른 사전 말이 있으면 되묻기에 후보
    asked_before = {c["expr"] for c in one_cand} if last.get("clarified") else set()
    handled = set()
    for term in unlinked:
        k = _key(term)
        if no_info or known(term) or term in asked_before:
            continue
        hits = {}
        for w, tgt in near_words(k, d) + near_words(k, d, loose=True):
            hits.setdefault(w, tgt)
        if confident(term):  # LLM이 아는 말로 푼 경우에는 은어·종목 약어 후보만 ("고가"를 "호가"로 묻지 않는다)
            hits = {w: t for w, t in hits.items() if t[1] != "표준 용어"}
        if len(hits) in (1, 2):
            words = list(hits)
            norm_log = [x for x in norm_log if not (x.get("method") == "LLM" and _key(x["expr"]) == k)]
            unresolved = [u for u in unresolved if _key(u["expr"]) != k]
            item = {"expr": term, "reason": "사전 말의 오타로 보임", "candidate": words[0]}
            if len(words) == 2:
                item["candidates"] = words
            unresolved.append(item)
            handled.add(k)

    # P-092: 짐작만 한 표현은 되묻는다. 설정 D에서 조회 뒤에 왔으면 못 찾은 용어와 겹치는 것만 (묻지 않은 표현은 버린다)
    def ask(expr):
        if not any(_key(u["expr"]) == _key(expr) for u in unresolved) and not has(expr):
            unresolved.append({"expr": expr, "reason": "뜻이 확인되지 않은 표현"})

    gk = {_key(g) for g in guessed}
    if missing:
        for term in unlinked:
            k = _key(term)
            if k not in handled and any(k in g or g in k for g in gk):
                # P-097: LLM이 적은 표현이 용어를 품고 있고 질문에 그대로 있으면 긴 쪽으로 묻는다 ("랠리" → "솜사탕 랠리")
                longer = next((g for g in guessed if k in _key(g) and _key(g) != k and g in query), None)
                ask(longer or term)
    elif not (last.get("clarified") and any(x.get("user_defined") for x in norm_log)):
        for g in guessed:
            ask(g)

    return {
        "annotated_query": render_annotation(query, norm_log),
        "norm_log": norm_log,
        "unresolved": unresolved,
        "clarify_kind": "",
        "typo_confirm": typo_confirm,
        "errors": errors,
        "usage": state["usage"] + [usage],
        "path": state["path"] + steps + ["2 LLM 정규화"],
    }
