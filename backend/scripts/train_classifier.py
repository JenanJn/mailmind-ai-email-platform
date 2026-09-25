"""Train and evaluate the email category classifier.

Usage: python -m scripts.train_classifier (from backend/)
"""
import html
import json
import logging
import pickle
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import LinearSVC

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data" / "training_data.json"
PUBLIC_DATA_PATH = Path(__file__).parent.parent / "data" / "public_multiclass_email.json"
MODEL_PATH = Path(__file__).parent.parent / "app" / "ml" / "models" / "email_classifier.pkl"
REPORT_PATH = Path(__file__).parent.parent / "data" / "training_report.json"

PUBLIC_LABEL_MAP = {
    "Business": "Work / Professional",
    "Customer Support": "Customer Support",
    "Events & Invitations": "Events / Invitations",
    "Finance & Bills": "Finance / Banking",
    "Job Application": "Job / Career",
    "Newsletters": "Promotions / Marketing",
    "Personal": "Social / Personal",
    "Promotions": "Promotions / Marketing",
    "Reminders": "Notifications",
    "Travel & Bookings": "Travel",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(str(text or "")))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def load_data() -> tuple[list[str], list[str], dict[str, int]]:
    records: list[tuple[str, str]] = []
    with DATA_PATH.open(encoding="utf-8") as handle:
        records.extend((item.get("text", ""), item.get("label", "")) for item in json.load(handle))
    with PUBLIC_DATA_PATH.open(encoding="utf-8") as handle:
        for item in json.load(handle):
            label = next((PUBLIC_LABEL_MAP[name] for name in item.get("labels", []) if name in PUBLIC_LABEL_MAP), None)
            if label:
                records.append((f"{item.get('subject', '')} {item.get('body', '')}", label))

    unique: dict[tuple[str, str], str] = {}
    for text, label in records:
        normalized = normalize_text(text)
        if len(normalized) >= 12 and label:
            unique[(normalized, label)] = normalized
    texts = [text for text, _ in unique]
    labels = [label for _, label in unique]
    counts = {label: labels.count(label) for label in sorted(set(labels))}
    return texts, labels, counts


def build_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(ngram_range=(1, 2), max_features=50000, sublinear_tf=True, min_df=1, strip_accents="unicode")


def build_pipeline(model_name: str, calibrated: bool = False) -> Pipeline:
    if model_name == "logistic_regression":
        estimator = LogisticRegression(C=2.0, class_weight="balanced", max_iter=3000)
    elif model_name == "balanced_svc":
        estimator = LinearSVC(C=1.5, class_weight="balanced", max_iter=5000)
    else:
        estimator = LinearSVC(C=1.0, max_iter=5000)
    if calibrated:
        estimator = CalibratedClassifierCV(estimator, cv=3, method="sigmoid")
    return Pipeline([("tfidf", build_vectorizer()), ("clf", estimator)])


def score_model(model: Pipeline, texts: list[str], labels: list[int]) -> dict[str, float]:
    predictions = model.predict(texts)
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision_macro": float(precision_score(labels, predictions, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(labels, predictions, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(labels, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(labels, predictions, average="weighted", zero_division=0)),
    }


def train() -> tuple[Pipeline, LabelEncoder, dict]:
    texts, labels, class_counts = load_data()
    encoder = LabelEncoder()
    encoded = encoder.fit_transform(labels)
    train_texts, test_texts, train_labels, test_labels = train_test_split(texts, encoded, test_size=0.2, random_state=42, stratify=encoded)
    fit_texts, validation_texts, fit_labels, validation_labels = train_test_split(train_texts, train_labels, test_size=0.25, random_state=42, stratify=train_labels)

    validation_results = {}
    for name in ("baseline_svc", "logistic_regression", "balanced_svc"):
        model = build_pipeline(name)
        model.fit(fit_texts, fit_labels)
        validation_results[name] = score_model(model, validation_texts, validation_labels)
        logger.info("Validation %s: %s", name, validation_results[name])

    selected_name = max(validation_results, key=lambda name: validation_results[name]["macro_f1"])
    final_model = build_pipeline(selected_name, calibrated=True)
    final_model.fit(train_texts, train_labels)
    test_predictions = final_model.predict(test_texts)
    test_scores = score_model(final_model, test_texts, test_labels)
    per_class = classification_report(test_labels, test_predictions, labels=list(range(len(encoder.classes_))), target_names=list(encoder.classes_), output_dict=True, zero_division=0)
    matrix = confusion_matrix(test_labels, test_predictions, labels=list(range(len(encoder.classes_))))
    result = {
        "dataset": {"source": "imnim/multiclass-email-classification", "license": "MIT", "public_samples": 2105, "unique_merged_samples": len(texts), "classes": len(encoder.classes_), "class_counts": class_counts},
        "split": {"train": len(train_texts), "validation": len(validation_texts), "test": len(test_texts), "random_state": 42},
        "validation_comparison": validation_results,
        "selected_model": selected_name,
        "test_metrics": test_scores,
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "confusion_matrix_labels": list(encoder.classes_),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as handle:
        pickle.dump({"pipeline": final_model, "label_encoder": encoder, "metadata": result}, handle)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    logger.info("Loaded %d unique samples across %d categories", len(texts), len(class_counts))
    logger.info("Selected %s; test metrics: %s", selected_name, test_scores)
    logger.info("Model saved to %s", MODEL_PATH)
    return final_model, encoder, result


if __name__ == "__main__":
    train()