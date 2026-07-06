-- Grain: one row per recommended fix (top 5).
-- Ranks (payer_type x specialty x carc_code) opportunities by
--   priority_score = total_recoverable_$  x  fix_probability
-- where fix_probability is the operational likelihood that a workflow change
-- actually prevents/recovers the denial (higher for technical/coding defects we
-- control, lower for coverage/medical-necessity calls we mostly do not).
with opportunities as (
    select
        payer_type,
        specialty,
        carc_code,
        carc_description,
        carc_category,
        count(*)                 as denial_count,
        sum(billed_amount)       as total_denied_billed,
        sum(recoverable_amount)  as total_recoverable
    from {{ ref('fct_denials') }}
    group by 1, 2, 3, 4, 5
),

scored as (
    select
        *,
        case carc_category
            when 'technical'         then 0.85
            when 'coding'            then 0.80
            when 'coverage'          then 0.35
            when 'medical_necessity' then 0.25
        end as fix_probability,
        case carc_category
            when 'technical'
                then 'Automate prior-auth / eligibility verification & documentation capture at intake'
            when 'coding'
                then 'Add pre-submission coding QA with dx-to-procedure edit checks'
            when 'coverage'
                then 'Verify benefits & coordination-of-benefits up front; appeal upside is limited'
            when 'medical_necessity'
                then 'Strengthen clinical documentation and align orders to payer medical-necessity policy'
        end as recommended_action
    from opportunities
),

ranked as (
    select
        *,
        round(total_recoverable * fix_probability, 2) as priority_score,
        row_number() over (order by total_recoverable * fix_probability desc)
            as priority_rank
    from scored
)

select
    priority_rank,
    payer_type,
    specialty,
    carc_code,
    carc_description,
    carc_category,
    denial_count,
    round(total_denied_billed, 2) as total_denied_billed,
    round(total_recoverable, 2)   as total_recoverable,
    fix_probability,
    priority_score,
    recommended_action
from ranked
where priority_rank <= 5
order by priority_rank
