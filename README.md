# django_pg_simple_hll

Postgres-only HyperLogLog cardinality aggregation for the Django ORM.

Instead of counting the number of distinct users,

```python
%%time
Session.objects.aggregate(unique_users=Count("user_uuid", distinct=True))

CPU times: user 864 µs, sys: 2.46 ms, total: 3.32 ms
Wall time: 461 ms
{'unique_users': 140000}
```

you can approximate it,

```python
%%time
Session.objects.aggregate(approx_unique_users=HLLCardinality("user_uuid"))

CPU times: user 480 µs, sys: 1.54 ms, total: 2.02 ms
Wall time: 845 ms
{'approx_unique_users': 144594}
```

Or, instead of counting the number of distinct users per day,

```python
%%time
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(unique_users=Count("user_uuid", distinct=True))
        .values("unique_users", "date_of_session")
        .order_by("date_of_session")
)

CPU times: user 1.47 ms, sys: 3.16 ms, total: 4.64 ms
Wall time: 758 ms
[{'date_of_session': datetime.date(2023, 4, 28), 'unique_users': 20000},
 {'date_of_session': datetime.date(2023, 4, 29), 'unique_users': 40000},
 {'date_of_session': datetime.date(2023, 4, 30), 'unique_users': 60000},
 {'date_of_session': datetime.date(2023, 5, 1), 'unique_users': 80000},
 {'date_of_session': datetime.date(2023, 5, 2), 'unique_users': 100000},
 {'date_of_session': datetime.date(2023, 5, 3), 'unique_users': 120000},
 {'date_of_session': datetime.date(2023, 5, 4), 'unique_users': 140000}]
```

you can approximate it,

```python
%%time
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=HLLCardinality("user_uuid"))
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
)

CPU times: user 1.53 ms, sys: 3.57 ms, total: 5.1 ms
Wall time: 838 ms
[{'date_of_session': datetime.date(2023, 4, 28), 'approx_unique_users': 19322},
 {'date_of_session': datetime.date(2023, 4, 29), 'approx_unique_users': 39356},
 {'date_of_session': datetime.date(2023, 4, 30), 'approx_unique_users': 61202},
 {'date_of_session': datetime.date(2023, 5, 1), 'approx_unique_users': 80917},
 {'date_of_session': datetime.date(2023, 5, 2), 'approx_unique_users': 102914},
 {'date_of_session': datetime.date(2023, 5, 3), 'approx_unique_users': 125637},
 {'date_of_session': datetime.date(2023, 5, 4), 'approx_unique_users': 144594}]
```

The approximation is sometimes faster and uses less memory, particularly when faceting by other variables.

By default, it uses a precision of 9, which tends to have an error of about 5%. You can set a higher precision (up to 26) through a second parameter:

```python
%%time
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=HLLCardinality("user_uuid", 11))
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
)

CPU times: user 1.71 ms, sys: 3.82 ms, total: 5.53 ms
Wall time: 1.98 s
[{'date_of_session': datetime.date(2023, 4, 28), 'approx_unique_users': 20013},
 {'date_of_session': datetime.date(2023, 4, 29), 'approx_unique_users': 39616},
 {'date_of_session': datetime.date(2023, 4, 30), 'approx_unique_users': 59312},
 {'date_of_session': datetime.date(2023, 5, 1), 'approx_unique_users': 81278},
 {'date_of_session': datetime.date(2023, 5, 2), 'approx_unique_users': 101880},
 {'date_of_session': datetime.date(2023, 5, 3), 'approx_unique_users': 122343},
 {'date_of_session': datetime.date(2023, 5, 4), 'approx_unique_users': 141375}]
```

You can also set a lower precision (down to 4) for a faster, less accurate estimate.

```python
%%time
list(
    Session.objects
        .annotate(date_of_session=TruncDate("created"))
        .values("date_of_session")
        .annotate(approx_unique_users=HLLCardinality("user_uuid", 7))
        .values("approx_unique_users", "date_of_session")
        .order_by("date_of_session")
)

CPU times: user 1.3 ms, sys: 2.85 ms, total: 4.15 ms
Wall time: 547 ms
[{'date_of_session': datetime.date(2023, 4, 28), 'approx_unique_users': 19363},
 {'date_of_session': datetime.date(2023, 4, 29), 'approx_unique_users': 40627},
 {'date_of_session': datetime.date(2023, 4, 30), 'approx_unique_users': 63159},
 {'date_of_session': datetime.date(2023, 5, 1), 'approx_unique_users': 83371},
 {'date_of_session': datetime.date(2023, 5, 2), 'approx_unique_users': 96185},
 {'date_of_session': datetime.date(2023, 5, 3), 'approx_unique_users': 116565},
 {'date_of_session': datetime.date(2023, 5, 4), 'approx_unique_users': 143588}]
```

The aggregation is also available in SQL for analytics:

```sql

select
    date_trunc('day', created) as date_of_session,
    hll_cardinality(user_uuid, 11) as approx_unique_users
from
    testapp_session
group by
    date_trunc('day', created)
order by date_of_session;

    date_of_session     | approx_unique_users
------------------------+---------------------
 2023-04-28 00:00:00+00 |               20013
 2023-04-29 00:00:00+00 |               39616
 2023-04-30 00:00:00+00 |               59312
 2023-05-01 00:00:00+00 |               81278
 2023-05-02 00:00:00+00 |              101880
 2023-05-03 00:00:00+00 |              122343
 2023-05-04 00:00:00+00 |              141375
(7 rows)

Time: 2121.662 ms (00:02.122)
```

