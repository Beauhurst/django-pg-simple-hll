from collections.abc import Iterable
from datetime import datetime, timedelta
from random import randint
from typing import Any
from uuid import UUID

import pytest
from django.utils.timezone import now

from .models import Group, Session

CREATED_NOW = now().replace(hour=0, minute=0, second=0, microsecond=0)
N_USER_IDS = 140_000
N_DAYS = 7

DB_BATCH_SIZE = 1_000


def yield_sessions_for_ids(
    ids: list[UUID], group: Group, on_day: datetime
) -> Iterable[Session]:
    for user_int, user_uuid in enumerate(ids):
        yield Session(
            user_uuid=user_uuid,
            user_int=user_int,
            user_str=f"{user_int}-{user_uuid}",
            created=on_day + timedelta(hours=randint(0, 23), minutes=randint(0, 59)),
            group=group,
        )


@pytest.fixture(scope="session")
def django_db_setup(  # noqa: PT004 - this fixture's name is fixed by django-pytest
    # these objects are magically used by pytest-django to setup the db\
    # they don't need to be annotated
    django_db_setup: Any,
    django_db_blocker: Any,
) -> None:
    """
    Creates a list of users and inserts sessions for those users for each day of the week.

    This is a fixture because it's expensive to create the data, and we want to reuse it

    The first day it will insert sessions for 1/N_DAYS of the users
    For every day after that, it will insert sessions for a further 1/N_DAYS of users
    and all previous users
    """

    user_ids = [UUID(int=i) for i in range(N_USER_IDS)]

    with django_db_blocker.unblock():
        for day_of_week in range(N_DAYS + 1):
            group = Group.objects.create(
                id=UUID(int=day_of_week),
                created=CREATED_NOW + timedelta(days=day_of_week),
            )

            Session.objects.bulk_create(
                yield_sessions_for_ids(
                    ids=user_ids[: int(day_of_week * (N_USER_IDS / N_DAYS))],
                    group=group,
                    on_day=CREATED_NOW + timedelta(days=day_of_week),
                ),
                batch_size=DB_BATCH_SIZE,
            )
