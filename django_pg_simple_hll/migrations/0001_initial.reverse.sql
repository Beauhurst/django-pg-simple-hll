DROP AGGREGATE IF EXISTS hll_cardinality(anyelement, int);
DROP AGGREGATE IF EXISTS hll_cardinality(anyelement);
DROP FUNCTION IF EXISTS hll_bucket(int [], anyelement, int);
DROP FUNCTION IF EXISTS hll_bucket(int [], anyelement);
DROP FUNCTION IF EXISTS hll_bucket_combine(int [], int []);
DROP FUNCTION IF EXISTS hll_approximate(int [], int);
