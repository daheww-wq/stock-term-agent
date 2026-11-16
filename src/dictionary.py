"""정규화 사전 불러오기와 노드 1(사전 정규화)의 매칭 규칙.

규칙 (설계도 노드 1)
- 원문을 바꾸지 않고 풀이를 덧붙인다
- 처리 순서: 오타 → 종목 약어 → 관용구 패턴 → 용어
- 관용구는 핵심 단어 사이에 다른 말이 끼어도 잡는다 (총알 졸라 장전 → 총알 장전). 사이 글자 수는 관용구마다 상한을 둔다
- 긴 표현부터 매칭한다 (슈퍼개미를 개미보다 먼저)
- 활용형은 매칭용 변형 칸으로 잡는다 (물렸, 물려 …)
- 문장 안에 표준 용어·종목 정식 이름이 그대로 있으면 그 구간은 매칭하지 않는다 (펀더멘털 안의 펀더)
- 오탐 예외 표현은 매칭하지 않는다 (숏폼, 물려받다 …)
- 오타는 확정하지 않는다: 되묻기=아니요 → typo_confirm, 되묻기=예 → unresolved
- 되묻기=예 오타라도 같은 문장에 원래 말이 있으면 되묻지 않는다 (P-073, "빛투는 빚투 말한 거야")
- 사전 은어는 문장 속 뜻과 상관없이 다 푼다. 비유·다른 뜻으로 쓰인 은어를 답에 쓸지는 노드 5가 정한다 (P-081, P-074의 비유 예외를 뺌)
- 자모 비교(P-069·P-072, 노드 2에서 씀): 사전 말(은어 원형·종목 약어·표준 용어)과 자모가 가까운 말을 찾는다.
  자모 비교에서 빼는 일상어·실제 은어는 near_exceptions.csv
"""
import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import ROOT

DICT_DIR = ROOT / "data" / "dictionary"


