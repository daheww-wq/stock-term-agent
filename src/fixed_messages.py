"""고정 문구 (노드 7·8·9). LLM을 거치지 않고, 컴플라이언스 검수도 하지 않는다.

이름 메모 (2026.11.16): OUT_OF_SCOPE의 '힘든 마음'은 기획서·README의 '자살·자해 위험 표현', '맞장구'는 '설명 뒤 짧은 수긍'이다.
  키 이름은 노드 3의 범위 밖 사유(out_reason)와 같아야 해서 바꾸지 않는다 (src/nodes/n3_intent.py의 이름 메모).

문구를 바꾸면 설계도 3번(노드별 세부 기준)도 같이 고친다.
"""

# 노드 7 안전 답변: 검수에서 재생성 2회 후에도 걸렸을 때
# (설계도에 문구가 정해져 있지 않아 Claude 초안. 본인 확인 필요)
SAFE_ANSWER = (
    "이 질문에는 안전하게 답변을 만들지 못했어요. "
    "사거나 파는 판단은 해드릴 수 없지만, 궁금한 주식 용어를 물어봐 주시면 뜻을 설명해드릴게요."
)

# 노드 7 안내 덧붙임 (P-068): 재생성 2회 뒤에도 남은 위반이 판단 불가 안내 누락(R1)뿐이면
# 안전 답변으로 답을 버리지 않고, 답 앞에 이 문장을 붙이고 끝맺음 문장이 없으면 끝에 붙인다
TRADING_NOTICE = "사거나 파는 건 판단해드릴 수 없어요."
TRADING_CLOSING = "결정 전에 충분히 알아보시는 걸 권해요."

# 노드 8 범위 밖 안내 (설계도 노드 8)
OUT_OF_SCOPE = {
    # P-071: 입구가 매매 질문을 범위 밖으로 보내도 판단 불가 안내가 나가게 문구에 넣었다 (4차 개발용 전망 질문 2/3 누락)
    "일반": "이 서비스는 주식 용어 설명을 도와드려요. 말씀하신 내용은 다루지 않고, 사거나 파는 판단이나 시장 전망도 해드릴 수 없어요.",
    "불법·유해": "법에 어긋날 수 있는 내용이라 안내해드릴 수 없어요. 주식 용어가 궁금하시면 편하게 물어봐 주세요.",
    # P-075: 마음이 크게 힘들다는 말. LLM을 거치지 않는 고정 문구 (Claude 초안, 11.12 본인 확정)
    # P-097: 설명으로 끝난 턴 다음의 맞장구("맞아요", "네"). LLM을 거치지 않는 고정 문구 (11.12 본인 결정)
    "맞장구": "네, 더 궁금한 주식 용어가 있으면 물어봐 주세요.",
    "힘든 마음": "많이 힘드셨겠어요. 혼자 견디지 마시고 주변 사람이나 자살예방 상담전화(109)에 지금 이야기해 보세요.",
}

# 노드 9 되묻기 (설계도 노드 9). ○○ 자리에 표현이 들어간다. 조사는 표현의 받침에 맞춘다 (P-059)
# P-092: 짐작 갈래를 없애면서 되묻기 문장을 하나로 맞췄다. "확인되지 않은 단어예요"는 11.12 본인 결정 (사전이 작아서 "사전에 없다"보다 이 말이 맞음)
CLARIFY = "'{expr}'{josa} 확인되지 않은 단어예요. 어떤 뜻으로 들으셨는지 알려주시면 이어서 설명해드릴게요."
# 후보가 있을 때 (P-072): 고치지 않고 후보를 보여 주며 묻는다. 화면에서는 "맞아요 / 아니에요" 빠른 답과 함께
CLARIFY_CANDIDATE = "'{expr}'{josa} 확인되지 않은 단어예요. 혹시 '{cand}'{josa2} 말씀하신 건가요? 아니라면 어떤 뜻으로 들으셨는지 알려주세요."
# 후보가 둘일 때 (P-093): 둘 다 보여 주며 묻는다 ("쏜절" → 손절, 본절)
CLARIFY_CANDIDATE2 = "'{expr}'{josa} 확인되지 않은 단어예요. 혹시 '{c1}'{josa1} '{c2}'{josa2} 말씀하신 건가요? 아니라면 어떤 뜻으로 들으셨는지 알려주세요."
# 되묻기 뒤 짧은 대답 (P-092)
#   "맞아요"(확인할 후보가 없음) · "다른 뜻이에요" → 다시 묻는다
CLARIFY_AGAIN = "어떤 뜻으로 들으셨는지 알려주시면 이어서 설명해드릴게요."
#   "몰라요" → 확인된 뜻이 없다고 말하고 끝낸다
DONT_KNOW = "'{expr}'{josa} 저도 확인된 뜻을 찾지 못했어요. 증권사 안내나 공식 자료에서 확인해 보세요."

