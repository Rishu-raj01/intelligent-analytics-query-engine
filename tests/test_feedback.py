from pathlib import Path

import pandas as pd

from analytics_engine.feedback import FeedbackStore


def test_retrieves_relevant_feedback_without_embeddings(tmp_path: Path):
    path = tmp_path / "feedback_log.csv"
    pd.DataFrame(
        [
            {
                "query": "Top products by revenue in each region",
                "correct_sql": "SELECT ...",
                "feedback": "Partition ranking by region",
                "is_correct": True,
            },
            {
                "query": "Monthly target variance",
                "correct_sql": "SELECT ...",
                "feedback": "Join on month and region",
                "is_correct": True,
            },
        ]
    ).to_csv(path, index=False)

    store = FeedbackStore(path, enable_embeddings=False)
    examples = store.relevant_examples("Show top 3 products for every region", limit=1)

    assert len(examples) == 1
    assert "products" in examples[0].query.lower()
    assert examples[0].retrieval_method == "lexical"
    assert examples[0].score > 0.3
