from pathlib import Path

from django.db import migrations


def load_sql(reverse: bool = False) -> str:
    this = Path(__file__)
    parent = this.parent
    stem = this.stem
    if reverse:
        filename = f"{stem}.reverse.sql"
    else:
        filename = f"{stem}.sql"

    with open(parent / filename) as sql_file:
        return sql_file.read()


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [migrations.RunSQL(sql=load_sql(), reverse_sql=load_sql(reverse=True))]
