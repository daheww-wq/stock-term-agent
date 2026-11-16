"""터미널에서 에이전트와 직접 대화해 보기 (멀티턴).

실행 (stock-term-agent 폴더에서)
  python scripts/chat.py              # 설정 C, 랭퓨즈 켜짐
  python scripts/chat.py --mode B
  python scripts/chat.py --no-langfuse

대화 중 명령
  /new   새 대화 시작 (대화 기억 비움)
  /exit  끝내기
"""
import argparse
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.runner import flush, run_turn  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="C", choices=list(config.MODES))
    ap.add_argument("--model")
    ap.add_argument("--no-langfuse", action="store_true")
    args = ap.parse_args()

    config.set_model(args.model)
    config.set_tracing(not args.no_langfuse)
    graph = build_graph()
    thread_id = str(uuid.uuid4())
    session = f"chat-{thread_id[:8]}"
    print(f"설정 {args.mode}({config.MODES[args.mode]}) · 모델 {config.current_model()} · /new 새 대화, /exit 끝")

    try:
        while True:
            q = input("\n나> ").strip()
            if not q:
                continue
            if q == "/exit":
                break
            if q == "/new":
                thread_id = str(uuid.uuid4())
                session = f"chat-{thread_id[:8]}"
                print("(새 대화)")
                continue
            try:
                state, _ = run_turn(graph, q, mode=args.mode, thread_id=thread_id,
                                    tags=["대화 테스트"], session_id=session)
            except Exception as e:
                print(f"[오류] {type(e).__name__}: {e}")
                continue
            print(f"\n에이전트> {state['final_answer']}")
            print(f"  · 재구성: {state['rewritten_query']}")
            print(f"  · 풀이: {state['annotated_query']}")
            print(f"  · 의도: {state['intent']} {state['out_reason']} / 용어 {state['terms']} / 종목 {state['ticker'] or '-'}")
            print(f"  · 경로: {' → '.join(state['path'])} ({state['_latency_sec']}초{', 호출 간격 대기 ' + str(state['_wait_sec']) + '초' if state.get('_wait_sec') else ''})")
    finally:
        flush()


if __name__ == "__main__":
    main()
