-- Grain: one row per (payer_type x specialty x carc_category).
-- Denial density by count AND by dollars, plus the denial rate for the segment.
-- The denial rate needs a claims denominator, so we build claim counts per
-- (payer_type x specialty) from the full claim population and join them on.
with claims_base as (
    -- 1 row per claim, with payer_type + specialty attached (no fan-out:
    -- payer/provider joins are 1:1)
    select
        pay.payer_type,
        pr.specialty,
        cwd.claim_status
    from {{ ref('int_claims_with_denials') }} cwd
    inner join {{ ref('stg_payers') }}    pay on cwd.payer_id    = pay.payer_id
    inner join {{ ref('stg_providers') }} pr  on cwd.provider_id = pr.provider_id
),

segment_claims as (
    -- denominator: total & denied claims per payer_type x specialty
    select
        payer_type,
        specialty,
        count(*)                                                 as total_claims,
        sum(case when claim_status = 'denied' then 1 else 0 end) as denied_claims
    from claims_base
    group by 1, 2
),

denial_agg as (
    -- numerator detail: denial counts & dollars per payer_type x specialty x category
    select
        payer_type,
        specialty,
        carc_category,
        count(*)                     as denial_count,
        count(distinct carc_code)    as distinct_carc_codes,
        sum(billed_amount)           as total_denied_billed,
        sum(recoverable_amount)      as total_recoverable
    from {{ ref('fct_denials') }}
    group by 1, 2, 3
)

select
    {{ generate_surrogate_key(['da.payer_type', 'da.specialty', 'da.carc_category']) }}
        as pattern_key,
    da.payer_type,
    da.specialty,
    da.carc_category,
    da.denial_count,
    da.distinct_carc_codes,
    sc.total_claims,
    sc.denied_claims,
    round(100.0 * sc.denied_claims / nullif(sc.total_claims, 0), 1)
        as segment_denial_rate_pct,
    round(da.total_denied_billed, 2)  as total_denied_billed,
    round(da.total_recoverable, 2)    as total_recoverable,
    round(da.total_recoverable / nullif(da.denial_count, 0), 2)
        as recoverable_per_denial
from denial_agg da
inner join segment_claims sc
    on da.payer_type = sc.payer_type
   and da.specialty  = sc.specialty     -- 1:1 back to the segment denominator
