"""설정: .env 읽기, 모델 이름, 노드별 생각하는 양, LLM 클라이언트.

바꿀 일이 많은 값은 이 파일 위쪽에 모아 두었다.
"""
import os
import pathlib

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# 예전 이름(LANGFUSE_HOST)만 읽는 버전에서도 동작하도록 같이 채워 둔다
if os.getenv("LANGFUSE_BASE_URL") and not os.getenv("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# 에이전트 모델. 실행 중 --model 옵션으로 바꿀 수 있다 (set_model)
AGENT_MODEL = os.getenv("AGENT_MODEL", "google/gemini-3.8-flash")
# 채점용 모델 (eval에서 LLM 채점을 붙일 때 사용). 10.15부터 기본 gpt-6-sol (P-064: sonnet과 판정이 같고 약 40% 쌈). .env 값이 비어 있어도 기본값
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or "openai/gpt-6-sol"

# 검수 실패 시 재생성 최대 횟수 (설계도: 최대 2회)
MAX_RETRY = 2
# 대화 기억 범위 (설계도: 최근 3턴)
HISTORY_TURNS = 3

# 노드별 생각하는 양 (OpenRouter reasoning 설정)
# RQ1에서 Gemini가 짧은 답에도 출력 토큰이 많았다 → 단순한 노드(재구성·LLM 정규화·분류)는 줄인다
# None이면 모델 기본값. .env에 LIGHT_REASONING=off 를 넣으면 전부 기본값으로 돌린다
NODE_REASONING = {
    "n0_rewrite": {"effort": "low"},
    "n2_llm_normalize": {"effort": "low"},
    "n3_intent": {"effort": "low"},
    # P-015: 말투 규칙이 늘면서 답변 생성이 문항당 최대 2.6만 토큰·160초를 생각에 썼다 → 생각에 쓸 토큰 상한
    "n5_answer": {"max_tokens": 1024},
    # P-028: 출력 상한(2,500)에 걸려 답이 잘렸을 때 한 번 다시 쓰는 호출. 생각을 더 줄인다
    "n5_answer_retry": {"max_tokens": 256},
    "n6_compliance": None,  # 안전 판정이라 모델 기본값 유지
}

# 노드별 출력 토큰 상한 (생각 토큰이 포함될 수 있어 넉넉히). 상한에 걸리면 usage의 finish_reason이 length
NODE_MAX_TOKENS = {
    "n5_answer": 2500,
    "n5_answer_retry": 2500,
    "judge_unknown_term": 1500,
}
if os.getenv("LIGHT_REASONING", "on").lower() == "off":
    NODE_REASONING = {k: None for k in NODE_REASONING}

# 호출 간격 조절 (P-025): OpenRouter 새 계정은 분당 20회 한도가 있다.
# 한도에 닿기 전에 호출 사이를 벌려 둔다. 테스트·대화 모두 적용. 0이면 끈다 (계정 한도가 오르면 .env에서 조정)
CALLS_PER_MINUTE = float(os.getenv("CALLS_PER_MINUTE") or 18)

# 관련 용어 안내 (P-022): 설명한 용어의 사전 설명 안에 다른 표준 용어가 나오면 다음 질문으로 이어지게 안내
RELATED_MAX = 1                                   # 한 답변에 최대 몇 개 (억지로 넣지 않게 1개)
RELATED_EXCLUDE = {"매수", "매도", "개인투자자"}   # 너무 기본이라 안내하지 않는 용어

# 실험 설정 (설계도 6번)
MODES = {
    "A": "정규화 없음",
    "B": "사전만",
    "C": "사전+LLM",
    "D": "사전 우선+필요 시 LLM",  # P-042: B처럼 가다가 사전 조회가 실패할 때만 노드 2
}

# 되묻기(노드 9)까지 갈 수 있는 설정 (노드 2가 있는 설정)
ASK_MODES = ("C", "D")

# 노드별 모델 (P-061, 3차 최적화 ①): 비어 있으면 모든 노드가 current_model()을 쓴다.
# {"n0_rewrite": "openai/gpt-6-luna", ...}. n5_answer_retry는 n5_answer를 따른다. 채점(judge)은 JUDGE_MODEL로 따로
NODE_MODELS: dict = {}
NODE_NAMES = ("n0_rewrite", "n2_llm_normalize", "n3_intent", "n5_answer", "n6_compliance")

# 규칙 분류 (P-062, 3차 최적화 ②): "○○가 뭐야?"처럼 뜻만 묻고 ○○가 사전 표준 용어(또는 사전 풀이로 표준 용어에 닿는 말)이면
# 노드 3 LLM을 부르지 않고 규칙으로 용어 설명 + 용어를 정한다. 기본 꺼짐 (지금 D와 개선 D를 같은 코드에서 나누기 위해)
FAST_PATH = False

_state = {"model": AGENT_MODEL, "tracing": None, "client": None}


def set_node_models(spec) -> dict:
    """노드별 모델 지정 (P-061). spec은 dict 또는 "n0,n2,n3,n5=openai/gpt-6-luna;n6=google/gemini-3.8-flash" 꼴 문자열.
    노드는 전체 이름이나 앞부분(n0·n2·n3·n5·n6)으로 적는다. 빈 값이면 모두 해제"""
    NODE_MODELS.clear()
    if not spec:
        return NODE_MODELS
    if isinstance(spec, dict):
        NODE_MODELS.update({k: v for k, v in spec.items() if v})
        return NODE_MODELS
    for part in str(spec).split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        nodes, model = part.rsplit("=", 1)
        model = model.strip()
        for n in nodes.split(","):
            n = n.strip()
            if not n:
                continue
            hits = [full for full in NODE_NAMES if full == n or full.startswith(n + "_")] if n != "*" else list(NODE_NAMES)
            if not hits:
                raise ValueError(f"노드 이름을 모름: {n} (가능: {', '.join(NODE_NAMES)})")
            for full in hits:
                NODE_MODELS[full] = model
    return NODE_MODELS


def model_for(node: str) -> str:
    """이 노드가 쓸 모델. n5_answer_retry는 n5_answer를 따른다"""
    base = "n5_answer" if node == "n5_answer_retry" else node
    return NODE_MODELS.get(base) or _state["model"]


def node_models_label() -> str:
    """결과 요약용: "n0·n2·n3·n5 openai/gpt-6-luna" (지정이 없으면 빈 문자열)"""
    if not NODE_MODELS:
        return ""
    by_model: dict = {}
    for n in NODE_NAMES:
        if n in NODE_MODELS:
            by_model.setdefault(NODE_MODELS[n], []).append(n.split("_")[0])
    return " / ".join(f"{'·'.join(ns)} {m}" for m, ns in by_model.items())


def set_fast_path(on: bool) -> None:
    global FAST_PATH
    FAST_PATH = bool(on)


def langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def set_tracing(on: bool) -> None:
    """랭퓨즈 기록을 켜고 끈다. 끄면 LLM 호출도 일반 openai 클라이언트로 한다."""
    _state["tracing"] = bool(on) and langfuse_configured()
    _state["client"] = None


def tracing_on() -> bool:
    if _state["tracing"] is None:
        set_tracing(True)
    return _state["tracing"]


def set_model(model: str | None) -> None:
    if model:
        _state["model"] = model


def current_model() -> str:
    return _state["model"]


def get_client():
    """OpenRouter용 OpenAI 클라이언트.

    랭퓨즈를 켜면 langfuse.openai의 OpenAI를 쓴다. 노드 안에서 부른 LLM 호출이
    랭퓨즈 trace의 해당 노드 아래에 generation으로 붙고, OpenRouter가 알려주는 비용도 같이 기록된다.
    """
    if _state["client"] is not None:
        return _state["client"]
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit(".env에 OPENROUTER_API_KEY를 채워주세요.")
    if tracing_on():
        from langfuse.openai import OpenAI
    else:
        from openai import OpenAI
    _state["client"] = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key, timeout=90)
    return _state["client"]
