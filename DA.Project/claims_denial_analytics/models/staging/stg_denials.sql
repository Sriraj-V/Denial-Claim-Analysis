-- Grain: one row per denial (1:1 with a denied claim).
with source as (
    select * from {{ source('raw', 'raw_denials') }}
)

select
    denial_id,
    claim_id,
    carc_code,
    rarc_code,
    cast(denial_date as date) as denial_date,
    appeal_status
from source