## How to use

Install the package:

```sh
pip install django-pg-simple-hll
```

Add it to your Django `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "django_pg_simple_hll",
    ...
]
```

Run migrations

```sh
django-admin migrate django_pg_simple_hll
```

## Should I use this?

If you can use [an optimised version](https://github.com/citusdata/postgresql-hll), you should use that. It will be faster - although I haven't done any benchmarks.

Use this if you can't install extensions on your database, such as on [Amazon RDS](https://aws.amazon.com/rds/).

## Notes on SQL implementation

This is a low-privilege implementation of [Hyperloglog](https://www.lix.polytechnique.fr/~fusy/Articles/FlFuGaMe07.pdf) approximate cardinality aggregation written in SQL and some [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html). Read about it [here](http://alejandro.giacometti.me/2023-03-30/hyperloglog-in-sql/),

## Notes on Performance

This is not a scientific test, but here is an example of performance running on an M1 MacBook Pro, running Postgres 14 in Docker.

For a dataset of 560k rows and 140k unique values a precision of 6 matches the speed of `COUNT(DISTINCT ...)`:

```sql

select count(user_uuid) from testapp_session;
 count
--------
 560000
(1 row)

Time: 115.919 ms

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
       140000
(1 row)

Time: 434.234 ms

select hll_cardinality(user_uuid, 6) as approx_unique_users from testapp_session;
  approx_unique_users
---------------------
              136260
(1 row)

Time: 409.562 ms

select hll_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
              141375
(1 row)

Time: 1309.422 ms (00:01.309)
```

For a dataset of 5.6M rows and 1.4M unique values:

- with a precision of 7, `hll_aggregate` runs in about 0.79x the speed of `COUNT(DISTINCT ...)`
- with a precision of 8, it roughly matches (0.94x)

```sql
select count(user_uuid) from testapp_session;
  count
---------
 5600000
(1 row)

Time: 6021.708 ms (00:06.022)

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
      1400000
(1 row)

Time: 5414.085 ms (00:05.414)

select hll_cardinality(user_uuid, 7) as approx_unique_users from
 approx_unique_users
---------------------
             1308235
(1 row)

Time: 4308.065 ms (00:04.308)

select hll_cardinality(user_uuid, 8) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             1407331
(1 row)

Time: 5083.205 ms (00:05.083)

select hll_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
             1390983
(1 row)

Time: 12468.054 ms (00:12.468)
```

For a dataset of 56M rows and 14M unique values:

- with a precision of 8, `hll_aggregate` runs in about 0.68x the speed of `COUNT(DISTINCT ...)`
- with a precision of 9, it runs in about 0.76x
- with a precision of 10, it runs in about 0.87x
- with a precision of 11, it runs in about 1.10x

```sql

select count(user_uuid) from testapp_session;
  count
----------
 56000000
(1 row)

Time: 86902.105 ms (01:26.902)93)

select count(distinct user_uuid) as unique_users from testapp_session;
 unique_users
--------------
     14000000
(1 row)

Time: 145953.595 ms (02:25.954)

select hll_cardinality(user_uuid, 8) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
            13469591
(1 row)

Time: 99688.330 ms (01:39.688)

select hll_cardinality(user_uuid, 9) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
            13028181
(1 row)

Time: 111210.513 ms (01:51.211)

select hll_cardinality(user_uuid, 10) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
            13147406
(1 row)

Time: 126465.312 ms (02:06.465)

hll_cardinality(user_uuid, 11) as approx_unique_users from testapp_session;
 approx_unique_users
---------------------
            13363203
(1 row)

Time: 160958.580 ms (02:40.959)
```

The real advantage though is in combination with other properties:

E.g. this query runs 0.37x quicker if using `hll_aggregate` than with `COUNT(DISTINCT ...)`:

```sql
select
  date_trunc('day', created) as date_of_session,
  count(distinct user_uuid) as unique_users
from testapp_session
group by
  date_trunc('day', created)
order by
  date_of_session;
    date_of_session     | unique_users
------------------------+--------------
 2023-04-28 00:00:00+00 |      2000000
 2023-04-29 00:00:00+00 |      4000000
 2023-04-30 00:00:00+00 |      6000000
 2023-05-01 00:00:00+00 |      8000000
 2023-05-02 00:00:00+00 |     10000000
 2023-05-03 00:00:00+00 |     12000000
 2023-05-04 00:00:00+00 |     14000000
(7 rows)

Time: 296766.361 ms (04:56.766)

select
  date_trunc('day', created) as date_of_session,
  hll_cardinality(user_uuid, 9) as unique_users
from
  testapp_session
group by
  date_trunc('day', created)
order by
  date_of_session;
    date_of_session     | unique_users
------------------------+--------------
 2023-04-28 00:00:00+00 |      1963972
 2023-04-29 00:00:00+00 |      4096876
 2023-04-30 00:00:00+00 |      5869339
 2023-05-01 00:00:00+00 |      7412843
 2023-05-02 00:00:00+00 |      9401010
 2023-05-03 00:00:00+00 |     11443836
 2023-05-04 00:00:00+00 |     13028181
(7 rows)

Time: 110217.665 ms (01:50.218)
```
