-- Grain: one row per patient. Cleaned + cast from raw_patients.
with source as (
    select * from {{ source('raw', 'raw_patients') }}
)

select
    patient_id,
    first_name,
    last_name,
    cast(dob as date)          as date_of_birth,
    gender,
    zip                        as zip_code,
    insurance_type
from source
