from os import PathLike
from pathlib import Path


def load_sql(path: PathLike[str] | str, reverse: bool = False) -> str:
    """
    This utility loads sql from base path with a `.sql` suffix,
    optionally it attaches a `.reverse.sql` suffix

    We use it to write migrations that can be run both forwards and backwards

    e.g.
    load_sql('migrations/0001_initial'),
        will load `migrations/0001_initial.sql`

    and

    load_sql('migrations/0001_initial', reverse=True),
        will load `migrations/0001_initial.reverse.sql`

    """
    path = Path(path)
    parent = path.parent
    stem = path.stem
    if reverse:
        filename = f"{stem}.reverse.sql"
    else:
        filename = f"{stem}.sql"

    with open(parent / filename) as sql_file:
        return sql_file.read()
