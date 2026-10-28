"""Ablatable sparse classification features for development experiments."""

from dataclasses import dataclass

from .preprocessing import PREPROCESSING_VERSION


FEATURE_CONTRACT_VERSION = "sparse-channels-v1"


@dataclass(frozen=True)
class FeatureSpec:
    word: bool = False
    char: bool = False
    subject: bool = False
    body: bool = False

    def __post_init__(self):
        if not any((self.word, self.char, self.subject, self.body)):
            raise ValueError("Select at least one feature channel")
        if not all(type(value) is bool for value in
                   (self.word, self.char, self.subject, self.body)):
            raise ValueError("Feature channels must be booleans")


FEATURE_VARIANTS = {
    "word": FeatureSpec(word=True),
    "word_char": FeatureSpec(word=True, char=True),
    "subject_body": FeatureSpec(subject=True, body=True),
    "all_channels": FeatureSpec(word=True, char=True, subject=True, body=True),
}


def select_channel(rows, *, field):
    """Top-level selector keeps fitted pipelines serializable."""
    if field not in ("text", "subject_text", "body_text"):
        raise ValueError("Unknown feature channel")
    values = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(field), str):
            raise ValueError("Feature row is missing a required text channel")
        values.append(row[field])
    return values


def validate_feature_rows(rows, spec):
    required = ["text"]
    if spec.subject:
        required.append("subject_text")
    if spec.body:
        required.append("body_text")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Feature row must be an object")
        for field in required:
            if not isinstance(row.get(field), str):
                raise ValueError("Feature row is missing a required text channel")
        if (spec.subject or spec.body) and row.get("preprocessing_version") != \
                PREPROCESSING_VERSION:
            raise ValueError("Feature row preprocessing version mismatch")
    if spec.subject and not any(row["subject_text"].strip() for row in rows):
        raise ValueError("Subject channel has no training text")
    if spec.body and not any(row["body_text"].strip() for row in rows):
        raise ValueError("Body channel has no training text")


def build_features(spec):
    """Create unfitted channels; vectorizers fit only inside a caller's fold."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import FunctionTransformer

    if not isinstance(spec, FeatureSpec):
        raise ValueError("Feature specification is required")
    channels = []

    def add(name, field, vectorizer):
        channels.append((name, Pipeline([
            ("select", FunctionTransformer(select_channel, validate=False,
                                           kw_args={"field": field})),
            ("tfidf", vectorizer),
        ])))

    if spec.word:
        add("word", "text", TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, max_features=30000))
    if spec.char:
        add("char", "text", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
            max_features=50000))
    if spec.subject:
        add("subject", "subject_text", TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, max_features=10000))
    if spec.body:
        add("body", "body_text", TfidfVectorizer(
            ngram_range=(1, 2), sublinear_tf=True, max_features=30000))
    return FeatureUnion(channels)
