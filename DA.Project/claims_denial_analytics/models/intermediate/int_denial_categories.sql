-- Grain: one row per CARC code.
-- Purpose: this is the single source of truth for denial APPEAL ECONOMICS.
-- We re-derive the category bucket from first principles and attach the
-- historical appeal win-rate and a recoverability multiplier. Keeping this
-- logic in dbt (not the seed) means operations can tune the assumptions in one
-- reviewable place.
--
-- Operational rationale:
--   technical / coding      -> the denial is usually a fixable defect on OUR
--                              side (missing auth, missing docs, wrong code) so
--                              appeals win often and recovery is high.
--   coverage                -> often a legitimate benefit/COB/deductible call;
--                              lower win rate, partial recovery.
--   medical_necessity       -> clinical judgement; hardest to overturn.
with carc as (
    select
        carc_code,
        carc_description,
        carc_category
    from {{ ref('stg_carc_codes') }}
)

select
    carc_code,
    carc_description,
    carc_category,
    -- high-appeal-value flag: is this denial category typically worth appealing?
    case
        when carc_category in ('technical', 'coding') then true
        else false
    end as is_high_appeal_value,
    -- historical appeal win rate (share of appeals that get paid)
    case carc_category
        when 'technical'         then 0.72
        when 'coding'            then 0.68
        when 'coverage'          then 0.30
        when 'medical_necessity' then 0.18
    end as appeal_win_rate,
    -- recoverability multiplier: fraction of billed we can realistically recover
    -- on a won appeal after write-downs / partial allowances
    case carc_category
        when 'technical'         then 1.00
        when 'coding'            then 0.95
        when 'coverage'          then 0.50
        when 'medical_necessity' then 0.35
    end as category_multiplier
from carc
