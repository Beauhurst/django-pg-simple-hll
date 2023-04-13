-- The state transition function
-- it takes the current state, and the two input values
-- hll_agg_state is the current running state, made up of bucket keys and hashes
--  it is an array of n_buckets + 2
-- input is the element we are considering
-- hll_precision is the precision we are using for the approximation
--  it use used to calculate the number of buckets
create or replace function hll_bucket(
    hll_agg_state int[],
    input anyelement,
    hll_precision int
) returns int[]
language plpgsql immutable strict parallel safe as $$
declare
    -- eg. for 512 buckets, hll_precision is 9 because 2**9 -> 512
    n_buckets int := POW(2, hll_precision);
    -- transform the input into a text and hash it
    hashed_input int := hashtext(input::text);
    -- keep all the significant bits, without the sign
    bucket_hash int := hashed_input & ~(1 << 31);
    -- bucket the hash into one of n buckets
    bucket_key int := hashed_input & (n_buckets - 1);
    -- pre fetch the hash for occupying the corresponding bucket for the input
    -- we add 2 because
    --  1. postgres arrays are 1-indexed
    --  2. we have to account for an extra first element
    current_hash int := hll_agg_state[bucket_key + 2];
begin
    -- we can only handle precision up to 11 or 2048 buckets
    -- because hashtext produces a hash of int size with 31 useable bits
    if hll_precision < 4 or hll_precision > 11 then
        raise exception 'invalid hll_precision: % - must be between 4 (16 buckets) and 11 (2048 buckets) inclusive',
            hll_precision;
    end if;
    -- postgres squeezes null elements in the array, we don't want that,
    -- so we add a first and last element to keep a fixed size
    if array_length(hll_agg_state, 1) < n_buckets + 2 then
        hll_agg_state[1] := n_buckets;
        hll_agg_state[n_buckets + 2] := n_buckets;
    end if;

    if current_hash is null or current_hash > bucket_hash then
        hll_agg_state[bucket_key + 2] := bucket_hash;
    end if;
    return hll_agg_state;
end $$;


-- sfunc with default precision of 9
create or replace function hll_bucket(
    hll_agg_state int[],
    input anyelement
) returns int[]
language plpgsql immutable strict parallel safe as $$
begin
    return hll_bucket(hll_agg_state, input, 9);
end $$;


-- The combinefunc
-- combines two states, taking the smaller hash from each corresponding index
-- we don't have any extra logic here for the two flanking extra elements at
-- the beginning and the end of the array because they should just be
-- copied as they are the same
create or replace function hll_bucket_combine(
    hll_left_agg_state int[],
    hll_right_agg_state int[]
) returns int[]
language sql immutable strict parallel safe as $$
select array(
    select
        LEAST(left_bucket_hash, right_bucket_hash)
    from
        unnest(hll_left_agg_state, hll_right_agg_state) as agg_state(left_bucket_hash, right_bucket_hash)
) $$;


-- The finalfunc
-- takes the hll_agg_state and approximates cardinality
create or replace function hll_approximate(
    hll_agg_state int[]
) returns int
language sql immutable as $$
with n_buckets as (
    select array_length(hll_agg_state, 1) - 2 as n_buckets
),
hll_agg_state_table as (
    select
        31 - FLOOR(LOG(2, bucket_hash)) as most_significant_bit,
        bucket_key
    from unnest(hll_agg_state) with ordinality as hll_agg_state_table(bucket_hash, bucket_key)
    where bucket_hash is not null -- ignore all null elements
        and bucket_key != 1 -- ignore the first element of the array
        and bucket_key != array_length(hll_agg_state, 1) -- ignore the last element of the array
),
alpha as (
    -- alpha is a correction constant related to the number of buckets used
    -- defined as follows:
    select
        case
            when n_buckets.n_buckets = 16 then 0.673 -- for precision 4
            when n_buckets.n_buckets = 32 then 0.697 -- for precision 5
            when n_buckets.n_buckets = 64 then 0.709 -- for precision 6
            else (0.7213 / (1 + 1.079 / n_buckets.n_buckets)) -- for precision >= 7
        end as alpha
    from n_buckets
),
-- compute counts and aggregates
counted as (
    select
        MAX(n_buckets.n_buckets) - COUNT(hll_agg_state_table.most_significant_bit) as n_zero_buckets,
        SUM(POW(2, -1 * hll_agg_state_table.most_significant_bit)) as harmonic_mean
    from hll_agg_state_table, n_buckets
),
-- estimate
estimation as (
    select
        (
            (POW(n_buckets.n_buckets, 2) * alpha.alpha) / (counted.n_zero_buckets + counted.harmonic_mean)
        )::int as approximated_cardinality
    from counted, n_buckets, alpha
)
-- correct for biases
select
    case
        when
            estimation.approximated_cardinality < 2.5 * n_buckets.n_buckets
            and counted.n_zero_buckets > 0 then
        (
                alpha.alpha
                * (
                    n_buckets.n_buckets
                    * LOG(2, (n_buckets.n_buckets::numeric / counted.n_zero_buckets)::int
                )
            )
        )::int
        else estimation.approximated_cardinality
    end as approximated_cardinality_corrected
from estimation, alpha, n_buckets, counted $$;


-- aggregation with precision argument
create or replace aggregate hll_approx_cardinality(anyelement, int) (
    SFUNC = hll_bucket,
    STYPE = int[],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = safe
);


--  aggregation with default precision argument
create or replace aggregate hll_approx_cardinality(anyelement) (
    SFUNC = hll_bucket,
    STYPE = int[],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = safe
);
