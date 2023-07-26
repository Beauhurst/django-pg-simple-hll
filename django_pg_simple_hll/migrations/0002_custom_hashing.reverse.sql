DROP AGGREGATE IF EXISTS hll_cardinality(anyelement);
DROP AGGREGATE IF EXISTS hll_cardinality(anyelement, int);
DROP AGGREGATE IF EXISTS hll_cardinality_from_hash(int, int);
DROP FUNCTION IF EXISTS hll_hash_and_bucket(int [], anyelement);
DROP FUNCTION IF EXISTS hll_hash_and_bucket(int [], anyelement, int);
DROP FUNCTION IF EXISTS hll_bucket(int [], int, int);
DROP FUNCTION IF EXISTS hll_hash(anyelement);
DROP FUNCTION IF EXISTS hll_bucket_combine(int [], int []);
DROP FUNCTION IF EXISTS hll_approximate(int [], int);


