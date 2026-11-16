"""LLM 호출 한 곳으로 모으기.

모든 LLM 노드는 call_llm()을 거친다. 여기서
- 모델 이름, temperature 0, 노드별 생각하는 양(reasoning)을 붙이고
- 응답 시간, 토큰, 비용(OpenRouter 제공)을 usage 기록으로 돌려준다
"""
import json
import re
import threading
import time

from . import config

PROMPT_DIR = config.ROOT / "prompts"


def load_prompt(name: str) -> str:
    """prompts/<name>.md 를 읽는다. 지침을 고칠 때는 이 파일들만 고치면 된다."""
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


# 랭퓨즈 Prompts 연결 (P-031)
# 기준은 저장소 prompts/ 파일이다. 랭퓨즈에는 같은 내용을 버전으로 올려 두고(scripts/langfuse_setup.py),
# LLM 호출마다 쓴 지침 버전을 generation에 연결한다. 랭퓨즈 쪽 내용이 파일과 다르거나 랭퓨즈에 닿지 않으면
# 연결만 하지 않고 호출은 그대로 한다 (에이전트 동작은 바뀌지 않음)
LANGFUSE_PROMPT_PREFIX = "stock-term/"
_prompt_links: dict = {}
_prompt_names: dict = {}


def prompt_files() -> dict:
    """{지침 이름: 내용} — prompts/*.md (README 제외)"""
    return {f.stem: f.read_text(encoding="utf-8") for f in sorted(PROMPT_DIR.glob("*.md")) if f.stem != "README"}


def _fetch_prompt(name: str):
    from langfuse import get_client
    return get_client().get_prompt(LANGFUSE_PROMPT_PREFIX + name, label="production", cache_ttl_seconds=300,
                                   max_retries=0, fetch_timeout_seconds=5)


def prompt_link(system: str):
    """system이 prompts/ 파일 하나와 글자까지 같고, 랭퓨즈 production 버전도 같은 내용이면 그 프롬프트를 돌려준다."""
    if not _prompt_names:
        _prompt_names.update({text: name for name, text in prompt_files().items()})
    name = _prompt_names.get(system)
    if not name:
        return None
    if name not in _prompt_links:
        try:
            p = _fetch_prompt(name)
            _prompt_links[name] = p if getattr(p, "prompt", None) == system else None
        except Exception:  # 아직 안 올렸거나 연결 실패 → 이번 실행에서는 연결 없이
            _prompt_links[name] = None
    return _prompt_links[name]


def sync_prompts(lf, note: str = "") -> list:
    """prompts/ 파일을 랭퓨즈 Prompts에 올린다. 내용이 바뀐 것만 새 버전(라벨 production)으로.
    [(이름, "새로 올림" | "새 버전" | "같음")]"""
    out = []
    for name, text in prompt_files().items():
        full = LANGFUSE_PROMPT_PREFIX + name
        try:
            cur = lf.get_prompt(full, label="production", cache_ttl_seconds=0, max_retries=0, fetch_timeout_seconds=10)
        except Exception:
            cur = None
        if cur is not None and cur.prompt == text:
            out.append((name, "같음"))
            continue
        lf.create_prompt(name=full, prompt=text, type="text", labels=["production"],
                         commit_message=note or "저장소 prompts/ 파일")
        out.append((name, "새 버전" if cur is not None else "새로 올림"))
    _prompt_links.clear()
    return out


