#!/bin/sh
set -x -e

# ruff
ruff check .

# black
black --check .

# docker build
docker compose build

# mypy test app
docker compose run testapp mypy --package testapp --package django_pg_simple_hll

# pytest
docker compose run testapp pytest
