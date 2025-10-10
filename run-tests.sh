#!/bin/sh
set -x -e

# lint
ruff check .

# Check formatting
ruff format --diff .

# sqlfluff
sqlfluff lint

# mypy test app
mypy

# pytest
pytest