def _read(name: str) -> list[dict]:
    with open(DICT_DIR / name, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def _split(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def _key(term: str) -> str:
    """조회용 키: 띄어쓰기와 대소문자 차이는 같은 용어로 본다 (갭상승 = 갭 상승, per = PER)."""
    return "".join(term.split()).lower()


@dataclass
class Dictionary:
    standard: dict = field(default_factory=dict)        # 표준용어 → 행
    standard_by_key: dict = field(default_factory=dict) # 조회 키 → 표준용어
    surfaces: list = field(default_factory=list)        # (매칭 표면형, 비표준 원형, 표준용어)
    nonstandard_map: dict = field(default_factory=dict) # 비표준 원형 → 표준용어
    tickers: dict = field(default_factory=dict)         # 약어 → 종목명
    typos: list = field(default_factory=list)           # (오타, 원표현, 되묻기 bool)
    exceptions: list = field(default_factory=list)      # 오탐 예외 표현
    idioms: list = field(default_factory=list)          # (관용구, 정규식, 표준용어, 민감 여부, 설명, 뜻)
    near_targets: dict = field(default_factory=dict)    # 자모 비교 대상 사전 말(띄어쓰기 없음) → (표준용어 또는 종목명, 종류)
    near_exceptions: set = field(default_factory=set)   # 자모 비교에서 빼는 말 (P-069)

    def lookup(self, term: str):
        """표준 용어 사전 조회. 이름이 정확히 같아야 찾는다 (띄어쓰기·대소문자만 무시)."""
        name = self.standard_by_key.get(_key(term))
        return self.standard.get(name) if name else None


@lru_cache(maxsize=1)
def load_dictionary() -> Dictionary:
    d = Dictionary()
    for r in _read("standard_terms.csv"):
        d.standard[r["표준용어"]] = r
        d.standard_by_key[_key(r["표준용어"])] = r["표준용어"]

    problems = []
    for r in _read("nonstandard.csv"):
        base, std = r["비표준표현"].strip(), r["표준용어"].strip()
        if std not in d.standard:
            problems.append(f"nonstandard.csv {r['id']} '{base}'의 표준용어 '{std}'가 standard_terms.csv에 없음")
        d.nonstandard_map[base] = std
        for s in [base] + _split(r.get("매칭용변형", "")):
            d.surfaces.append((s, base, std))

    for r in _read("tickers.csv"):
        d.tickers[r["약어"].strip()] = r["종목명"].strip()

    for r in _read("typos.csv"):
        orig = r["원표현"].strip()
        if orig not in d.nonstandard_map and orig not in d.tickers:
            problems.append(f"typos.csv {r['id']} 원표현 '{orig}'이 비표준 표현·종목 약어에 없음")
        d.typos.append((r["오타"].strip(), orig, r["되묻기"].strip() == "예"))

    for r in _read("false_positives.csv"):
        d.exceptions += _split(r["예외표현"])

    # 관용구 패턴 (사전 v0.4). 핵심 단어를 순서대로, 단어 안의 "/"는 "또는", 사이 글자 수 상한
    if (DICT_DIR / "idioms.csv").exists():
        for r in _read("idioms.csv"):
            base, std = r["관용구"].strip(), r["표준용어"].strip()
            if std not in d.standard:
                problems.append(f"idioms.csv {r['id']} '{base}'의 표준용어 '{std}'가 standard_terms.csv에 없음")
            gap = int(r.get("사이최대글자") or 6)
            parts = []
            for word in _split(r["핵심단어"]):
                alts = [re.escape(a.strip()) for a in word.split("/") if a.strip()]
                parts.append("(" + "|".join(alts) + ")")
            # 사이에는 문장 부호·줄바꿈이 없는 글자만 허용 (다른 문장의 단어를 잇지 않게)
            pattern = re.compile(f"[^.?!\n]{{0,{gap}}}?".join(parts))
            sensitive = (r.get("민감") or "").strip() == "예"
            meaning = (r.get("뜻") or "").strip() or base   # 관용구 자체의 뜻 (없으면 관용구 이름)
            d.idioms.append((base, pattern, std, sensitive, (r.get("설명") or "").strip(), meaning))

    if problems:
        raise ValueError("사전 데이터 확인 필요:\n- " + "\n- ".join(problems))

    # 자모 비교 대상 (P-069): 표준 용어 → 은어 원형 → 종목 약어 순서로 넣는다 (같은 말이면 뒤의 것)
    for name in d.standard:
        d.near_targets[_key(name)] = (name, "표준 용어")
    for base, std in d.nonstandard_map.items():
        d.near_targets[_key(base)] = (std, "용어")
    for abbr, name in d.tickers.items():
        d.near_targets[_key(abbr)] = (name, "종목 약어")
    if (DICT_DIR / "near_exceptions.csv").exists():
        d.near_exceptions = {_key(r["표현"]) for r in _read("near_exceptions.csv") if (r.get("표현") or "").strip()}

    # 긴 표현 우선
    d.surfaces.sort(key=lambda x: -len(x[0]))
    d.typos.sort(key=lambda x: -len(x[0]))
    return d


# ---------------------------------------------------------------------------
# 노드 1 매칭
# ---------------------------------------------------------------------------

def _occurrences(text: str, needle: str):
    start = 0
    while needle:
        i = text.find(needle, start)
        if i < 0:
            return
        yield i, i + len(needle)
        start = i + 1


def _free(mask: list, s: int, e: int) -> bool:
    return not any(mask[s:e])


def _mark(mask: list, s: int, e: int) -> None:
    for i in range(s, e):
        mask[i] = True


def _jamo(ch: str):
    o = ord(ch) - 0xAC00
    return (o // 588, (o % 588) // 28, o % 28) if 0 <= o < 11172 else None


def jamo_gaps(a: str, b: str):
    """글자 수가 같은 두 말의 글자별 자모(초성·중성·종성) 차이 수. 글자 수가 다르거나 한글이 아닌 글자가 다르면 None"""
    if len(a) != len(b):
        return None
    out = []
    for x, y in zip(a, b):
        if x == y:
            out.append(0)
            continue
        jx, jy = _jamo(x), _jamo(y)
        if jx is None or jy is None:
            return None
        out.append(sum(p != q for p, q in zip(jx, jy)))
    return out


def near_words(term: str, d: Dictionary | None = None, loose: bool = False) -> list:
    """사전 말 가운데 term과 자모가 가까운 것 [(사전 말, (표준용어 또는 종목명, 종류))].

    loose=False (P-069 잇기 2): 모두 합쳐 자모 하나만 다름. loose=True (P-072 후보로만 묻기): 글자마다 자모 하나까지, 모두 합쳐 둘.
    두 글자 미만, 사전에 그대로 있는 말, 예외 목록(near_exceptions.csv)에 있는 말은 비교하지 않는다.
    """
    d = d or load_dictionary()
    t = _key(term)
    if len(t) < 2 or t in d.near_exceptions or t in d.near_targets:
        return []
    hits = []
    for w, tgt in d.near_targets.items():
        if len(w) < 2:
            continue
        g = jamo_gaps(t, w)
        if not g:
            continue
        s = sum(g)
        if (not loose and s == 1) or (loose and s == 2 and max(g) <= 1):
            hits.append((w, tgt))
    return hits


@dataclass
class NormResult:
    norm_log: list
    typo_confirm: list
    unresolved: list


def dict_normalize(text: str, d: Dictionary | None = None) -> NormResult:
    d = d or load_dictionary()
    raw = text

    # 1) 원문에서 오탐 예외 구간을 막는다 (오타도 이 안에서는 찾지 않음)
    raw_block = [False] * len(raw)
    for ex in d.exceptions:
        for s, e in _occurrences(raw, ex):
            _mark(raw_block, s, e)

    # 2) 오타: 원문 위에서 찾고, 고친 문장(work)을 따로 만든다. 원문은 바꾸지 않는다
    corrections = []  # (raw_s, raw_e, typo, original)
    ask_spans = []    # 되묻기=예 오타 구간 (raw)
    unresolved = []
    log = []
    taken = [False] * len(raw)
    for typo, orig, ask in d.typos:
        for s, e in _occurrences(raw, typo):
            if not _free(raw_block, s, e) or not _free(taken, s, e):
                continue
            _mark(taken, s, e)
            if ask and orig in raw:
                continue  # P-073: 원래 말이 같은 문장에 있으면 사용자가 이미 밝힌 것 → 되묻지 않고 원래 말을 용어로 잡는다
            if ask:
                ask_spans.append((s, e))
                if not any(u["expr"] == typo for u in unresolved):
                    unresolved.append({"expr": typo, "reason": "다른 말로도 읽힐 수 있는 오타",
                                       "candidate": orig})
                    log.append({"pos": s, "expr": typo, "standard": "", "type": "오타",
                                "method": "사전", "via": orig, "status": "되묻기",
                                "annotation": ""})
            else:
                corrections.append((s, e, typo, orig))

    # work 문장과 위치 대응표 (work 위치 → 원문 시작·끝)
    work, w2r_s, w2r_e = [], [], []
    corrections.sort()
    i = 0
    for s, e, typo, orig in corrections + [(len(raw), len(raw), "", "")]:
        while i < s:
            work.append(raw[i]); w2r_s.append(i); w2r_e.append(i + 1); i += 1
        for ch in orig:
            work.append(ch); w2r_s.append(s); w2r_e.append(e)
        i = max(i, e)
    work = "".join(work)

    def raw_surface(ws, we):
        return raw[w2r_s[ws]: w2r_e[we - 1]]

    def typo_in(ws, we):
        rs, re_ = w2r_s[ws], w2r_e[we - 1]
        return [c for c in corrections if c[0] < re_ and c[1] > rs]

    # 3) work 문장에서 막을 구간: 오탐 예외, 표준 용어, 종목 정식 이름, 되묻기 오타
    block = [False] * len(work)
    protect = list(d.exceptions) + list(d.standard.keys()) + list(d.tickers.values())
    for p in protect:
        for s, e in _occurrences(work, p):
            _mark(block, s, e)
    for wi in range(len(work)):
        if any(s <= w2r_s[wi] < e for s, e in ask_spans):
            block[wi] = True

    used = [False] * len(work)
    typo_confirm = []

    def add(ws, we, entry):
        _mark(used, ws, we)
        hit = typo_in(ws, we)
        surface = raw_surface(ws, we)
        entry.update({"pos": w2r_s[ws], "expr": surface, "method": "사전"})
        if hit:
            corrected = work[ws:we]
            entry["via"] = corrected
            entry["type"] = "오타"
            entry["annotation"] = f"{surface}={corrected}(오타로 보임)={entry['standard']}"
            for _, _, typo, orig in hit:
                if not any(t["typo"] == typo for t in typo_confirm):
                    typo_confirm.append({"typo": typo, "original": orig})
        if not any(x["expr"] == surface and x.get("status") != "되묻기" for x in log):
            log.append(entry)

    # 4) 종목 약어
    for abbr in sorted(d.tickers, key=len, reverse=True):
        for s, e in _occurrences(work, abbr):
            if _free(block, s, e) and _free(used, s, e):
                name = d.tickers[abbr]
                add(s, e, {"standard": name, "type": "종목 약어",
                           "annotation": f"{raw_surface(s, e)}={name}"})

    # 5) 관용구 패턴 (용어보다 먼저: "총알 장전"이 "총알"보다 긴 표현)
    # 관용구 경계를 가로지르는 더 긴 슬랭이 있으면 관용구로 보지 않는다 (슈퍼개미 털렸대 ≠ 개미 털리다)
    term_spans = [(ts, te) for surface, _, _ in d.surfaces for ts, te in _occurrences(work, surface)
                  if _free(block, ts, te)]

    def crosses(s, e):
        return any((ts < s < te) or (ts < e < te) for ts, te in term_spans)

    for base, pattern, std, sensitive, desc, meaning in d.idioms:
        for m in pattern.finditer(work):
            s, e = m.span()
            parts_free = all(_free(block, m.start(i), m.end(i)) for i in range(1, (m.lastindex or 0) + 1))
            if parts_free and _free(used, s, e) and not crosses(s, e):
                shown = raw_surface(s, e)
                # 풀이 형식: 원문=관용구 뜻=표준 용어 (뜻이 표준 용어와 같으면 원문=표준 용어)
                mid = meaning if meaning != std else ""
                ann = f"{shown}={mid}={std}" if mid else f"{shown}={std}"
                entry = {"standard": std, "type": "관용구", "base": base, "meaning": meaning, "annotation": ann}
                if sensitive:
                    entry.update({"sensitive": True, "note": desc.split(".")[0]})
                add(s, e, entry)

    # 6) 용어 (긴 표현 우선, 활용형 포함)
    for surface, base, std in d.surfaces:
        for s, e in _occurrences(work, surface):
            if _free(block, s, e) and _free(used, s, e):
                shown = raw_surface(s, e)
                ann = f"{shown}={base}={std}" if surface != base else f"{shown}={std}"
                add(s, e, {"standard": std, "type": "용어", "base": base, "annotation": ann})

    log.sort(key=lambda x: x["pos"])
    return NormResult(norm_log=log, typo_confirm=typo_confirm, unresolved=unresolved)


def render_annotation(query: str, norm_log: list) -> str:
    """원문 + [풀이: …] 형태로 만든다. 풀이가 없으면 원문 그대로."""
    parts = [x["annotation"] for x in sorted(norm_log, key=lambda x: x.get("pos", 9999))
             if x.get("annotation")]
    return f"{query} [풀이: {', '.join(parts)}]" if parts else query


def has_sensitive_expression(text: str) -> bool:
    """민감 표현(관용구 사전의 민감=예)이 문장에 있는지. 실험 설정(A/B/C)과 상관없이 쓴다 (P-023 상담 안내)."""
    d = load_dictionary()
    return any(sensitive and pattern.search(text) for _, pattern, _, sensitive, _, _ in d.idioms)

