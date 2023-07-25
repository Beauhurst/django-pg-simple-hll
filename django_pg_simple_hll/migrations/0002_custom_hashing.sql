-- drop some methods that we will overwrite
DROP AGGREGATE IF EXISTS hll_cardinality(anyelement, int);
DROP AGGREGATE IF EXISTS hll_cardinality(anyelement);
DROP FUNCTION IF EXISTS hll_bucket(int [], anyelement);
DROP FUNCTION IF EXISTS hll_bucket(int [], anyelement, int);


-- Default hashing function, it turns any input into an unsigned 32 bit integer
CREATE OR REPLACE FUNCTION hll_hash(input anyelement) RETURNS int
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
-- hash and unset the signing bit
SELECT HASHTEXT(input::text) & ~(1 << 31)
$$;

-- The state transition function
-- it takes the current state, and the hashed input values
-- hll_agg_state is the current running state, made up of bucket keys and hashes
--  it is an array of n_buckets
-- hashed_input is the int32 hash of any element we are considering
-- hll_precision is the precision we are using for the approximation
--  it use used to calculate the number of buckets
CREATE OR REPLACE FUNCTION hll_bucket(
    hll_agg_state int [],
    hashed_input int,
    hll_precision int
) RETURNS int []
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    -- eg. for 512 buckets, hll_precision is 9 because 2**9 -> 512
    n_buckets int := POW(2, hll_precision);
    -- bucket the hash into one of n buckets
    -- we add 1 because postgres arrays are 1-indexed
    bucket_key int := (hashed_input & (n_buckets - 1)) + 1;
    -- length of current state array
    hll_agg_state_length int := ARRAY_LENGTH(hll_agg_state, 1);
    -- pre fetch the hash for occupying the corresponding bucket for the input
    current_hash int := hll_agg_state[bucket_key];
BEGIN
    -- we can only handle precision up to 26 or 67,108,864 buckets
    -- because array size is limited to 134,217,727 (or 2^27 - 1) in postgres
    IF hll_precision < 4 OR hll_precision > 26 THEN
        RAISE EXCEPTION 'invalid hll_precision: % - must be between 4 (16 buckets) and 26 (67,108,864 buckets) inclusive',
            hll_precision;
    END IF;
    -- postgres squeezes uninitialised elements in an array,
    -- so we add a first and last NULL elements to keep a fixed size
    IF hll_agg_state_length IS NULL OR hll_agg_state_length < n_buckets THEN
        hll_agg_state[1] := COALESCE(hll_agg_state[1], NULL);
        hll_agg_state[n_buckets] := COALESCE(hll_agg_state[n_buckets], NULL);
    END IF;

    IF current_hash IS NULL OR current_hash > hashed_input THEN
        hll_agg_state[bucket_key] := hashed_input;
    END IF;
    RETURN hll_agg_state;
END $$;

-- hash and bucket in one function
CREATE OR REPLACE FUNCTION hll_hash_and_bucket(
    hll_agg_state int [],
    input anyelement,
    hll_precision int
) RETURNS int []
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
SELECT hll_bucket(hll_agg_state, hll_hash(input), hll_precision);
$$;

-- -- hash and bucket in one function with default precision of 9
CREATE OR REPLACE FUNCTION hll_hash_and_bucket(
    hll_agg_state int [],
    input anyelement
) RETURNS int []
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
BEGIN
    RETURN hll_hash_and_bucket(hll_agg_state, input, 9);
END $$;

-- aggregation with precision argument
CREATE OR REPLACE AGGREGATE hll_cardinality_from_hash(int, int) (
    SFUNC = hll_bucket,
    STYPE = int [],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = SAFE
);

-- aggregation with precision argument
CREATE OR REPLACE AGGREGATE hll_cardinality(anyelement, int) (
    SFUNC = hll_hash_and_bucket,
    STYPE = int [],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = SAFE
);


--  aggregation with default precision argument
CREATE OR REPLACE AGGREGATE hll_cardinality(anyelement) (
    SFUNC = hll_hash_and_bucket,
    STYPE = int [],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = SAFE
);
