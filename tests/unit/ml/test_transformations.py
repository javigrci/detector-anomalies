"""FR-004-06, 07: transformaciones ajustadas con entrenamiento y tolerantes a categorías nuevas."""

import numpy as np

from security_anomaly.features.schema import FEATURE_SCHEMA
from security_anomaly.ml.dataset import Partition, make_dataset, split_temporal
from security_anomaly.ml.pipeline import TrainedModel, feature_matrix, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors, tweak

NUMERIC = [d.name for d in FEATURE_SCHEMA.definitions if d.kind != "category"]
CATEGORICAL = [d.name for d in FEATURE_SCHEMA.definitions if d.kind == "category"]


def _model_and_partition() -> tuple[TrainedModel, Partition]:
    data = synthetic_vectors(3, 1500)
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    return train_model(partition, MlPolicy()), partition


def test_the_feature_matrix_has_one_column_per_schema_feature_in_order() -> None:
    data = synthetic_vectors(3, 300)
    matrix = feature_matrix(data.vectors[:50])
    assert matrix.shape == (50, len(FEATURE_SCHEMA.names))
    assert matrix[0, 0] == data.vectors[0].features["hour_sin"]


def test_the_output_has_numeric_columns_then_one_hot_blocks() -> None:
    model, partition = _model_and_partition()
    out = model.transformer.transform(feature_matrix(partition.test[:10]))
    encoder = model.transformer.named_transformers_["categorical"]
    expected = len(NUMERIC) + sum(len(c) for c in encoder.categories_)
    assert out.shape == (10, expected)
    assert out.dtype == np.float64
    assert len(encoder.categories_) == len(CATEGORICAL)


def test_categories_are_learned_from_training_only_and_sorted() -> None:
    model, partition = _model_and_partition()
    encoder = model.transformer.named_transformers_["categorical"]
    seen = {name: {str(v.features[name]) for v in partition.train} for name in CATEGORICAL}
    for name, categories in zip(CATEGORICAL, encoder.categories_, strict=True):
        assert [str(c) for c in categories] == sorted(seen[name])


def test_an_unknown_category_gives_zeros_in_its_block_and_no_error() -> None:
    model, partition = _model_and_partition()
    base = partition.test[0]
    unknown = tweak(base, source="never-seen-source")
    a = model.transformer.transform(feature_matrix([base]))[0]
    b = model.transformer.transform(feature_matrix([unknown]))[0]
    encoder = model.transformer.named_transformers_["categorical"]
    offset = len(NUMERIC) + sum(len(c) for c in encoder.categories_[:-1])  # `source` es la última
    width = len(encoder.categories_[-1])
    assert np.all(b[offset : offset + width] == 0)
    assert np.array_equal(a[:offset], b[:offset])  # lo demás no cambia


def test_no_identifier_is_encoded() -> None:
    model, _ = _model_and_partition()
    columns = [name for _, _, cols in model.transformer.transformers_[:2] for name in cols]
    assert sorted(columns) == list(range(len(FEATURE_SCHEMA.names)))
    names = FEATURE_SCHEMA.names
    for index in model.transformer.transformers_[1][2]:
        assert names[index] in {"event_type", "action", "outcome", "source"}


def test_a_training_set_with_a_single_category_value_does_not_fail() -> None:
    data = synthetic_vectors(3, 1500, burst_count=0)
    vectors = [tweak(v, source="only-source") for v in data.vectors]
    partition = split_temporal(make_dataset(vectors), MlPolicy())
    model = train_model(partition, MlPolicy())
    out = model.transformer.transform(feature_matrix(partition.test[:5]))
    assert out.shape[0] == 5
