from collections.abc import Iterable
from math import log, sqrt
from statistics import mean
from typing import Any

import pytest
from django.db.models import Count
from django.db.models.functions import TruncDate
from django_pg_simple_hll.aggregate import ApproxCardinality

from .models import Session


def _calculate_error(precision: int) -> float:
    """
    Calculates the expected error for the given precision

    E.g. If we use 9 bits of precision, we have 512 buckets
    we should have sqrt(3 * log(2) - 1) / sqrt(512)
    -> 4.592% expected error
    """
    return sqrt(3 * log(2) - 1) / sqrt(2**precision)


def __combine_params(
    field: Iterable[str], precision: Iterable[int]
) -> Iterable[tuple[str, int]]:
    for field_name in field:
        for precision_value in precision:
            yield (field_name, precision_value)


def __test_id(val: Any) -> str:
    return str(val)


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(
        field=("user_int", "user_uuid", "user_str"),
        precision=(4, 5, 6, 7, 8, 9, 10, 11),
    ),
    ids=__test_id,
)
@pytest.mark.django_db()
def test_total(field: str, precision: int) -> None:
    frequency_actual = Session.objects.aggregate(
        unique_users=Count(field, distinct=True)
    )["unique_users"]

    frequency_approximated = Session.objects.aggregate(
        approx_unique_users=ApproxCardinality(field, precision)
    )["approx_unique_users"]

    # TODO: we really should be testing something like this
    # actual_error ~ ERROR
    # but really we are just saying is the error less than double the expected
    actual_error = abs(frequency_actual - frequency_approximated) / frequency_actual
    assert actual_error <= _calculate_error(precision) * 2


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(
        field=("user_int", "user_uuid", "user_str"),
        precision=(4, 5, 6, 7, 8, 9, 10, 11),
    ),
)
@pytest.mark.django_db()
def test_by_date(field: str, precision: int) -> None:
    frequency_actual = {
        d["date_of_session"]: d["unique_users"]
        for d in Session.objects.annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(unique_users=Count(field, distinct=True))
        .values("unique_users", "date_of_session")
    }
    frequency_approximated = {
        d["date_of_session"]: d["approx_unique_users"]
        for d in Session.objects.annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=ApproxCardinality(field, precision))
        .values("approx_unique_users", "date_of_session")
    }

    accumulated_error = []
    for date in set(frequency_actual.keys()) | set(frequency_approximated.keys()):
        accumulated_error.append(
            abs(frequency_actual[date] - frequency_approximated[date])
            / frequency_actual[date]
        )

    # TODO: we really should be testing something like this
    # accumulated_error ~ ERROR
    # but really we are just saying is the error less than double the expected
    assert mean(accumulated_error) <= _calculate_error(precision) * 2
