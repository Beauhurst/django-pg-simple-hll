from collections.abc import Iterable
from math import log, sqrt
from typing import Any

import pytest
from django.db.models import Count
from django.db.models.functions import TruncDate
from django_pg_simple_hll.aggregate import ApproxCardinality
from scipy.stats import ttest_ind

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
        precision=(5, 6, 7, 8, 9, 10, 11),  # fails intermittently with 4
    ),
    ids=__test_id,
)
@pytest.mark.django_db()
def test_total(field: str, precision: int) -> None:
    # get 5 random records:
    rand_sessions = list(Session.objects.values_list(field)[:5])

    frequency_actual = []
    frequency_approximated = []
    for session in rand_sessions:
        filter = {f"{field}__lte": session[0]}
        frequency_actual.append(
            Session.objects.filter(**filter).aggregate(
                unique_users=Count(field, distinct=True)
            )["unique_users"]
        )

        frequency_approximated.append(
            Session.objects.filter(**filter).aggregate(
                approx_unique_users=ApproxCardinality(field, precision)
            )["approx_unique_users"]
        )

    res = ttest_ind(frequency_actual, frequency_approximated)
    # TODO: I'm not sure this is the right comparison
    assert res.pvalue >= _calculate_error(precision)


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(
        field=("user_int", "user_uuid", "user_str"),
        precision=(5, 6, 7, 8, 9, 10, 11),  # fails intermittently with 4
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

    frequency_actual_dist, frequency_approximated_dist = zip(
        *[
            (frequency_actual[date], frequency_approximated[date])
            for date in set(frequency_actual.keys())
            | set(frequency_approximated.keys())
        ]
    )
    res = ttest_ind(frequency_actual_dist, frequency_approximated_dist)
    # TODO: I'm not sure this is the right comparison
    assert res.pvalue >= _calculate_error(precision)
