"""Run the offline Spark analytics demo with an in-memory email dataset.

Run: python -m scripts.run_pyspark_analytics [--output-dir PATH] (from backend/)
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.analytics.pyspark_batch import (
    aggregate_email_batch,
    create_spark_session,
    load_analyzed_email_records,
    write_email_batch_parquet,
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
    parser = argparse.ArgumentParser(description="Run PySpark email batch analytics.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "analytics",
        help="Directory in which to write the Parquet datasets.",
    )
    args = parser.parse_args()

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

        locations = write_email_batch_parquet(aggregations, args.output_dir)
        print("\nParquet datasets written:")
        for name, location in locations.items():
            print(f"{name}: {location}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
