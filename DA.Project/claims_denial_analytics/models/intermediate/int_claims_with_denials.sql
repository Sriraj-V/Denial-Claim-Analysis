-- Grain: ONE ROW PER CLAIM (10,000 rows). This is enforced by construction:
--   - stg_claims is 1 row/claim
--   - stg_encounters is 1 row/encounter, joined 1:1 on encounter_id
--   - stg_denials is 1 row/claim (a claim has at most one denial) -> LEFT JOIN
--     cannot fan out.
-- Denial columns are NULL for non-denied claims. Never join stg_denials on
-- anything coarser than claim_id or this grain breaks.
with claims as (
    select
        claim_id,
        encounter_id,
        payer_id,
        billed_amount,
        allowed_amount,
        paid_amount,
        claim_status,
        claim_date
    from {{ ref('stg_claims') }}
),

encounters as (
    select
        encounter_id,
        patient_id,
        provider_id,
        procedure_code,
        procedure_desc,
        procedure_category,
        diagnosis_code,
        encounter_date
    from {{ ref('stg_encounters') }}
),

denials as (
    select
        denial_id,
        claim_id,
        carc_code,
        rarc_code,
        denial_date,
        appeal_status
    from {{ ref('stg_denials') }}
)

select
    -- claim
    c.claim_id,
    c.encounter_id,
    c.payer_id,
    c.billed_amount,
    c.allowed_amount,
    c.paid_amount,
    c.claim_status,
    c.claim_date,
    -- encounter (1:1 on encounter_id -> no fan-out)
    e.patient_id,
    e.provider_id,
    e.procedure_code,
    e.procedure_desc,
    e.procedure_category,
    e.diagnosis_code,
    e.encounter_date,
    -- denial (1:1 on claim_id, LEFT so paid/pending claims survive as NULLs)
    d.denial_id,
    d.carc_code,
    d.rarc_code,
    d.denial_date,
    d.appeal_status,
    (d.denial_id is not null) as is_denied
from claims c
inner join encounters e
    on c.encounter_id = e.encounter_id      -- grain: 1 claim : 1 encounter
left join denials d
    on c.claim_id = d.claim_id              -- grain: 1 claim : 0-or-1 denial
