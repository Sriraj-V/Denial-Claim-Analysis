-- Grain: ONE ROW PER DENIAL (~2,750 rows). Fully denormalized fact for the BI
-- layer: claim + encounter + patient-agnostic provider/payer attributes + CARC
-- category + appeal economics + the recoverable-dollar estimate.
--
-- Recoverable-dollar definition (the core metric of the whole project):
--   recoverable_amount = billed_amount
--                        * appeal_win_rate         (prob. an appeal is paid)
--                        * category_multiplier     (fraction of billed recovered)
-- Dropping either factor makes the recommendations meaningless, so both are
-- applied here explicitly.
with denials as (
    select
        claim_id,
        denial_id,
        encounter_id,
        payer_id,
        provider_id,
        procedure_code,
        procedure_desc,
        procedure_category,
        diagnosis_code,
        billed_amount,
        allowed_amount,
        paid_amount,
        carc_code,
        rarc_code,
        claim_date,
        denial_date,
        appeal_status
    from {{ ref('int_claims_with_denials') }}
    where is_denied                              -- keep only denied claims
),

providers as (
    select provider_id, provider_name, specialty, region
    from {{ ref('stg_providers') }}
),

payers as (
    select payer_id, payer_name, payer_type
    from {{ ref('stg_payers') }}
),

carc as (
    select
        carc_code,
        carc_description,
        carc_category,
        is_high_appeal_value,
        appeal_win_rate,
        category_multiplier
    from {{ ref('int_denial_categories') }}
)

select
    -- surrogate key for the denial grain (drop-in dbt_utils behaviour)
    {{ generate_surrogate_key(['d.denial_id']) }} as denial_key,
    d.denial_id,
    d.claim_id,
    d.encounter_id,
    -- provider (1:1 on provider_id)
    d.provider_id,
    p.provider_name,
    p.specialty,
    p.region,
    -- payer (1:1 on payer_id)
    d.payer_id,
    pay.payer_name,
    pay.payer_type,
    -- clinical
    d.procedure_code,
    d.procedure_desc,
    d.procedure_category,
    d.diagnosis_code,
    -- CARC (1:1 on carc_code)
    d.carc_code,
    c.carc_description,
    c.carc_category,
    c.is_high_appeal_value,
    -- money
    d.billed_amount,
    d.allowed_amount,
    d.paid_amount,
    c.appeal_win_rate,
    c.category_multiplier,
    round(d.billed_amount * c.appeal_win_rate * c.category_multiplier, 2)
        as recoverable_amount,
    -- dates + appeal state
    d.claim_date,
    d.denial_date,
    d.rarc_code,
    d.appeal_status
from denials d
inner join providers p on d.provider_id = p.provider_id   -- grain: 1 denial : 1 provider
inner join payers    pay on d.payer_id  = pay.payer_id     -- grain: 1 denial : 1 payer
inner join carc      c   on d.carc_code = c.carc_code       -- grain: 1 denial : 1 carc
