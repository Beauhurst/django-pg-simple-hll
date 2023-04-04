-- The state transition function
-- it takes the current state, and the two input values
-- hll_agg_state is the current running state, made up of bucket keys and hashes
--  it is an array of n_buckets + 2
-- input is the element we are considering
-- hll_precision is the precision we are using for the approximation
--  it use used to calculate the number of buckets
create or replace function
hll_bucket(hll_agg_state int[], input anyelement, hll_precision int)
returns int[]
language plpgsql immutable strict parallel safe as
$$
declare
    n_buckets int := POW(2, hll_precision); -- eg.. for 512 buckets, hll_precision is 9 because 2**9 -> 512
    hashed_input int := hashtext(input::text); -- transform the input into a text and hash it
    bucket_hash int := hashed_input & ~(1 << 31); -- keep all the significant bits, without the sign
    bucket_key int := hashed_input & (n_buckets - 1); -- bucket the hash into one of n buckets
    -- pre fetch the hash for occupying the corresponding bucket for the input
    -- we add 2 because
    --  1. postgres arrays are 1-indexed
    --  2. we have to account for an extra first element
    current_hash int := hll_agg_state[bucket_key + 2];
begin
    -- we can only handle precision up to 11 or 2048 buckets
    -- because hashtext produces a hash of int size with 31 useable bits
    if hll_precision < 3 or hll_precision > 11 then
        raise exception 'invalid hll_precision: % - must be between 3 and 11 inclusive', hll_precision;
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
end
$$;


-- sfunc with default precision of 9
create or replace function
hll_bucket(hll_agg_state int[], input anyelement)
returns int[]
language plpgsql immutable strict parallel safe as
$$
begin
    return hll_bucket(hll_agg_state, input, 9);
end
$$;

-- The combinefunc
-- combines two states, taking the smaller hash from each corresponding index
-- we don't have any extra logic here for the two flanking extra elements at
-- the beginning and the end of the array because they should just be
-- copied as they are the same
create or replace function
hll_bucket_combine(hll_left_agg_state int[], hll_right_agg_state int[])
returns int[]
language sql immutable strict parallel safe as
$$
select array(
    select
        LEAST(left_bucket_hash, right_bucket_hash)
    from
        unnest(hll_left_agg_state, hll_right_agg_state) as state(left_bucket_hash, right_bucket_hash)
)
$$;

-- The finalfunc
-- takes the hll_agg_state and approximates cardinality
create or replace function
hll_approximate(hll_agg_state int[])
returns int
language sql immutable as
$$
with hll_agg_state_table as (
    select
        31 - FLOOR(LOG(2, bucket_hash)) as bucket_hash,
        bucket_key,
        (array_length(hll_agg_state, 1) - 2) as n_buckets
    from unnest(hll_agg_state) with ordinality as hll_agg_state_table(bucket_hash, bucket_key)
    where bucket_hash is not null -- ignore all null elements
        and bucket_key != 1 -- ignore the first element of the array
        and bucket_key != array_length(hll_agg_state, 1) -- ignore the last element of the array
),
-- compute counts and aggregates
counted as (
    select
        MAX(hll_agg_state_table.n_buckets) as n_buckets,
        MAX(hll_agg_state_table.n_buckets) - COUNT(hll_agg_state_table.bucket_hash) as n_zero_buckets,
        SUM(POW(2, -1 * hll_agg_state_table.bucket_hash)) as harmonic_mean
    from hll_agg_state_table
),
-- estimate
estimation as (
    select
        (
            (POW(counted.n_buckets, 2) * (0.7213 / (1 + 1.079 / counted.n_buckets))) /
            (counted.n_zero_buckets + counted.harmonic_mean)
        )::int as approximated_cardinality,
        counted.n_zero_buckets,
        counted.n_buckets
    from counted
)
-- correct for biases
select
    case
        when estimation.approximated_cardinality < 2.5 * estimation.n_buckets
            and estimation.n_zero_buckets > 0 then (
                (0.7213 / (1 + 1.079 / estimation.n_buckets))
                * (
                    estimation.n_buckets
                    * LOG(2, (estimation.n_buckets::numeric / estimation.n_zero_buckets)::int)
                )
            )::int
        else estimation.approximated_cardinality
    end as approximated_cardinality_corrected
from estimation
$$;

-- aggregation with precision argument
create or replace aggregate
hll_approx_cardinality(anyelement, int) (
    SFUNC = hll_bucket,
    STYPE = int[],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = safe
);

--  aggregation with default precision argument
create or replace aggregate
hll_approx_cardinality(anyelement) (
    SFUNC = hll_bucket,
    STYPE = int[],
    FINALFUNC = hll_approximate,
    COMBINEFUNC = hll_bucket_combine,
    INITCOND = '{}',
    PARALLEL = safe
);
