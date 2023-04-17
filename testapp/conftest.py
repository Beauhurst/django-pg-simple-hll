from datetime import timedelta
from random import choice, randint
from typing import Any
from uuid import uuid4

import pytest
from django.utils.timezone import now

from .models import Session


@pytest.fixture(scope="session")
def django_db_setup(  # noqa: PT004 - this fixture's name is fixed by django-pytest
    # these objects are magically used by pytest-django to setup the db\
    # they don't need to be annotated
    django_db_setup: Any,
    django_db_blocker: Any,
) -> None:
    created_now = now()
    n_user_ids = 150_000
    user_ids = [uuid4() for _ in range(n_user_ids)]
    sessions = []
    for _ in range(250_000):
        user_int = randint(0, n_user_ids - 1)
        user_uuid = user_ids[user_int]
        user_str = f"{user_int}-{user_uuid}"
        timestamp = created_now + timedelta(
            days=choice([0, 1, 2, 3, 4, 7, 8, 9, 10, 11])
        )
        sessions.append(
            Session(
                user_uuid=user_uuid,
                user_int=user_int,
                user_str=user_str,
                created=timestamp,
            )
        )

    for _ in range(20_000):
        user_int = randint(0, n_user_ids - 1)
        user_uuid = user_ids[user_int]
        user_str = f"{user_int}-{user_uuid}"
        timestamp = created_now + timedelta(days=choice([5, 6, 12, 13]))
        sessions.append(
            Session(
                user_uuid=user_uuid,
                user_int=user_int,
                user_str=user_str,
                created=timestamp,
            )
        )
    with django_db_blocker.unblock():
        Session.objects.bulk_create(sessions)
