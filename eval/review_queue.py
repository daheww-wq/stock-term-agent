"""측정 검토 대기열 (P-030). 측정 결과에서 사람이 볼 trace를 골라 랭퓨즈 대기열 하나에 넣는다.

쓰는 곳
- eval/run_dev.py --set test --dataset-run <이름>: 측정이 끝나면 자동으로 "<이름> 측정 검토" 대기열을 만든다
- scripts/langfuse_setup.py: 이미 끝난 측정 결과 엑셀로 같은 대기열을 만든다 (1차처럼 이 기능 전에 돌린 측정)

대기열에 넣는 것 = 꼭 확인 + 훑어보기
- 꼭 확인: 아래 규칙 중 하나라도 걸린 trace. 이유를 trace 코멘트("[검토_필요] …")로 남긴다
  · 의도 불일치(의도_일치 0) · 재구성 글자 다름(재구성_일치 0) · LLM 채점 0점(사전밖_* 중 0)
  · 오류·출력 상한(오류 칸) · 용어 보정 작동(용어_보정 칸, P-027) · 직접 지정(MANUAL_FLAGS)
- 훑어보기: 꼭 확인에 걸리지 않았지만 LLM이 채점한 사전 밖 답변 (사람이 LLM 채점을 맞춰 보는 대상)
- 모든 대상에 점수 "검토_필요"(꼭 확인 / 훑어보기)를 남긴다 → Traces 목록·Dataset 화면에서 점수로 거를 수 있다

순서
- 랭퓨즈 대기열은 넣은 순서대로 보여주고 "Complete + next"도 그 순서로 넘어간다. 대기열 안에서 거르거나 정렬하는 기능은 없다
- 그래서 꼭 확인을 먼저 넣는다 (규칙 순서 → 문항 순서 → 설정 A·B·C). 같은 문항의 A·B·C가 붙어 나와 비교하기 쉽다
- 그 뒤에 훑어보기를 문항 순서 → 설정 순서로 넣는다

여러 번 실행해도 이미 넣은 trace·코멘트는 다시 넣지 않고, 점수는 같은 id로 덮어쓴다.
"""
import uuid

FLAG_SCORE = "검토_필요"
FLAG_MUST, FLAG_SKIM = "꼭 확인", "훑어보기"
COMMENT_PREFIX = "[검토_필요]"
KEY_PREFIX = "[정답지]"  # P-033: 검토 화면에서 정답지와 에이전트 결과를 나란히 보게
JUDGE_COLS = ("사전밖_뜻일치", "사전밖_틀린사실없음", "사전밖_표시", "사전밖_눈높이")
GROUPS = ["의도 불일치", "재구성 글자 다름", "LLM 채점 0점", "오류·출력 상한", "용어 보정 작동", "직접 지정"]

# 검토_원인 고르는 법과 예시 (P-032). 점수 항목 설명과 대기열 설명에 같이 넣는다
CAUSE_GUIDE = (
    "틀렸을 때 path 순서대로 따라가 처음으로 결과가 틀린 노드 하나를 고른다. 앞에서 틀리면 뒤는 따라 틀리므로 첫 번째만. "
    "맞았으면 문제 없음. 어떻게 됐어야 하는지는 코멘트 한 줄로. "
    "선택지: 0 재구성(앞 대화를 잘못 채움) · 1·4 사전(사전에 없거나 잘못 풀림) · 2 LLM 풀이(추정 풀이가 틀림, 되물어야 했는데 안 물음) · "
    "3 의도(라벨을 잘못 고름) · 3 용어 추출(terms를 잘못 뽑음) · 5 답변(근거는 맞는데 답이 틀리거나 단정·잘림) · "
    "6 검수(위반을 놓치거나 과하게 막음) · 정답지(라벨·정답이 틀렸고 에이전트가 맞음) · "
    "설정 한계(A·B라서 당연히 못 푸는 것) · 문제 없음(맞음, 채점만 엄격했음). "
    "예시: S41-A 하소연 속 몰빵을 범위 밖으로 보냄 → 3 의도 / "
    "S05-B 사전 풀이 '평가손실 상태가 되다'를 terms에서 '평가손실'로 줄여 조회 실패 → 3 용어 추출 / "
    "M12-1-A 도롱뇽장 뜻을 지어냄, A에는 되묻기 단계가 없음 → 설정 한계 / "
    "M5-2-A 재구성이 글자만 다르고 뜻은 같음 → 문제 없음(검토_재구성 예) / "
    "S25-B 답변이 출력 상한에 걸려 잘림 → 5 답변"
)

