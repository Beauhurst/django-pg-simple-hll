import json
from datetime import timedelta
from itertools import product
from pathlib import Path

import pytest
from django.core.exceptions import FieldError
from django.db.models import Case, F, Q, When
from django.db.models.functions import TruncDate
from django.db.utils import DataError, ProgrammingError
from django_pg_simple_hll.aggregate import HLLCardinality, HLLCardinalityFromHash
from django_pg_simple_hll.functions import HLLHash

from .conftest import CREATED_NOW, N_DAYS
from .hyperloglog import HyperLogLog
from .models import Group, Session

FIELDS = ("user_int", "user_uuid", "user_str")
PRECISIONS_TO_TEST = (4, 5, 8, 9, 10, 11, 12)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
            .annotate(raw=F(field), hash=HLLHash(F(field)))
            .values("hash", "raw")
        )

        hll = HyperLogLog(precision)
        for s in query:
            if field == "user_hash":
                hll.add(s["raw"])
            else:
                hll.add(s["hash"])

        fixtures[day_of_week] = int(hll.cardinality())

    with open(FIXTURES_DIR / f"{field}.{precision}.json", "w") as f:
        json.dump(fixtures, f)

    return fixtures


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_total(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinality(field, precision),
    )

    assert fixtures[N_DAYS - 1] == aggregation["approx_unique_users"]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.django_db()
def test_hll_cardinality_with_default_precision_total(field: str) -> None:
    fixtures = _get_reference_approximation(field, 9)
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinality(field),
    )

    assert fixtures[N_DAYS - 1] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_total(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash(HLLHash(field), precision),
    )

    assert fixtures[N_DAYS - 1] == aggregation["approx_unique_users"]


@pytest.mark.parametrize("precision", PRECISIONS_TO_TEST)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_pre_hashed_total(precision: int) -> None:
    fixtures = _get_reference_approximation("user_hash", precision)
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash("user_hash", precision),
    )

    assert fixtures[N_DAYS - 1] == aggregation["approx_unique_users"]


@pytest.mark.django_db()
def test_hll_cardinality_raises_error_without_expression() -> None:
    """HLLCardinality cannot be used without targetting a specific field"""
    with pytest.raises(ProgrammingError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinality(),
        )


@pytest.mark.django_db()
def test_hll_cardinality_from_hash_raises_error_without_expression() -> None:
    """HLLCardinalityFromHash cannot be used without targetting a specific field"""
    with pytest.raises(ProgrammingError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinalityFromHash(),
        )


@pytest.mark.django_db()
def test_hll_cardinality_raises_error_with_star() -> None:
    """HLLCardinality cannot be used without targetting a specific field"""
    with pytest.raises(FieldError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinality("*"),
        )


@pytest.mark.django_db()
def test_hll_cardinality_raises_error_with_star_and_precision() -> None:
    """HLLCardinality cannot be used without targetting a specific field"""
    with pytest.raises(FieldError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinality("*", 9),
        )


@pytest.mark.django_db()
def test_hll_cardinality_from_hash_raises_error_with_star() -> None:
    """HLLCardinality cannot be used without targetting a specific field"""
    with pytest.raises(FieldError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinalityFromHash("*", 9),
        )


@pytest.mark.django_db()
def test_hll_cardinality_from_hash_raises_error_with_no_precision() -> None:
    """HLLCardinalityFromHash cannot be used without targetting a specific field"""
    with pytest.raises(ProgrammingError):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinalityFromHash(HLLHash("user_str")),
        )


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_raises_error_with_no_hash(field: str) -> None:
    """HLLCardinalityFromHash cannot be used without targetting a specific field"""

    error_type: type[Exception]

    if field == "user_int":
        # hll_cardinality_from_hash is defined for integers
        # this will give unexpected results because user_int is not hashed
        # however, because there is a user_int of 0, it will raise a DataError
        # because you cannot take the log of 0
        error_type = DataError
    else:
        error_type = ProgrammingError

    with pytest.raises(error_type):
        Session.objects.aggregate(
            approx_unique_users=HLLCardinalityFromHash(field, 9),
        )


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_with_filter(field: str, precision: int) -> None:
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


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_with_filter(field: str, precision: int) -> None:
    days_for_filter = 2
    fixtures = _get_reference_approximation(field, precision)

    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash(
            HLLHash(field),
            precision,
            filter=Q(created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)),
        ),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize("precision", PRECISIONS_TO_TEST)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_pre_hashed_with_filter(precision: int) -> None:
    days_for_filter = 2
    fixtures = _get_reference_approximation("user_hash", precision)

    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash(
            "user_hash",
            precision,
            filter=Q(created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)),
        ),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_implicit_join(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    days_for_filter = 4

    aggregation = Group.objects.filter(
        created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)
    ).aggregate(
        approx_unique_users=HLLCardinality(f"sessions__{field}", precision),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_implicit_join(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    days_for_filter = 4

    aggregation = Group.objects.filter(
        created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)
    ).aggregate(
        approx_unique_users=HLLCardinalityFromHash(
            HLLHash(f"sessions__{field}"), precision
        ),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize("precision", PRECISIONS_TO_TEST)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_pre_hashed_implicit_join(precision: int) -> None:
    fixtures = _get_reference_approximation("user_hash", precision)
    days_for_filter = 4

    aggregation = Group.objects.filter(
        created__lt=CREATED_NOW + timedelta(days=days_for_filter + 2)
    ).aggregate(
        approx_unique_users=HLLCardinalityFromHash("sessions__user_hash", precision),
    )
    assert fixtures[days_for_filter] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_with_expression(field: str, precision: int) -> None:
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


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_with_expression(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)
    days_for_expression = 3

    expression = Case(
        When(
            created__lt=CREATED_NOW + timedelta(days=days_for_expression + 2),
            then=F(field),
        )
    )  # Works since NULLs aren't counted
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash(HLLHash(expression), precision),
    )
    assert fixtures[days_for_expression] == aggregation["approx_unique_users"]


@pytest.mark.parametrize("precision", PRECISIONS_TO_TEST)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_pre_hashed_with_expression(precision: int) -> None:
    fixtures = _get_reference_approximation("user_hash", precision)
    days_for_expression = 3

    expression = Case(
        When(
            created__lt=CREATED_NOW + timedelta(days=days_for_expression + 2),
            then=F("user_hash"),
        )
    )  # Works since NULLs aren't counted
    aggregation = Session.objects.aggregate(
        approx_unique_users=HLLCardinalityFromHash(expression, precision),
    )
    assert fixtures[days_for_expression] == aggregation["approx_unique_users"]


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_by_date(field: str, precision: int) -> None:
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


@pytest.mark.parametrize(("field", "precision"), product(FIELDS, PRECISIONS_TO_TEST))
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_by_date(field: str, precision: int) -> None:
    fixtures = _get_reference_approximation(field, precision)

    aggregation = (
        Session.objects.annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(
            approx_unique_users=HLLCardinalityFromHash(HLLHash(field), precision),
        )
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
    )
    for i, row in enumerate(aggregation):
        assert fixtures[i] == row["approx_unique_users"]


@pytest.mark.parametrize("precision", PRECISIONS_TO_TEST)
@pytest.mark.django_db()
def test_hll_cardinality_from_hash_pre_hashed_by_date(precision: int) -> None:
    fixtures = _get_reference_approximation("user_hash", precision)

    aggregation = (
        Session.objects.annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(
            approx_unique_users=HLLCardinalityFromHash("user_hash", precision),
        )
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
    )
    for i, row in enumerate(aggregation):
        assert fixtures[i] == row["approx_unique_users"]
