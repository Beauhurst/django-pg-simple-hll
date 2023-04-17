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

By default, it uses a precision of 9, which tends to have an error of about 5%. You can set a higher precision (up to 31) through a second parameter:

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

You can also set a lower precision (down to 4) for a faster, less accurate estimate.

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

## Performance

This is not a scientific test, but here is an example of performance:

For a dataset of 125k a precision of 6 matches the speed of `COUNT(DISTINCT ...)`:

```sql

select count(user_uuid) from testapp_session;
 count
--------
 125000
(1 row)

Time: 31.401 ms

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
        71498
(1 row)

Time: 176.382 ms

select hll_approx_cardinality(user_uuid, 6) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
               77215
(1 row)

Time: 174.439 ms

select hll_approx_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
               74614
(1 row)

Time: 502.541 ms

```

For a dataset of 1.25M:

- a precision of 8 is about 60% faster than `COUNT(DISTINCT ...)`
- a precision 9 roughly matches the speed of `COUNT(DISTINCT ...)`

```sql

select count(user_uuid) from testapp_session;
  count
---------
 1250000
(1 row)

Time: 212.952 ms

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
       713161
(1 row)

Time: 1287.163 ms (00:01.287)

select hll_approx_cardinality(user_uuid, 8) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
              734585
(1 row)

Time: 777.405 ms

select hll_approx_cardinality(user_uuid, 9) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
              757331
(1 row)

Time: 1109.805 ms (00:01.110)

select hll_approx_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
              708123
(1 row)

Time: 2681.318 ms (00:02.681)

```

For a dataset of 12.5M:

- a precision of 8 is about 100% faster than `COUNT(DISTINCT ...)`
- a precision of 9 is about 60% faster than `COUNT(DISTINCT ...)`
- a precision 10 roughly matches the speed of `COUNT(DISTINCT ...)`

```sql

select count(user_uuid) from testapp_session;
  count
----------
 12500000
(1 row)

Time: 2093.473 ms (00:02.093)

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
      7134576
(1 row)

Time: 16944.364 ms (00:16.944)

select hll_approx_cardinality(user_uuid, 8) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             8494117
(1 row)

Time: 8599.141 ms (00:08.599)

select hll_approx_cardinality(user_uuid, 9) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             8154493
(1 row)

Time: 10642.760 ms (00:10.643)

select hll_approx_cardinality(user_uuid, 10) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             7768230
(1 row)

Time: 14647.500 ms (00:14.647)

select hll_approx_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             7447066
(1 row)

Time: 23068.642 ms (00:23.069)
```

The real advantage though is in combination with other properties:

E.g. this query is about 380% faster:

```sql

select
    date_trunc('day', created) as date_of_session,
    count(distinct user_uuid) as unique_users
from
    testapp_session
group by
    date_trunc('day', created);
    date_of_session     | unique_users
------------------------+--------------
 2023-04-06 00:00:00+00 |      1535903
 2023-04-07 00:00:00+00 |      1535558
 2023-04-08 00:00:00+00 |      1532815
 2023-04-09 00:00:00+00 |      1536498
 2023-04-10 00:00:00+00 |      1534280
 2023-04-11 00:00:00+00 |      1535005
 2023-04-12 00:00:00+00 |      1175794
 2023-04-13 00:00:00+00 |      1174328
(8 rows)

Time: 44780.758 ms (00:44.781)


select
    date_trunc('day', created) as date_of_session,
    hll_approx_cardinality(user_uuid, 9) as unique_users
from
    testapp_session
group by
    date_trunc('day', created);
    date_of_session     | unique_users
------------------------+--------------
 2023-04-06 00:00:00+00 |      1509097
 2023-04-07 00:00:00+00 |      1478254
 2023-04-08 00:00:00+00 |      1734274
 2023-04-09 00:00:00+00 |      1570385
 2023-04-10 00:00:00+00 |      1575785
 2023-04-11 00:00:00+00 |      1529300
 2023-04-12 00:00:00+00 |      1241961
 2023-04-13 00:00:00+00 |      1131402
(8 rows)

Time: 12430.238 ms (00:12.430)
```
