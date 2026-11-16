"""규칙 분류 (P-062, 3차 최적화 ②): 뜻만 묻는 단순 질문은 노드 3 LLM을 부르지 않는다.

"○○가 뭐야?", "○○ 무슨 뜻이야?"처럼 문장이 "표현 + 뜻을 묻는 끝말"뿐이고, 그 표현이
- 사전 표준 용어 이름이거나 (PER이 뭐야?)
- 노드 1 사전 풀이로 표준 용어에 닿는 말이면 (개미털기가 뭐예요? → 주가 흔들기)
의도는 "용어 설명", 용어는 그 표준 용어로 정한다. 노드 3 LLM이 같은 질문에 내던 결과와 같다.

잡지 않는 것 (노드 3으로 보낸다)
- 표현이 사전에 닿지 않는 말 (코인 스테이킹이 뭐야? 는 범위 밖일 수 있고, 배당락이 뭐예요? 는 사전 밖 설명이라 LLM 판단이 필요)
- LLM 풀이((추정)·(짐작)·(사용자 설명))만 있는 말, 종목 약어, 오타 확인·되묻기 대상, 민감 표현
- 용어가 둘 이상인 문장 ("손절이랑 익절 차이가 뭐야?"), 뜻 묻는 끝말 앞에 다른 말이 더 있는 문장
매매 판단 안전망(P-044)과 같은 방식의 규칙이고, 과잉 차단은 개발용 과잉 차단 점검과 범위 밖 문항으로 잰다.
설정 A(정규화 없음)에는 쓰지 않는다 (기준선 유지). 켜고 끄기는 config.FAST_PATH (--fast-path).
"""
import re

from .dictionary import _key, load_dictionary

# 뜻을 묻는 끝말. 앞의 표현에 조사(이/가/은/는/이란/란)나 "~라는 게/말이/건"이 붙을 수 있다
_TAIL = (r"(?:이|가|은|는|이란|란|이라는\s*(?:게|말이|건|거)|라는\s*(?:게|말이|건|거)|의\s*뜻이|\s*뜻이|\s*뜻은|\s*뜻)?\s*"
         r"(?:뭐야|뭐예요|뭐에요|뭔가요|뭐죠|무슨\s*뜻이야|무슨\s*뜻이에요|무슨\s*뜻인가요|무슨\s*뜻|무슨\s*말이야|무슨\s*말이에요|"
         r"무슨\s*의미야|무슨\s*의미예요|뭘\s*말하는\s*거야|무엇인가요|뭔지\s*알려줘|뜻\s*알려줘|뜻이\s*뭐야|뜻이\s*뭐예요|"
         r"무슨\s*뜻인지\s*알려줘|설명해\s*줘|설명해줘)\s*$")
_HEAD = r"^(?:주식에서|주식\s*용어\s*중에|주식\s*용어|주식\s*할\s*때|근데|그런데|혹시|저기|아|음)?\s*"
_PATTERN = re.compile(_HEAD + r"(?P<expr>[가-힣A-Za-z0-9·\s]{1,20}?)" + _TAIL)
_MULTI = re.compile(r"(이랑|랑|하고|과\s|와\s|,|/|차이|비교)")


def simple_term_question(question: str, norm_log: list, typo_confirm: list, unresolved: list) -> str | None:
    """뜻만 묻는 단순 질문이고 표현이 사전에 닿으면 그 표준 용어를, 아니면 None"""
    q = (question or "").strip().rstrip("?!. ").strip()
    if not q or typo_confirm or unresolved:
        return None
    if _MULTI.search(q):
        return None
    m = _PATTERN.match(q)
    if not m:
        return None
    expr = m.group("expr").strip()
    if not expr:
        return None
    d = load_dictionary()
    # 노드 1 사전 풀이: 표현이 그 풀이의 expr와 글자까지 같을 때만 (풀이 구간 밖에 다른 말이 있으면 단순 질문이 아님)
    for x in norm_log or []:
        if _key(x.get("expr", "")) != _key(expr):
            continue
        if x.get("sensitive") or x.get("type") == "종목 약어" or x.get("method") != "사전" or x.get("status") == "되묻기":
            return None
        std = x.get("standard") or ""
        return std if d.lookup(std) else None
    # 풀이가 없으면 표현 자체가 표준 용어일 때만
    row = d.lookup(expr)
    if row and not any(_key(x.get("expr", "")) in _key(expr) or _key(expr) in _key(x.get("expr", "")) for x in norm_log or []):
        return row["표준용어"]
    return None
