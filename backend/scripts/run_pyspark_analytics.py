"""Run the offline Spark analytics demo with an in-memory email dataset.

Run: python -m scripts.run_pyspark_analytics (from the backend/ directory)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.analytics.pyspark_batch import (
    aggregate_email_batch,
    create_spark_session,
    load_analyzed_email_records,
)


COLUMNS = [
    "email_id",
    "received_at",
    "category",
    "priority_score",
    "priority_level",
    "sentiment",
    "action_required",
    "intent",
]

EMAILS = [
    ("e1", "2025-03-01T10:00:00", "Work", 82.0, "high", "positive", True, "reply"),
    ("e2", "2025-03-01T11:30:00", "Work", 58.0, "medium", "neutral", False, "review"),
    ("e3", "2025-03-02T09:15:00", "Personal", 24.0, "low", "negative", True, "archive"),
]


def main() -> None:
    records = asyncio.run(load_analyzed_email_records())
    if not records:
        print("No analyzed email records found; nothing to aggregate.")
        return

    spark = create_spark_session("AVEN Email Analytics Demo")
    try:
        rows = [tuple(record[column] for column in COLUMNS) for record in records]
        emails = spark.createDataFrame(rows, COLUMNS)
        aggregations = aggregate_email_batch(emails)

        for name, dataframe in aggregations.items():
            print(f"\n{name.replace('_', ' ').title()}")
            dataframe.show(truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
