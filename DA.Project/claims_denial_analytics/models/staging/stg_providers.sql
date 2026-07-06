-- Grain: one row per provider.
with source as (
    select * from {{ source('raw', 'dim_providers') }}
)

select
    provider_id,
    provider_name,
    specialty,
    npi,
    region
from source
