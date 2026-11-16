"""노드 4 용어 사전 조회 (tool).

노드 3이 뽑은 terms를 표준 용어 사전에서 찾는다. 없는 용어는 "없음"으로 넘긴다.
용어 설명이면 관련 용어 안내 후보(사전 설명 안의 다른 표준 용어)도 함께 찾는다 (P-022).
사전에 없는 용어가 짐작·사용자 설명 풀이의 원래 표현이고, 그 풀이의 뜻이 사전 표준 용어와 글자까지 같을 때만
그 표준 용어를 "가까운 표준 용어"로 함께 조회한다 (P-056). 글자가 다르면 찾지 않는다 (노드 5가 사전 근거 없이 △△를 대지 않게).
"""
from ..dictionary import _key, dict_normalize, load_dictionary
from ..state import AgentState
from ..tools.term_lookup import lookup_terms, related_terms, term_lookup


def near_standard_terms(term_info: list, norm_log: list) -> list:
    """P-056: 사전에 없는 용어 ← 짐작·사용자 설명 풀이 ← 뜻이 사전 표준 용어 이름과 같을 때만"""
    out = []
    for t in term_info:
        if t.get("found"):
            continue
        for x in norm_log or []:
            if x.get("method") != "LLM" or not x.get("guess"):  # 사용자 설명은 user_words_terms가 맡는다 (P-088)
                continue
            if _key(x.get("expr", "")) != _key(t["term"]):
                continue
            hit = lookup_terms([x.get("standard", "")])[0]
            if hit["found"] and not any(n["standard"] == hit["standard"] for n in out):
                out.append({"term": t["term"], "standard": hit["standard"], "description": hit["description"]})
    return out


def user_words_terms(term_info: list, norm_log: list) -> list:
    """P-088: 사전에 없는 용어 ← 사용자 설명 ← 그 설명 안에 든 사전 말(표준 용어 이름, 은어)만 찾는다.

    용어의 뜻을 표준 용어로 바꿔 말하려는 것이 아니라, 사용자가 쓴 말 가운데 사전으로 설명할 수 있는 부분을 찾는 것이다.
    """
    d = load_dictionary()
    out = []
    for t in term_info:
        if t.get("found"):
            continue
        for x in norm_log or []:
            if not x.get("user_defined") or _key(x.get("expr", "")) != _key(t["term"]):
                continue
            said = x.get("standard", "")
            hits = []  # (사용자가 쓴 말, 표준 용어)
            for name in sorted(d.standard, key=len, reverse=True):
                if len(_key(name)) >= 2 and _key(name) in _key(said) and not any(_key(name) in _key(h[1]) for h in hits):
                    hits.append((name, name))
            for y in dict_normalize(said, d).norm_log:
                if y.get("standard") and y.get("type") != "종목 약어" and not y.get("sensitive") and y.get("status") != "되묻기":
                    if not any(h[1] == y["standard"] for h in hits):
                        hits.append((y.get("base") or y["expr"], y["standard"]))
            for part, std in hits[:2]:
                hit = lookup_terms([std])[0]
                if hit["found"] and not any(n["standard"] == hit["standard"] for n in out):
                    out.append({"term": t["term"], "part": part, "standard": hit["standard"], "description": hit["description"]})
    return out


def lookup_node(state: AgentState) -> dict:
    info = term_lookup.invoke({"terms": state["terms"]})
    # 관련 용어 안내(P-022)는 용어 설명이고, 설명할 용어가 모두 사전에 있을 때만 (사전 밖 답변은 조심스럽게 끝내야 해서 제외)
    related = []
    sensitive = any(x.get("sensitive") for x in state.get("norm_log") or [])
    if state["intent"] == "용어 설명" and info and all(t["found"] for t in info) and not sensitive:
        related = related_terms(info)
    near = near_standard_terms(info, state.get("norm_log") or [])
    said = user_words_terms(info, state.get("norm_log") or [])
    return {"term_info": info, "related_terms": related, "near_terms": near, "user_words_terms": said,
            "path": state["path"] + ["4 용어 조회"]}
