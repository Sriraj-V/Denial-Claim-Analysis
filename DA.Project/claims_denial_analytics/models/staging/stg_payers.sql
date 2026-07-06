-- Grain: one row per payer.
with source as (
    select * from {{ source('raw', 'dim_payers') }}
)

select
    payer_id,
    payer_name,
    payer_type
from source
