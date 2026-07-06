-- Grain: one row per carc_category.
-- Sizes the recoverable dollar POOL, splitting the "worth appealing" categories
-- (technical + coding = is_high_appeal_value) from the rest so operations can
-- see where appeal effort actually pays back.
with denials as (
    select
        carc_category,
        is_high_appeal_value,
        appeal_win_rate,
        category_multiplier,
        billed_amount,
        recoverable_amount
    from {{ ref('fct_denials') }}
),

by_category as (
    select
        carc_category,
        is_high_appeal_value,
        count(*)                        as denial_count,
        sum(billed_amount)              as total_denied_billed,
        sum(recoverable_amount)         as total_recoverable,
        -- assumptions are constant within a category; min() just surfaces them
        min(appeal_win_rate)            as appeal_win_rate,
        min(category_multiplier)        as category_multiplier
    from denials
    group by 1, 2
)

select
    carc_category,
    is_high_appeal_value,
    denial_count,
    appeal_win_rate,
    category_multiplier,
    round(total_denied_billed, 2)   as total_denied_billed,
    round(total_recoverable, 2)     as total_recoverable,
    round(100.0 * total_recoverable
          / nullif(sum(total_recoverable) over (), 0), 1)
        as pct_of_total_recoverable
from by_category
order by total_recoverable desc
