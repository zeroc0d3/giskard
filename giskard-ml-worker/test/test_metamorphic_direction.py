from ml_worker.testing.functions import GiskardTestFunctions


def _test_metamorphic_increasing_regression(df, model, threshold):
    tests = GiskardTestFunctions()
    perturbation = {
        "bmi": lambda x: x.bmi + x.bmi * 0.1}
    results = tests.metamorphic.test_metamorphic_increasing(
        df=df,
        model=model,
        perturbation_dict=perturbation,
        threshold=threshold
    )

    assert results.actual_slices_size[0] == 442
    assert results.number_of_perturbed_rows == 442
    assert round(results.metric, 2) == 0.44
    return results.passed


def _test_metamorphic_decreasing_regression(df, model, threshold):
    tests = GiskardTestFunctions()
    perturbation = {
        "age": lambda x: x.age - x.age * 0.1}
    results = tests.metamorphic.test_metamorphic_decreasing(
        df=df,
        model=model,
        perturbation_dict=perturbation,
        threshold=threshold
    )
    assert results.actual_slices_size[0] == 442
    assert results.number_of_perturbed_rows == 442
    assert round(results.metric, 2) == 0.54
    return results.passed


def _test_metamorphic_increasing_classification(df, model, threshold):
    tests = GiskardTestFunctions()
    perturbation = {
        "duration_in_month": lambda x: x.duration_in_month + x.duration_in_month * 0.5}
    results = tests.metamorphic.test_metamorphic_increasing(
        df=df,
        model=model,
        classification_label=model.classification_labels[0],
        perturbation_dict=perturbation,
        threshold=threshold
    )

    assert results.actual_slices_size[0] == 1000
    assert results.number_of_perturbed_rows == 1000
    assert results.metric == 1
    return results.passed


def _test_metamorphic_decreasing_classification(df, model, threshold):
    tests = GiskardTestFunctions()
    perturbation = {
        "duration_in_month": lambda x: x.duration_in_month - x.duration_in_month * 0.5}
    results = tests.metamorphic.test_metamorphic_decreasing(
        df=df,
        model=model,
        classification_label=model.classification_labels[0],
        perturbation_dict=perturbation,
        threshold=threshold
    )

    assert results.actual_slices_size[0] == 1000
    assert results.number_of_perturbed_rows == 1000
    assert results.metric == 1
    return results.passed


def test_metamorphic_increasing_classification(german_credit_test_data, german_credit_model):
    assert _test_metamorphic_increasing_classification(german_credit_test_data, german_credit_model, 0.8)


def test_metamorphic_decreasing_classification(german_credit_test_data, german_credit_model):
    assert _test_metamorphic_decreasing_classification(german_credit_test_data, german_credit_model, 0.8)


def test_metamorphic_increasing_regression(diabetes_dataset, linear_regression_diabetes):
    assert _test_metamorphic_increasing_regression(diabetes_dataset, linear_regression_diabetes, 0.3)
    assert not _test_metamorphic_increasing_regression(diabetes_dataset, linear_regression_diabetes, 0.5)


def test_metamorphic_decreasing_regression(diabetes_dataset, linear_regression_diabetes):
    assert _test_metamorphic_decreasing_regression(diabetes_dataset, linear_regression_diabetes, 0.5)
    assert not _test_metamorphic_decreasing_regression(diabetes_dataset, linear_regression_diabetes, 0.6)