from datetime import date, datetime
import os
import sys

import pytest
from pyspark.sql import SparkSession

from app.analytics.pyspark_batch import aggregate_email_batch, create_spark_session


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = create_spark_session("AVEN Batch Analytics Tests", "local[1]")
    yield session
    session.stop()


def test_spark_workers_use_active_python(spark: SparkSession):
    assert os.environ["PYSPARK_PYTHON"] == sys.executable
    assert os.environ["PYSPARK_DRIVER_PYTHON"] == sys.executable


def test_aggregates_clean_records_and_drops_invalid_rows(spark: SparkSession):
    rows = [
        ("e1", "2025-03-01T10:00:00", "Work", 80.0, "high", "positive", True, "reply"),
        ("e2", "2025-03-01T11:00:00", "Work", 60.0, "medium", "neutral", False, "review"),
        ("e3", "2025-03-02T09:00:00", "Personal", 20.0, "low", "negative", True, "archive"),
        (None, "2025-03-02T09:00:00", "Work", 50.0, "medium", "neutral", False, "review"),
        ("e4", "not-a-date", "Work", 50.0, "medium", "neutral", False, "review"),
        ("e5", "2025-03-02T09:00:00", "Work", 101.0, "high", "neutral", False, "review"),
        ("e6", "2025-03-02T09:00:00", "Work", 50.0, "urgent", "neutral", False, "review"),
    ]
    columns = [
        "email_id", "received_at", "category", "priority_score", "priority_level",
        "sentiment", "action_required", "intent",
    ]
    result = aggregate_email_batch(spark.createDataFrame(rows, columns))

    daily = {row.received_date: row.email_count for row in result["daily_email_volume"].collect()}
    categories = {row.category: row.email_count for row in result["category_distribution"].collect()}
    priorities = {
        row.priority_level: row.email_count
        for row in result["priority_distribution"].collect()
    }
    average_scores = {
        row.category: row.average_priority_score
        for row in result["average_priority_by_category"].collect()
    }
    sentiments = {
        row.sentiment: row.email_count
        for row in result["sentiment_distribution"].collect()
    }

    assert daily == {date(2025, 3, 1): 2, date(2025, 3, 2): 1}
    assert categories == {"Work": 2, "Personal": 1}
    assert priorities == {"high": 1, "medium": 1, "low": 1}
    assert average_scores == {"Work": 70.0, "Personal": 20.0}
    assert sentiments == {"positive": 1, "neutral": 1, "negative": 1}
    assert result["action_required_count"].first().action_required_count == 2


def test_rejects_missing_required_columns(spark: SparkSession):
    emails = spark.createDataFrame([("e1",)], ["email_id"])

    with pytest.raises(ValueError, match="missing columns"):
        aggregate_email_batch(emails)


def test_aggregates_records_with_datetime_received_at(spark: SparkSession):
    rows = [
        ("e1", datetime(2025, 3, 1, 10, 0), "Work", 80, "high", "positive", True, "reply"),
        ("e2", datetime(2025, 3, 2, 11, 30), "Personal", 40, "medium", "neutral", False, "review"),
    ]
    columns = [
        "email_id", "received_at", "category", "priority_score", "priority_level",
        "sentiment", "action_required", "intent",
    ]

    result = aggregate_email_batch(spark.createDataFrame(rows, columns))
    daily = {
        row.received_date: row.email_count
        for row in result["daily_email_volume"].collect()
    }

    assert daily == {date(2025, 3, 1): 1, date(2025, 3, 2): 1}