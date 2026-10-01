"""Offline Spark aggregations for email analytics batch jobs."""
import os
import sys
from typing import TypedDict

from sqlalchemy import select
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from app.db.session import AsyncSessionLocal
from app.models import category, entity, reply, user  # noqa: F401
from app.models.analysis import EmailAnalysis
from app.models.email import Email


REQUIRED_COLUMNS = (
    "email_id",
    "received_at",
    "category",
    "priority_score",
    "priority_level",
    "sentiment",
    "action_required",
    "intent",
)


class EmailBatchAggregations(TypedDict):
    daily_email_volume: DataFrame
    category_distribution: DataFrame
    priority_distribution: DataFrame
    average_priority_by_category: DataFrame
    sentiment_distribution: DataFrame
    action_required_count: DataFrame


def create_spark_session(
    app_name: str = "AVEN Email Batch Analytics",
    master: str = "local[*]",
) -> SparkSession:
    """Create or reuse a Spark session for offline batch processing."""
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    return (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.ui.enabled", "false")
        .config("spark.python.worker.reuse", "false")
        .getOrCreate()
    )


async def load_analyzed_email_records() -> list[dict[str, object]]:
    """Load email and analysis fields for offline batch processing."""
    statement = (
        select(
            Email.id.label("email_id"),
            Email.received_at.label("received_at"),
            EmailAnalysis.category_name.label("category"),
            EmailAnalysis.priority_score.label("priority_score"),
            EmailAnalysis.priority_level.label("priority_level"),
            EmailAnalysis.sentiment.label("sentiment"),
            EmailAnalysis.action_required.label("action_required"),
            EmailAnalysis.intent.label("intent"),
        )
        .join(EmailAnalysis, EmailAnalysis.email_id == Email.id)
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings()]


def _clean_email_records(emails: DataFrame) -> DataFrame:
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(emails.columns))
    if missing_columns:
        raise ValueError(f"Email DataFrame is missing columns: {', '.join(missing_columns)}")

    cleaned = emails.withColumn(
        "received_at", F.try_to_timestamp(F.col("received_at"))
    )
    cleaned = cleaned.withColumn(
        "priority_score", F.col("priority_score").cast("double")
    ).withColumn(
        "priority_level", F.lower(F.trim(F.col("priority_level").cast("string")))
    ).withColumn(
        "sentiment", F.lower(F.trim(F.col("sentiment").cast("string")))
    ).withColumn(
        "action_required", F.col("action_required").cast("boolean")
    )

    non_empty_columns = ("email_id", "category", "priority_level", "sentiment", "intent")
    valid = F.col("received_at").isNotNull()
    for column in REQUIRED_COLUMNS:
        valid = valid & F.col(column).isNotNull()
    for column in non_empty_columns:
        valid = valid & (F.length(F.trim(F.col(column).cast("string"))) > 0)

    valid = (
        valid
        & (~F.isnan("priority_score"))
        & F.col("priority_score").between(0, 100)
        & F.col("priority_level").isin("low", "medium", "high")
        & F.col("sentiment").isin("positive", "neutral", "negative")
    )
    return (
        cleaned.filter(valid)
        .withColumn("email_id", F.trim(F.col("email_id").cast("string")))
        .withColumn("category", F.trim(F.col("category").cast("string")))
        .withColumn("intent", F.trim(F.col("intent").cast("string")))
        .withColumn("received_date", F.to_date("received_at"))
    )


def aggregate_email_batch(emails: DataFrame) -> EmailBatchAggregations:
    """Clean an email DataFrame and produce offline analytics aggregations."""
    cleaned = _clean_email_records(emails)
    return {
        "daily_email_volume": cleaned.groupBy("received_date").agg(
            F.count("email_id").alias("email_count")
        ),
        "category_distribution": cleaned.groupBy("category").agg(
            F.count("email_id").alias("email_count")
        ),
        "priority_distribution": cleaned.groupBy("priority_level").agg(
            F.count("email_id").alias("email_count")
        ),
        "average_priority_by_category": cleaned.groupBy("category").agg(
            F.avg("priority_score").alias("average_priority_score")
        ),
        "sentiment_distribution": cleaned.groupBy("sentiment").agg(
            F.count("email_id").alias("email_count")
        ),
        "action_required_count": cleaned.agg(
            F.coalesce(
                F.sum(F.when(F.col("action_required"), 1).otherwise(0)), F.lit(0)
            ).alias("action_required_count")
        ),
    }