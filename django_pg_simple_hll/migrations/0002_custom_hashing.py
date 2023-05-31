from django.db import migrations

from . import load_sql


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("django_pg_simple_hll", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=load_sql(__file__), reverse_sql=load_sql(__file__, reverse=True)
        )
    ]