def call_llm(node: str, system: str, user: str, model: str | None = None) -> tuple[str, dict]:
    """LLM을 한 번 부르고 (답변 텍스트, usage 기록)을 돌려준다.

    model을 주면 그 모델로 부른다 (채점용 모델 등). 없으면 에이전트 모델.
    """
    client = config.get_client()
    model = model or config.model_for(node)  # P-061: 노드별 모델 지정이 있으면 그 모델

    extra_body = {"usage": {"include": True}}  # OpenRouter가 비용을 응답에 넣어주게 함
    reasoning = config.NODE_REASONING.get(node)
    if reasoning:
        extra_body["reasoning"] = reasoning

    kwargs = dict(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        extra_body=extra_body,
    )
    if config.NODE_MAX_TOKENS.get(node):
        kwargs["max_tokens"] = config.NODE_MAX_TOKENS[node]
    if config.tracing_on():
        kwargs["name"] = node  # 랭퓨즈 generation 이름
        linked = prompt_link(system)
        if linked is not None:
            kwargs["langfuse_prompt"] = linked  # 이 호출이 쓴 지침 버전 (P-031)

    # sec에는 순수 호출 시간만 넣고, 간격 조절·한도 초과로 기다린 시간은 wait_sec에 따로 적는다 (P-025)
    wait_sec = _pace()
    t0 = time.time()
    resp, retry_wait = _create_with_wait(client, kwargs, node)
    sec = round(time.time() - t0 - retry_wait, 2)
    wait_sec = round(wait_sec + retry_wait, 2)

    text = (resp.choices[0].message.content or "").strip()
    usage = {"node": node, "model": model, "sec": sec, "wait_sec": wait_sec, "input_tokens": None,
             "output_tokens": None, "cost_usd": None,
             "finish_reason": resp.choices[0].finish_reason}
    if resp.usage is not None:
        usage["input_tokens"] = resp.usage.prompt_tokens
        usage["output_tokens"] = resp.usage.completion_tokens
        cost = getattr(resp.usage, "cost", None)
        if cost is None and getattr(resp.usage, "model_extra", None):
            cost = resp.usage.model_extra.get("cost")
        usage["cost_usd"] = cost
    return text, usage


# OpenRouter 새 계정은 모델별 분당 20회 제한이 있다. 질문 하나에 LLM을 4~5번 부르므로
# 연속 실행하면 걸릴 수 있다. 429(분당 한도 초과)가 오면 기다렸다가 다시 부른다
# P-025부터는 _pace()가 미리 간격을 벌려 한도에 닿지 않게 하고, 이 대기는 만일을 위한 안전장치로 남긴다
RATE_LIMIT_WAITS = [20, 40, 60]

_pace_lock = threading.Lock()
_last_call = {"t": 0.0}


def _pace() -> float:
    """직전 LLM 호출 시작과 최소 (60 / CALLS_PER_MINUTE)초 간격을 둔다. 기다린 초를 돌려준다.

    CALLS_PER_MINUTE가 0이면 기다리지 않는다. 노드·채점 호출 모두 이 함수를 지난다.
    """
    cpm = config.CALLS_PER_MINUTE
    with _pace_lock:
        now = time.monotonic()
        if not cpm or cpm <= 0:
            _last_call["t"] = now
            return 0.0
        wait = max(0.0, _last_call["t"] + 60.0 / cpm - now)
        if wait:
            time.sleep(wait)
        _last_call["t"] = time.monotonic()
        return wait


def _create_with_wait(client, kwargs, node):
    """(응답, 한도 초과로 기다린 초)를 돌려준다."""
    from openai import RateLimitError
    waited = 0.0
    for wait in RATE_LIMIT_WAITS + [None]:
        try:
            return client.chat.completions.create(**kwargs), waited
        except RateLimitError:
            if wait is None:
                raise
            print(f"  (분당 호출 한도 초과 · {node} · {wait}초 기다렸다 다시 시도)")
            time.sleep(wait)
            waited += wait


def parse_json(text: str):
    """모델 답변에서 JSON 객체 하나를 꺼낸다. 못 꺼내면 None.

    ```json 펜스나 앞뒤 설명 문장이 붙어도 첫 번째 { 부터 마지막 } 까지를 읽어본다.
    """
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def format_history(history: list) -> str:
    """대화 기억(최근 3턴)을 지침에 넣을 글로 바꾼다."""
    if not history:
        return "(없음)"
    lines = []
    for i, turn in enumerate(history, 1):
        lines.append(f"[{i}턴] 사용자: {turn['user']}")
        lines.append(f"[{i}턴] 에이전트: {turn['assistant']}")
    return "\n".join(lines)