# 사람이 볼 점수 항목 (P-029). 대기열 검토 화면에 이 항목들이 나온다
SCORE_CONFIGS = [
    dict(name="검토_의도", data_type="CATEGORICAL",
         categories=[("정답지가 맞음", 1), ("에이전트가 맞음", 2), ("둘 다 틀림", 0)],
         description="의도 정답지(코멘트 [정답지]의 '의도 정답')와 에이전트가 고른 의도 중 맞는 쪽. "
                     "정답지가 맞음 → 에이전트 수정 / 에이전트가 맞음 → 정답지 수정 / 둘 다 틀림 → 코멘트에 맞는 라벨"),
    dict(name="검토_재구성", data_type="BOOLEAN", description="재구성 결과가 정답과 뜻이 같은가 (글자가 달라도)"),
    dict(name="검토_사전밖_뜻", data_type="BOOLEAN", description="사전 밖 용어 설명이 핵심 뜻과 맞는가 (LLM 채점과 비교). 뜻을 짐작하지 않고 되물은 답, 추정이라고 밝히고 확인을 구한 답은 비워 둔다 (P-051·P-054). 추정이라고 해 놓고 사실처럼 설명한 답은 아니오 (P-055)"),
    dict(name="검토_사전밖_틀린사실없음", data_type="BOOLEAN", description="사전 밖 용어 설명에 틀린 사실이 없는가 (LLM 채점과 비교)"),
    dict(name="검토_답변품질", data_type="CATEGORICAL",
         categories=[("좋음", 2), ("보통", 1), ("나쁨", 0)], description="말투·길이·눈높이를 포함한 답변 품질"),
    # P-032: 틀린 곳을 노드 단위로 남겨 원인별로 묶으면 바로 수정 방향이 된다
    dict(name="검토_원인", data_type="CATEGORICAL",
         categories=[("문제 없음", 0), ("설정 한계", 1), ("정답지", 2), ("0 재구성", 3), ("1·4 사전", 4),
                     ("2 LLM 풀이", 5), ("3 의도", 6), ("3 용어 추출", 7), ("5 답변", 8), ("6 검수", 9)],
         description=CAUSE_GUIDE),
]

# 자동 규칙으로 잡히지 않아 직접 지정한 것 {실행 이름: {"문항-설정": 이유}}
# 1차는 용어 보정(P-027) 전에 돌려 용어_보정 칸이 없다. 노드 3이 용어를 줄여 사전을 못 찾은 답변 (LLM 채점은 1점)
MANUAL_FLAGS = {
    "1차": {
        "S05-B": "노드 3이 용어를 줄여 사전 조회를 못 함 (P-027 대상, LLM 채점 1점)",
        "S27-B": "노드 3이 용어를 줄여 사전 조회를 못 함 (P-027 대상, LLM 채점 1점)",
        "S27-C": "노드 3이 용어를 줄여 사전 조회를 못 함 (P-027 대상, LLM 채점 1점)",
        "S06-C": "노드 3이 용어를 줄여 사전 조회를 못 함 (P-027 대상, LLM 채점 1점)",
    },
}


def item_key(row: dict) -> str:
    return row.get("id") or f"{row.get('시나리오')}-{row.get('턴')}"


def _zero(v) -> bool:
    return v is not None and str(v).strip() in ("0", "0.0")


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def flag_reasons(row: dict, manual: str = "") -> list:
    """꼭 확인 이유 [(규칙, 설명)]. 비어 있으면 꼭 확인이 아니다."""
    out = []
    if _zero(row.get("의도_일치")):
        memo = f" ({_txt(row.get('의도_채점메모'))})" if _txt(row.get("의도_채점메모")) else ""
        out.append(("의도 불일치", f"정답 {_txt(row.get('의도_정답'))} · 결과 {_txt(row.get('의도_결과'))}{memo}"))
    if _zero(row.get("재구성_일치")):
        out.append(("재구성 글자 다름", f"정답 「{_txt(row.get('재구성_정답'))}」 · 결과 「{_txt(row.get('재구성_결과'))}」"))
    zeros = [c.replace("사전밖_", "") for c in JUDGE_COLS if _zero(row.get(c))]
    if zeros:
        memo = f" — {_txt(row.get('사전밖_채점메모'))}" if _txt(row.get("사전밖_채점메모")) else ""
        out.append(("LLM 채점 0점", f"{', '.join(zeros)}{memo}"))
    if _txt(row.get("오류")):
        out.append(("오류·출력 상한", _txt(row.get("오류"))))
    if _txt(row.get("용어_보정")):
        out.append(("용어 보정 작동", _txt(row.get("용어_보정"))))
    if manual:
        out.append(("직접 지정", f"{manual} · terms {_txt(row.get('terms'))}"))
    return out


