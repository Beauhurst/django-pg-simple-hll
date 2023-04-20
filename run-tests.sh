#!/bin/sh
set -x -e

# ruff
ruff check .

# black
black --check .

# sqlfluff
# TODO: Enforce linting when sqlfluff can handle postgresql aggregates
# https://github.com/sqlfluff/sqlfluff/issues/3556
# sqlfluff lint

# docker build
docker compose build

# mypy test app
docker compose run testapp mypy --package testapp --package django_pg_simple_hll

# pytest
docker compose run testapp pytest
