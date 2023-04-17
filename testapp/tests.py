from collections import defaultdict
from collections.abc import Iterable
from math import log, sqrt

import pytest
from django.db.models import Count
from django.db.models.functions import TruncDate
from django_pg_simple_hll.aggregate import ApproxCardinality

from .models import Session

FIELDS = ("user_int", "user_uuid", "user_str")
PRECISIONS_TO_TEST = (5, 8, 9, 10, 11, 12)  # if tails intermittently with 4


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


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST),
)
@pytest.mark.django_db()
def test_total(field: str, precision: int) -> None:
    N = 10
    # get N random records:
    rand_sessions = list(Session.objects.values_list(field)[:N])

    square_difference_of_means = []
    for session in rand_sessions:
        filter = {f"{field}__lte": session[0]}
        aggregation = Session.objects.filter(**filter).aggregate(
            unique_users=Count(field, distinct=True),
            approx_unique_users=ApproxCardinality(field, precision),
        )
        square_difference_of_means.append(
            (aggregation["unique_users"] - aggregation["approx_unique_users"]) ** 2
        )

    actual_error = sqrt(sum(square_difference_of_means) / N)

    assert actual_error <= _calculate_error(precision)


@pytest.mark.parametrize(
    ("field", "precision"), __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST)
)
@pytest.mark.django_db()
def test_by_date(field: str, precision: int) -> None:
    N = 10
    # get N random records:
    rand_sessions = list(Session.objects.values_list(field)[:N])

    square_difference_of_means = defaultdict(list)
    for session in rand_sessions:
        filter = {f"{field}__lte": session[0]}

        aggregation = (
            Session.objects.filter(**filter)
            .annotate(date_of_session=TruncDate("created"))
            .values("date_of_session")
            .annotate(
                approx_unique_users=ApproxCardinality(field, precision),
                unique_users=Count(field, distinct=True),
            )
            .values("approx_unique_users", "unique_users", "date_of_session")
        )
        for row in aggregation:
            square_difference_of_means[row["date_of_session"]].append(
                (row["unique_users"] - row["approx_unique_users"]) ** 2
            )
    expected_error = _calculate_error(precision)
    for _, square_difference_of_means_for_date in square_difference_of_means.items():
        actual_error = sqrt(sum(square_difference_of_means_for_date) / N)
        assert actual_error <= expected_error
