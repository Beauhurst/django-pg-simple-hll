import json
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.exceptions import FieldError
from django.db.models import Case, F, Func, Q, When
from django.db.models.functions import TruncDate
from django.db.utils import ProgrammingError
from django_pg_simple_hll.aggregate import HLLCardinality

from .conftest import CREATED_NOW, N_DAYS
from .hyperloglog import HyperLogLog
from .models import Group, Session

FIELDS = ("user_int", "user_uuid", "user_str")
PRECISIONS_TO_TEST = (4, 5, 8, 9, 10, 11, 12)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class HashText(Func):
    template = "HASHTEXT(%(expressions)s::text) & ~(1 << 31)"


def __combine_params(
    field: Iterable[str], precision: Iterable[int]
) -> Iterable[tuple[str, int]]:
    for field_name in field:
        for precision_value in precision:
            yield (field_name, precision_value)


def _get_reference_approximation(field: str, precision: int) -> dict[int, int]:
    """
    Get the reference approximation for a given field and precision
    Calculate values only once, and store them in a JSON file for future use
    """
    fixture_path = FIXTURES_DIR / f"{field}.{precision}.json"

    if fixture_path.exists():
        with open(fixture_path) as f:
            return {int(key): val for key, val in json.load(f).items()}

    fixtures = {}
    for day_of_week in range(N_DAYS):
        timestamp = CREATED_NOW + timedelta(days=day_of_week + 2)
        query = (
            Session.objects.filter(created__lt=timestamp)
            .annotate(hash=HashText(F(field)))
            .values("hash")
        )

        hll = HyperLogLog(precision)
        for s in query:
            hll.add(s["hash"])

        fixtures[day_of_week] = int(hll.cardinality())

    with open(FIXTURES_DIR / f"{field}.{precision}.json", "w") as f:
        json.dump(fixtures, f)

    return fixtures


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST),
)
@pytest.mark.django_db()
def test_total(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinality(field, precision),
    )

    assert fixtures[N_DAYS - 1] == aggregation["approx_unique_users"]


@pytest.mark.django_db()
def test_raises_error_without_expression() -> None:
    """Aggregation cannot be used without targetting a specific field"""
    with pytest.raises(ProgrammingError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinality(),
        )


@pytest.mark.django_db()
def test_raises_error_with_star() -> None:
    """Aggregation cannot be used without targetting a specific field"""
    with pytest.raises(FieldError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinality("*"),
        )


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST),
)
@pytest.mark.django_db()
def test_with_filter(field: str, precision: int) -> None:
    days_for_filter = 2
    fixtures = _get_reference_approximation(field, precision)

    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinality(
            field,
            precision,
            filter=Q(created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)),
        ),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST),
)
@pytest.mark.django_db()
def test_implicit_join(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    days_for_filter = 4

    aggregation = Group.objects.filter(
        created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)
    ).aggregate(
        approx_unique_users=HLLCardinality(f"sessions__{field}", precision),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(
    ("field", "precision"),
    __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST),
)
@pytest.mark.django_db()
def test_with_expression(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    days_for_expression = 3

    expression = Case(
        When(
            created__lt=CREATED_NOW + timedelta(days=days_for_expression + 2),
            then=F(field),
        )
    )  # Works since NULLs aren't counted
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinality(expression, precision),
    )
    assert fixtures[days_for_expression] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(
    ("field", "precision"), __combine_params(field=FIELDS, precision=PRECISIONS_TO_TEST)
)
@pytest.mark.django_db()
def test_by_date(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)

    aggregation = (
        Session.objects.annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(
            approx_unique_users=HLLCardinality(field, precision),
        )
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
    )
    for i, row in enumerate(aggregation):
        assert fixtures[i] == row["approx_unique_users"]