def _load_refs() -> dict:
    """사전 밖 평가용 정답 (측정용). 읽지 못하면 빈 dict"""
    try:
        from run_dev import load_references  # eval/run_dev.py
        return load_references()
    except Exception:
        return {}


def answer_key(row: dict, label: str, refs: dict) -> str:
    """[정답지] 코멘트: 정답지와 에이전트 결과를 나란히 (P-033). 빈 칸은 뺀다."""
    def line(name, value):
        return f"- {name}: {value}" if _txt(value) else None

    intent = _txt(row.get("의도_정답"))
    if _txt(row.get("범위밖_사유_정답")):
        intent += f"({_txt(row.get('범위밖_사유_정답'))})"
    ref_lines = []
    if refs:
        try:
            from run_dev import references_for
            terms = [t.strip() for t in _txt(row.get("사전_근거_없음")).split("·") if t.strip()]
            ref_lines = [f"{k}: {v}" for k, v in (references_for(terms, refs) or {}).items()]
        except Exception:
            ref_lines = []
    got_intent = _txt(row.get("의도_결과"))
    if _txt(row.get("범위밖_사유_결과")):
        got_intent += f"({_txt(row.get('범위밖_사유_결과'))})"
    if _txt(row.get("분류_근거")):
        got_intent += f" — {_txt(row.get('분류_근거'))}"
    lines = [f"{KEY_PREFIX} {label}",
             line("의도 정답", intent),
             line("허용 의도", row.get("허용_의도")),
             line("재구성 정답", row.get("재구성_정답")),
             line("풀이 정답", row.get("풀이_정답")),
             line("사전 밖 평가용 정답", " / ".join(ref_lines)),
             line("기대 행동", row.get("기대_행동")),
             line("확인 포인트", row.get("확인_포인트")),
             "[에이전트 결과]",
             line("의도", got_intent),
             line("재구성", row.get("재구성_결과")),
             line("풀이", row.get("풀이_결과")),
             line("되묻기 대상", row.get("되묻기_대상")),
             line("terms", row.get("terms")),
             line("조회 적중", row.get("조회_적중")),
             line("사전 근거 없음", row.get("사전_근거_없음")),
             line("검수", row.get("검수_판정")),
             line("경로", row.get("경로"))]
    return "\n".join(x for x in lines if x)[:2900]


def judged(row: dict) -> bool:
    return any(_txt(row.get(c)) for c in JUDGE_COLS)


def plan(results: dict, run_name: str = "") -> list:
    """results = {설정: (단발 행, 멀티턴 행)} → 대기열에 넣을 순서대로
    [{trace_id, label, must, reasons, comment}]"""
    manual = MANUAL_FLAGS.get(run_name, {})
    refs = _load_refs()
    modes = sorted(results)
    order = {}
    for mode in modes:
        s_rows, m_rows = results[mode]
        for r in list(s_rows) + list(m_rows):
            order.setdefault(item_key(r), len(order))
    must, skim = [], []
    for mode in modes:
        s_rows, m_rows = results[mode]
        for r in list(s_rows) + list(m_rows):
            tid = _txt(r.get("trace_id"))
            if not tid:
                continue
            key = item_key(r)
            label = f"{key}-{mode}"
            reasons = flag_reasons(r, manual.get(label, ""))
            rec = {"trace_id": tid, "label": label, "must": bool(reasons), "reasons": reasons,
                   "key": answer_key(r, label, refs),
                   "_sort": (min((GROUPS.index(g) for g, _ in reasons), default=99), order[key], mode)}
            if reasons:
                rec["comment"] = (f"{COMMENT_PREFIX} {label}\n" + "\n".join(f"- {g}: {t}" for g, t in reasons))[:2500]
                must.append(rec)
            elif judged(r):
                skim.append(rec)
    must.sort(key=lambda x: x["_sort"])
    skim.sort(key=lambda x: x["_sort"][1:])
    return must + skim


def _all_pages(fn, *args, **kwargs):
    out, page = [], 1
    while True:
        res = fn(*args, page=page, limit=100, **kwargs)
        out.extend(res.data)
        if len(res.data) < 100:
            return out
        page += 1