# 사전 밖 안내 첫 문장 (P-094): LLM이 쓰지 않고 코드가 사용자가 쓴 말 그대로 붙인다
UNGROUNDED_NOTICE = "'{expr}'{josa} 사전에 등록되지 않은 용어라 일반적인 설명으로 안내해요."
UNGROUNDED_NOTICE_NONE = "사전에 등록되지 않은 내용이라 일반적인 설명으로 안내해요."
UNGROUNDED_CLOSING = "정확한 내용은 증권사 안내나 공식 자료에서 한 번 더 확인해 보세요."
# 노드 5가 뜻을 모를 때 내는 표시 (P-092). 코드가 되묻기 문장으로 바꾼다
UNKNOWN_MARK = "[모름]"

# 하소연 (P-070): 노드 5가 공감 한 문장을 쓰고, 그 뒤에 이 문장과 용어 제안을 붙인다
COMFORT_TAIL = "이 서비스는 주식 용어 설명을 도와드려요."
COMFORT_OFFER = "'{expr}' 뜻이 궁금하시면 물어봐 주세요."
COMFORT_OFFER_NONE = "궁금한 주식 용어가 있으면 물어봐 주세요."
COMFORT_FALLBACK = "많이 속상하셨겠어요."


def josa_eun_neun(word: str) -> str:
    """마지막 글자 받침에 따라 은/는. 한글이 아니면(영문·숫자 등) '는'"""
    w = (word or "").strip()
    if not w:
        return "는"
    ch = w[-1]
    if "가" <= ch <= "힣":
        return "은" if (ord(ch) - 0xAC00) % 28 else "는"
    return "는"


def josa_eul_reul(word: str) -> str:
    w = (word or "").strip()
    if w and "가" <= w[-1] <= "힣":
        return "을" if (ord(w[-1]) - 0xAC00) % 28 else "를"
    return "를"


def josa_ina_na(word: str) -> str:
    w = (word or "").strip()
    if w and "가" <= w[-1] <= "힣":
        return "이나" if (ord(w[-1]) - 0xAC00) % 28 else "나"
    return "나"


def clarify_message(exprs: list, candidate: str = "", candidates: list | None = None) -> str:
    """되묻기 문구. 표현이 여럿이면 'a', 'b'로 잇고 조사는 마지막 표현에 맞춘다.
    표현이 하나이고 사전 말 후보가 있으면 후보를 보여 주며 묻는다 (P-072). 후보가 둘이면 둘 다 (P-093)"""
    exprs = [e for e in exprs if e]
    cands = [c for c in (candidates or ([candidate] if candidate else [])) if c]
    if len(cands) == 2 and len(exprs) == 1:
        return CLARIFY_CANDIDATE2.format(expr=exprs[0], josa=josa_eun_neun(exprs[0]), c1=cands[0], josa1=josa_ina_na(cands[0]),
                                         c2=cands[1], josa2=josa_eul_reul(cands[1]))
    if len(cands) == 1 and len(exprs) == 1:
        return CLARIFY_CANDIDATE.format(expr=exprs[0], josa=josa_eun_neun(exprs[0]), cand=cands[0],
                                        josa2=josa_eul_reul(cands[0]))
    return CLARIFY.format(expr="', '".join(exprs), josa=josa_eun_neun(exprs[-1] if exprs else ""))


def dont_know_message(exprs: list) -> str:
    exprs = [e for e in exprs if e]
    return DONT_KNOW.format(expr="', '".join(exprs), josa=josa_eun_neun(exprs[-1] if exprs else ""))


def ungrounded_notice(exprs: list) -> str:
    """사전 밖 안내 첫 문장. 사용자가 쓴 말이 없으면(질문에 용어가 없음) 말 없이 안내한다"""
    exprs = list(dict.fromkeys(e for e in exprs if e))
    if not exprs:
        return UNGROUNDED_NOTICE_NONE
    return UNGROUNDED_NOTICE.format(expr="', '".join(exprs), josa=josa_eun_neun(exprs[-1]))

# 민감 표현(관용구 사전 민감=예, 예: 한강 물 온도 체크) 질문에 붙이는 걱정 한 문장 (P-023, 본인 확정)
# 농담인지 진심인지 판단하기 어려워 항상 짧게 한 번 붙인다. 실험 설정과 상관없이, 모든 경로(답변·범위 밖·되묻기·안전 답변)에 붙는다
CARE_MESSAGE = "혹시 정말 마음이 많이 힘드시다면 혼자 두지 말고 주변이나 자살예방 상담전화(109)에 이야기해 보세요."

