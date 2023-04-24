-- The state transition function
-- it takes the current state, and the two input values
-- hll_agg_state is the current running state, made up of bucket keys and hashes
--  it is an array of n_buckets + 2
-- input is the element we are considering
-- hll_precision is the precision we are using for the approximation
--  it use used to calculate the number of buckets
CREATE OR REPLACE FUNCTION hll_bucket(
    hll_agg_state int [],
    input anyelement,
    hll_precision int
) RETURNS int []
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    -- eg. for 512 buckets, hll_precision is 9 because 2**9 -> 512
    n_buckets int := POW(2, hll_precision);
    -- transform the input into a text and hash it
    hashed_input int := HASHTEXT(input::text);
    -- keep all the significant bits, without the sign
    bucket_hash int := hashed_input & ~(1 << 31);
    -- bucket the hash into one of n buckets
    bucket_key int := hashed_input & (n_buckets - 1);
    -- length of current state array
    hll_agg_state_length int := ARRAY_LENGTH(hll_agg_state, 1);
    -- pre fetch the hash for occupying the corresponding bucket for the input
    -- we add 2 because
    --  1. postgres arrays are 1-indexed
    --  2. we have to account for an extra first element
    current_hash int := hll_agg_state[bucket_key + 2];
BEGIN
    -- we can only handle precision up to 26 or 67,108,864 buckets
    -- because array size is limited to 134,217,727 (or 2^27 - 1) in postgres
    IF hll_precision < 4 OR hll_precision > 26 THEN
        RAISE EXCEPTION 'invalid hll_precision: % - must be between 4 (16 buckets) and 26 (67,108,864 buckets) inclusive',
            hll_precision;
    END IF;
    -- postgres squeezes null elements in the array, we don't want that,
    -- so we add a first and last element to keep a fixed size
    IF hll_agg_state_length IS NULL OR hll_agg_state_length < (n_buckets + 2) THEN
        hll_agg_state[1] := n_buckets;
        hll_agg_state[n_buckets + 2] := n_buckets;
    END IF;

    IF current_hash IS NULL OR current_hash > bucket_hash THEN
        hll_agg_state[bucket_key + 2] := bucket_hash;
    END IF;
    RETURN hll_agg_state;
END $$;


-- sfunc with default precision of 9
CREATE OR REPLACE FUNCTION hll_bucket(
    hll_agg_state int [],
    input anyelement
) RETURNS int []
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
BEGIN
    RETURN hll_bucket(hll_agg_state, input, 9);
END $$;


-- The combinefunc
-- combines two states, taking the smaller hash from each corresponding index
-- we don't have any extra logic here for the two flanking extra elements at
-- the beginning and the end of the array because they should just be
-- copied as they are the same
CREATE OR REPLACE FUNCTION hll_bucket_combine(
    hll_left_agg_state int [],
    hll_right_agg_state int []
) RETURNS int []
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
SELECT ARRAY(
    SELECT
        LEAST(left_bucket_hash, right_bucket_hash)
    FROM
        UNNEST(hll_left_agg_state, hll_right_agg_state) AS AGG_STATE(left_bucket_hash, right_bucket_hash)
) $$;


-- The finalfunc
-- takes the hll_agg_state and approximates cardinality
CREATE OR REPLACE FUNCTION hll_approximate(
    hll_agg_state int []
) RETURNS int
LANGUAGE sql IMMUTABLE AS $$
WITH n_buckets AS (
    SELECT ARRAY_LENGTH(hll_agg_state, 1) - 2 AS n_buckets
),
hll_agg_state_table AS (
    SELECT
        31 - FLOOR(LOG(2, bucket_hash)) AS most_significant_bit,
        bucket_key
    FROM UNNEST(hll_agg_state) WITH ORDINALITY AS hll_agg_state_table(bucket_hash, bucket_key)
    WHERE bucket_hash IS NOT NULL -- ignore all null elements
        AND bucket_key != 1 -- ignore the first element of the array
        AND bucket_key != ARRAY_LENGTH(hll_agg_state, 1) -- ignore the last element of the array
),
alpha AS (
    -- alpha is a correction constant related to the number of buckets used
    -- defined as follows:
    SELECT
        CASE
            WHEN n_buckets.n_buckets = 16 THEN 0.673 -- for precision 4
            WHEN n_buckets.n_buckets = 32 THEN 0.697 -- for precision 5
            WHEN n_buckets.n_buckets = 64 THEN 0.709 -- for precision 6
            ELSE (0.7213 / (1 + 1.079 / n_buckets.n_buckets)) -- for precision >= 7
        END AS alpha
    FROM n_buckets
),
-- compute counts and aggregates
counted AS (
    SELECT
        MAX(n_buckets.n_buckets) - COUNT(hll_agg_state_table.most_significant_bit) AS n_zero_buckets,
        SUM(POW(2, -1 * hll_agg_state_table.most_significant_bit)) AS harmonic_mean
    FROM hll_agg_state_table, n_buckets
),
-- estimate
estimation AS (
    SELECT
        (
            (POW(n_buckets.n_buckets, 2) * alpha.alpha) / (counted.n_zero_buckets + counted.harmonic_mean)
        )::int AS approximated_cardinality
    FROM counted, n_buckets, alpha
)
-- correct for biases
SELECT
    CASE
        WHEN
            estimation.approximated_cardinality < 2.5 * n_buckets.n_buckets
            AND counted.n_zero_buckets > 0 THEN
        (
                alpha.alpha
                * (
                    n_buckets.n_buckets
                    * LOG(2, (n_buckets.n_buckets::numeric / counted.n_zero_buckets)::int
                )
            )
        )::int
        ELSE estimation.approximated_cardinality
    END AS approximated_cardinality_corrected
FROM estimation, alpha, n_buckets, counted $$;


-- aggregation with precision argument
CREATE OR REPLACE AGGREGATE hll_approx_cardinality(anyelement, int) (
    SFUNC = hll_bucket,
    STYPE = int [],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = SAFE
);


--  aggregation with default precision argument
CREATE OR REPLACE AGGREGATE hll_approx_cardinality(anyelement) (
    SFUNC = hll_bucket,
    STYPE = int [],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = SAFE
);
