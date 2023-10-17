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

# mypy test app
mypy

# pytest
pytest
