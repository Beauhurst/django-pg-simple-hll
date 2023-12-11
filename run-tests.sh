#!/bin/sh
set -x -e

# lint
ruff check .

# Check formatting
ruff format --diff .

# sqlfluff
# TODO: Enforce linting when sqlfluff can handle postgresql aggregates
# https://github.com/sqlfluff/sqlfluff/issues/3556
# sqlfluff lint

# mypy test app
mypy

# pytest
pytest
