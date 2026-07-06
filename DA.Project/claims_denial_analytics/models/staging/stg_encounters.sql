-- Grain: one row per encounter (clinical visit).
with source as (
    select * from {{ source('raw', 'raw_encounters') }}
)

select
    encounter_id,
    patient_id,
    provider_id,
    cast(encounter_date as date) as encounter_date,
    procedure_code,
    procedure_desc,
    procedure_category,
    diagnosis_code
from source
