import pytest
import numpy as np
from unittest.mock import Mock

from giskard import WrapperModel
from giskard.core.core import ModelMeta
from functools import partial


def _make_model_mock(labels=["First", "Second", "Third"]):
    model = Mock(WrapperModel)
    meta = Mock(ModelMeta)
    meta.classification_labels = labels
    model.meta = meta
    model.model_postprocessing_function = None

    model._possibly_fix_predictions_shape = partial(WrapperModel._possibly_fix_predictions_shape, model)

    return model


def test_postprocess():
    model = _make_model_mock(["one", "two"])

    data_prepocessing_function_output = np.array(0.6)
    result = WrapperModel._postprocess(model, data_prepocessing_function_output)

    assert result.ndim == 2
    if WrapperModel.is_binary_classification:
        assert result.shape[1] == 2

    data_prepocessing_function_output = np.array([0.6])
    result = WrapperModel._postprocess(model, data_prepocessing_function_output)

    assert result.ndim == 2
    if WrapperModel.is_binary_classification:
        assert result.shape[1] == 2

    data_prepocessing_function_output = np.array([[0.6], [0.4]])
    result = WrapperModel._postprocess(model, data_prepocessing_function_output)

    assert result.ndim == 2
    if WrapperModel.is_binary_classification:
        assert result.shape[1] == 2


def test_postprocess_fixes_dummy_dimensions_by_squeezing():
    model = _make_model_mock()

    data = np.random.normal(size=(10, 1, 1, 1, 1, 1, 1, 1, 3))
    result = WrapperModel._postprocess(model, data)

    assert result.ndim == 2
    assert result.shape == (10, 3)

    # But should not squeeze first and last dimension
    data = np.random.uniform(size=(1, 3))
    result = WrapperModel._postprocess(model, data)
    assert result.shape == (1, 3)


def test_postprocess_fixes_missing_binary_class():
    model = _make_model_mock(["one", "two"])

    # Should handle 1d data and convert it to (n_entries, 2)
    data = np.random.uniform(size=10)
    result = WrapperModel._postprocess(model, data)

    assert result.shape == (10, 2)
    assert (result[:, 0] == data).all()
    assert np.allclose(result[:, 1], 1 - data)

    # Same for 2d data with a single class
    data = np.random.uniform(size=(10, 1))
    result = WrapperModel._postprocess(model, data)

    assert result.shape == (10, 2)
    assert (result[:, 0] == data[:, 0]).all()
    assert np.allclose(result[:, 1], 1 - data[:, 0])


def test_raises_error_if_classifier_shape_is_not_right():
    # Two classes and 3 outputs: wrong
    model = _make_model_mock(["one", "two"])
    data = np.random.uniform(size=(10, 3))

    with pytest.raises(ValueError):
        _ = WrapperModel._postprocess(model, data)

    # Three classes and 2 outputs: wrong
    model = _make_model_mock(["one", "two", "three"])
    data = np.random.uniform(size=(10, 2))
    with pytest.raises(ValueError):
        _ = WrapperModel._postprocess(model, data)

    # 4 outputs: still wrong
    data = np.random.uniform(size=(10, 4))
    with pytest.raises(ValueError):
        _ = WrapperModel._postprocess(model, data)


def test_should_convert_to_numpy():
    model = _make_model_mock(["one", "two"])
    result = WrapperModel._postprocess(model, [1, 2, 3, 4])
    assert isinstance(result, np.ndarray)
