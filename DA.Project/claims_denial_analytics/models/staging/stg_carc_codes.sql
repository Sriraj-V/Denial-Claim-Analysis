-- Grain: one row per CARC (Claim Adjustment Reason Code).
-- Note: appeal_win_rate / category_multiplier are kept in the raw seed for
-- reference, but the canonical appeal economics are (re)derived in
-- int_denial_categories so the business logic lives in dbt, not the source.
with source as (
    select * from {{ source('raw', 'dim_carc_codes') }}
)

select
    carc_code,
    description                as carc_description,
    category                   as carc_category
from source
