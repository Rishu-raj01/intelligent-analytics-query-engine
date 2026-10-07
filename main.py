from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analytics_engine.config import get_settings
from analytics_engine.engine import AnalyticsQueryEngine


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Intelligent Analytics Query Engine")
    p.add_argument("--dataset", default="dataset", help="Path to dataset directory")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Run one natural-language query")
    group.add_argument(
        "--all", action="store_true", help="Run every query from nl_queries.json"
    )
    p.add_argument("--output", help="Optional JSON output file")
    return p


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings(args.dataset)

    try:
        engine = AnalyticsQueryEngine(settings)
        if args.query:
            payload = engine.answer(args.query).to_dict()
        else:
            payload = [engine.answer_safe(q).to_dict() for q in engine.bundle.nl_queries]

        rendered = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        print(rendered)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
