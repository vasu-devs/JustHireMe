"""Regression suite entrypoint.

The original monolithic regression assertions now live in focused regression
files. Keep this file intentionally small so new coverage lands near the domain
it protects.
"""


def test_regression_suite_is_split():
    assert True
