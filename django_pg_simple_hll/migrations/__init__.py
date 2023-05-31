from os import PathLike
from pathlib import Path


def load_sql(path: PathLike[str] | str, reverse: bool = False) -> str:
    path = Path(path)
    parent = path.parent
    stem = path.stem
    if reverse:
        filename = f"{stem}.reverse.sql"
    else:
        filename = f"{stem}.sql"

    with open(parent / filename) as sql_file:
        return sql_file.read()
