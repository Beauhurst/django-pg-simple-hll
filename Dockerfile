ARG PYTHON_IMAGE_TAG="3.11-slim"

FROM python:${PYTHON_IMAGE_TAG} as base

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install apt build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc libc6-dev

COPY poetry.lock pyproject.toml README.md /code/
COPY ./django_pg_simple_hll /code/django_pg_simple_hll
COPY ./testapp /code/testapp

# Install python dependencies
RUN --mount=type=cache,target=/root/.cache \
    pip install --upgrade --no-cache-dir --quiet pip setuptools wheel poetry

RUN poetry config virtualenvs.in-project true \
    && poetry install --with=dev --no-interaction

ENV PATH="/code/.venv/bin:$PATH"

CMD ["pytest"]
