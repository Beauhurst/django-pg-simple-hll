# django_pg_simple_hll

Postgres only approximated cardinality aggregation for the Django ORM.

Instead of counting the number of distinct users,

```python
Session.objects.aggregate(unique_users=Count("user_uuid", distinct=True))

{'unique_users': 71287}
```

you can approximate it,

```python
Session.objects.aggregate(approx_unique_users=ApproxCardinality("user_uuid"))

{'approx_unique_users': 76914}
```

Or, instead of counting the number of distinct users per day,

```python
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(unique_users=Count("user_uuid", distinct=True))
        .values("unique_users", "date_of_session")
)

[{'date_of_session': datetime.date(2023, 4, 6), 'unique_users': 15292},
 {'date_of_session': datetime.date(2023, 4, 7), 'unique_users': 15289},
 {'date_of_session': datetime.date(2023, 4, 8), 'unique_users': 15395},
 {'date_of_session': datetime.date(2023, 4, 9), 'unique_users': 15484},
 {'date_of_session': datetime.date(2023, 4, 10), 'unique_users': 15315},
 {'date_of_session': datetime.date(2023, 4, 11), 'unique_users': 15346},
 {'date_of_session': datetime.date(2023, 4, 12), 'unique_users': 11791},
 {'date_of_session': datetime.date(2023, 4, 13), 'unique_users': 11672}]
```

you can approximate it,

```python

list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=ApproxCardinality("user_uuid"))
        .values("approx_unique_users", "date_of_session")
 )

 [{'date_of_session': datetime.date(2023, 4, 6), 'approx_unique_users': 15214},
 {'date_of_session': datetime.date(2023, 4, 7), 'approx_unique_users': 15686},
 {'date_of_session': datetime.date(2023, 4, 8), 'approx_unique_users': 15597},
 {'date_of_session': datetime.date(2023, 4, 9), 'approx_unique_users': 16056},
 {'date_of_session': datetime.date(2023, 4, 10), 'approx_unique_users': 15765},
 {'date_of_session': datetime.date(2023, 4, 11), 'approx_unique_users': 16620},
 {'date_of_session': datetime.date(2023, 4, 12), 'approx_unique_users': 12395},
 {'date_of_session': datetime.date(2023, 4, 13), 'approx_unique_users': 13029}]
```

The approximation is sometimes faster and uses less memory.

By default, it uses a precision of 9, which tends to have an error of about 5%. You can set a higher precision (up to 11)) through a second parameter:

```python
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=ApproxCardinality("user_uuid", 11))
        .values("approx_unique_users", "date_of_session")
)

[{'date_of_session': datetime.date(2023, 4, 6), 'approx_unique_users': 15430},
{'date_of_session': datetime.date(2023, 4, 7), 'approx_unique_users': 15261},
{'date_of_session': datetime.date(2023, 4, 8), 'approx_unique_users': 15739},
{'date_of_session': datetime.date(2023, 4, 9), 'approx_unique_users': 15357},
{'date_of_session': datetime.date(2023, 4, 10), 'approx_unique_users': 15511},
{'date_of_session': datetime.date(2023, 4, 11), 'approx_unique_users': 15117},
{'date_of_session': datetime.date(2023, 4, 12), 'approx_unique_users': 11658},
{'date_of_session': datetime.date(2023, 4, 13), 'approx_unique_users': 11841}]
```

You can also set a lower precision (down to 3) for a faster, less accurate estimate.

The aggregation is also available in SQL:

```sql

select
    date_trunc('day', created) as date_of_session,
    hll_approx_cardinality(user_uuid, 11) as approx_unique_users
from
    testapp_session
group by
    date_trunc('day', created);
    date_of_session     | approx_unique_users
------------------------+---------------------
 2023-04-06 00:00:00+00 |               15430
 2023-04-07 00:00:00+00 |               15261
 2023-04-08 00:00:00+00 |               15739
 2023-04-09 00:00:00+00 |               15357
 2023-04-10 00:00:00+00 |               15511
 2023-04-11 00:00:00+00 |               15117
 2023-04-12 00:00:00+00 |               11658
 2023-04-13 00:00:00+00 |               11841
(8 rows)

Time: 1289.249 ms (00:01.289)
```

## SQL implementation

This is a low-privilege implementation of [Hyperloglog](https://www.lix.polytechnique.fr/~fusy/Articles/FlFuGaMe07.pdf) approximate cardinality aggregation written in SQL and some [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html). Read about it [here](http://alejandro.giacometti.me/2023-03-30/hyperloglog-in-sql/),
