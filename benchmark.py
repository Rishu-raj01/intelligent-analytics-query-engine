from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from analytics_engine.config import get_settings
from analytics_engine.engine import AnalyticsQueryEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the provided NL-query benchmark.")
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--output", default="benchmark_results.json")
    args = parser.parse_args()

    engine = AnalyticsQueryEngine(get_settings(args.dataset))
    outputs = [engine.answer_safe(q).to_dict() for q in engine.bundle.nl_queries]
    successes = [x for x in outputs if x["result"] is not None]
    confidences = [float(x["confidence_score"]) for x in successes]
    latencies = [
        float(x.get("metadata", {}).get("latency_ms", 0.0))
        for x in successes
        if x.get("metadata", {}).get("latency_ms") is not None
    ]

    summary = {
        "total_queries": len(outputs),
        "successful_queries": len(successes),
        "success_rate": round(len(successes) / len(outputs), 3) if outputs else 0.0,
        "average_confidence": round(statistics.mean(confidences), 3) if confidences else 0.0,
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "repair_count": sum(bool(x.get("metadata", {}).get("repaired")) for x in successes),
    }
    payload = {"summary": summary, "results": outputs}
    Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
