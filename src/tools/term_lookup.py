"""노드 4가 부르는 tool: 표준 용어 사전 조회.

- 표준 용어 이름과 정확히 같아야 찾는다 (띄어쓰기·대소문자 차이만 무시)
- 비표준 표현(떡상 등)으로는 찾지 않는다. 슬랭을 표준 용어로 바꾸는 건 정규화(노드 1·2)의 몫이고,
  여기서 대신 풀어주면 실험 설정 A(정규화 없음)에서도 사전이 쓰이게 되어 RQ2 ②(조회 적중)를 잴 수 없다
- 사전에 없는 용어는 found=False("없음")로 넘긴다
"""
from langchain_core.tools import tool

from ..dictionary import load_dictionary


def lookup_terms(terms: list[str]) -> list[dict]:
    d = load_dictionary()
    out = []
    for t in terms:
        row = d.lookup(t)
        if row:
            out.append({"term": t, "found": True, "standard": row["표준용어"],
                        "description": row["설명"]})
        else:
            out.append({"term": t, "found": False, "standard": "", "description": "없음"})
    return out


@tool
def term_lookup(terms: list[str]) -> list[dict]:
    """표준 용어 사전에서 용어 설명(100자 이내)을 찾는다. 없으면 '없음'으로 표시한다."""
    return lookup_terms(terms)


def related_terms(term_info: list[dict], max_n: int | None = None) -> list[str]:
    """P-022 관련 용어 안내 후보: 설명한 용어의 사전 설명 안에 나오는 다른 표준 용어.

    - 사전에 있는 용어만 후보가 된다 (다음 답변도 사전 근거로 할 수 있게). LLM이 고르지 않는다
    - 이미 설명한 용어, 너무 기본인 용어(config.RELATED_EXCLUDE)는 빼고, 최대 config.RELATED_MAX개
    - 긴 이름부터 찾는다 (시가총액 안의 시가를 따로 잡지 않게)
    """
    from .. import config
    max_n = config.RELATED_MAX if max_n is None else max_n
    d = load_dictionary()
    asked = {t["standard"] for t in term_info if t["found"]}
    names = sorted(d.standard, key=len, reverse=True)
    out = []
    for t in term_info:
        if not t["found"]:
            continue
        desc = t["description"]
        used = [False] * len(desc)
        for name in names:
            if name in asked or name in config.RELATED_EXCLUDE:
                continue
            i = desc.find(name)
            while i >= 0:
                if not any(used[i:i + len(name)]):
                    for k in range(i, i + len(name)):
                        used[k] = True
                    if name not in out:
                        out.append(name)
                i = desc.find(name, i + 1)
    return out[:max_n]

