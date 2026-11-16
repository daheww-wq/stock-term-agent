"""그래프 모양을 mermaid 글로 뽑는다 (LLM 호출 없음, 키 없어도 됨).

실행: python scripts/draw_graph.py  → docs_graph.mermaid 생성
README나 포트폴리오에 붙이거나 https://mermaid.live 에 붙여 넣어 그림으로 볼 수 있다.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph import build_graph  # noqa: E402

text = build_graph().get_graph().draw_mermaid()
out = ROOT / "docs_graph.mermaid"
out.write_text(text, encoding="utf-8")
print(text)
print(f"\n저장: {out.name}")
