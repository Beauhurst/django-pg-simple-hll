drop aggregate if exists hll_approx_cardinality(anyelement, int);
drop aggregate if exists hll_approx_cardinality(anyelement);
drop function if exists hll_bucket(int[], anyelement, int);
drop function if exists hll_bucket(int[], anyelement);
drop function if exists hll_bucket_combine(int[], int[]);
drop function if exists hll_approximate(int[], int);
