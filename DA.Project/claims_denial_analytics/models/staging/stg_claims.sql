-- Grain: one row per claim (1:1 with encounter).
with source as (
    select * from {{ source('raw', 'raw_claims') }}
)

select
    claim_id,
    encounter_id,
    payer_id,
    cast(billed_amount  as decimal(12, 2)) as billed_amount,
    cast(allowed_amount as decimal(12, 2)) as allowed_amount,
    cast(paid_amount    as decimal(12, 2)) as paid_amount,
    status                                 as claim_status,
    cast(claim_date as date)               as claim_date
from source