def ensure_score_configs(api) -> list:
    """SCORE_CONFIGS가 없으면 만들고 id 목록을 돌려준다."""
    from langfuse.api import ConfigCategory, ScoreConfigDataType
    existing = {c.name: c for c in _all_pages(api.score_configs.get)}
    ids = []
    for sc in SCORE_CONFIGS:
        if sc["name"] in existing:
            cur = existing[sc["name"]]
            ids.append(cur.id)
            want = [(l, float(v)) for l, v in sc.get("categories") or []]
            have = [(c.label, float(c.value)) for c in (getattr(cur, "categories", None) or [])]
            if (want and want != have) or (getattr(cur, "description", None) or "") != sc["description"]:
                try:  # 값(1·2·0)은 그대로 두고 이름·설명만 바꾼다 (P-033)
                    kw = {"description": sc["description"]}
                    if want:
                        kw["categories"] = [ConfigCategory(label=l, value=v) for l, v in sc["categories"]]
                    api.score_configs.update(cur.id, **kw)
                    print(f"점수 항목 고침: {sc['name']}")
                except Exception as e:
                    print(f"(점수 항목 {sc['name']}을 고치지 못함: {type(e).__name__}. 랭퓨즈 Settings → Scores에서 확인해 주세요)")
            continue
        kwargs = dict(name=sc["name"], data_type=ScoreConfigDataType(sc["data_type"]), description=sc["description"])
        if sc.get("categories"):
            kwargs["categories"] = [ConfigCategory(label=l, value=v) for l, v in sc["categories"]]
        ids.append(api.score_configs.create(**kwargs).id)
        print(f"점수 항목 만듦: {sc['name']}")
    return ids


def queue_name(run_name: str) -> str:
    return f"{run_name} 측정 검토"


def build(lf, run_name: str, items: list, source: str = "") -> dict:
    """랭퓨즈에 대기열·점수·코멘트를 쓴다. lf = langfuse 클라이언트(get_client())."""
    from langfuse.api import AnnotationQueueObjectType
    api = lf.api
    config_ids = ensure_score_configs(api)
    name = queue_name(run_name)
    queues = {q.name: q for q in _all_pages(api.annotation_queues.list_queues)}
    n_must = sum(1 for x in items if x["must"])
    desc = (f"{source} · 앞 {n_must}개 꼭 확인(코멘트에 이유), 뒤 {len(items) - n_must}개 훑어보기. "
            f"점수 {FLAG_SCORE}로 Traces·Datasets 화면에서 거를 수 있음. "
            "한 건마다 ① 맞음/틀림을 검토_* 항목으로 ② 틀렸으면 검토_원인에 처음 틀린 노드 ③ 어떻게 됐어야 하는지 코멘트 한 줄. "
            "예: S41-A → 검토_의도 '정답지가 맞음', 검토_원인 '3 의도', 코멘트 '하소연이어도 몰빵 설명했어야 함'")
    q = queues.get(name)
    if q is None:
        q = api.annotation_queues.create_queue(name=name, description=desc, score_config_ids=config_ids)
    else:
        missing = [sc["name"] for sc, cid in zip(SCORE_CONFIGS, config_ids) if cid not in (getattr(q, "score_config_ids", None) or [])]
        if missing:  # 이미 만든 대기열에는 API로 점수 항목을 더할 수 없다
            print(f"(대기열 '{name}'에 없는 점수 항목: {', '.join(missing)}. 랭퓨즈 화면 Annotation Queues → {name} → "
                  "대기열 수정(Edit) → Score Configs에서 추가해 주세요)")
    have = {x.object_id for x in _all_pages(api.annotation_queues.list_queue_items, q.id)}
    project_id = api.projects.get().data[0].id
    added = commented = 0
    for x in items:  # 순서가 곧 검토 순서라 한 개씩 차례로 넣는다
        if x["trace_id"] not in have:
            api.annotation_queues.create_queue_item(q.id, object_id=x["trace_id"], object_type=AnnotationQueueObjectType.TRACE)
            have.add(x["trace_id"])
            added += 1
        lf.create_score(trace_id=x["trace_id"], name=FLAG_SCORE, value=FLAG_MUST if x["must"] else FLAG_SKIM,
                        data_type="CATEGORICAL", score_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/{x['trace_id']}")),
                        comment=" / ".join(g for g, _ in x["reasons"]) or None)
        old = None
        for prefix, text in ((KEY_PREFIX, x.get("key")), (COMMENT_PREFIX, x.get("comment"))):
            if not text:
                continue
            if old is None:
                old = api.comments.get(object_type="TRACE", object_id=x["trace_id"], limit=100).data
            if not any((c.content or "").startswith(prefix) for c in old):
                api.comments.create(project_id=project_id, object_type="TRACE", object_id=x["trace_id"], content=text)
                commented += 1
    lf.flush()
    return {"queue": name, "items": len(items), "must": n_must, "added": added, "commented": commented}


def print_plan(items: list):
    n_must = sum(1 for x in items if x["must"])
    print(f"검토 대기열: 꼭 확인 {n_must}개 → 훑어보기 {len(items) - n_must}개 (모두 {len(items)}개)")
    for g in GROUPS:
        labels = [x["label"] for x in items if x["must"] and x["reasons"][0][0] == g]
        if labels:
            print(f"  - {g} {len(labels)}: {', '.join(labels)}")
