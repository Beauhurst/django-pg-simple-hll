from collections.abc import Iterable
from datetime import datetime, timedelta
from hashlib import blake2s
from itertools import islice
from random import randint
from typing import Any
from uuid import UUID

import pytest
from django.utils.timezone import now

from .models import Group, Session

TEST_DATA_BASE_TIMESTAMP = now().replace(hour=0, minute=0, second=0, microsecond=0)
TEST_DATA_N_USER_IDS = 140_000
TEST_DATA_N_SESSION_DAYS = 7

DB_BATCH_SIZE = 2_500


def uuid_hash_31bit(id: UUID) -> int:
    """return a 31bit hash of the uuid"""
    return int.from_bytes(
        blake2s(id.hex.encode("utf-8")).digest(),
        byteorder="big",
        signed=False,
    ) % (2**31 - 1)


def yield_sessions_for_ids(
    ids: Iterable[UUID], group: Group, on_day: datetime
) -> Iterable[Session]:
    for user_int, user_uuid in enumerate(ids):
        yield Session(
            user_uuid=user_uuid,
            user_int=user_int,
            user_str=f"{user_int}-{user_uuid}",
            user_hash=uuid_hash_31bit(user_uuid),
            created=on_day + timedelta(hours=randint(0, 23), minutes=randint(0, 59)),
            group=group,
        )


def generate_test_data(
    n_user_ids: int = TEST_DATA_N_USER_IDS,
    n_session_days: int = TEST_DATA_N_SESSION_DAYS,
    base_timestamp: datetime = TEST_DATA_BASE_TIMESTAMP,
    db_batch_size: int = DB_BATCH_SIZE,
) -> None:
    """
    Creates a list of users and inserts sessions for those users for each day of the week.

    This is a fixture because it's expensive to create the data, and we want to reuse it

    The first day it will insert sessions for 1/n_session_days of the users
    For every day after that, it will insert sessions for a further 1/n_session_days
    of users and all previous users
    """

    for day_of_week in range(n_session_days + 1):
        group = Group.objects.create(
            id=UUID(int=day_of_week),
            created=base_timestamp + timedelta(days=day_of_week),
        )
        total_sessions_per_day = int(day_of_week * (n_user_ids / n_session_days))

        # This creates an iterator that can generate Sessions on demand
        session_factory = iter(
            yield_sessions_for_ids(
                ids=(UUID(int=i) for i in range(total_sessions_per_day)),
                group=group,
                on_day=base_timestamp + timedelta(days=day_of_week),
            )
        )
        # Insert batches into the db:
        # The reason we do not just feed all the sessions is that `.bulk_create`
        # will consume the entire set before communicating with the db.
        # The `batch_size` is only used for communicating with the db.
        while batch_of_sessions := tuple(islice(session_factory, db_batch_size)):
            Session.objects.bulk_create(
                batch_of_sessions,
                batch_size=db_batch_size,
            )


@pytest.fixture(scope="session")
def django_db_setup(  # noqa: PT004 - this fixture's name is fixed by django-pytest
    # these objects are magically used by pytest-django to setup the db\
    # they don't need to be annotated
    django_db_setup: Any,
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock():
        generate_test_data()
