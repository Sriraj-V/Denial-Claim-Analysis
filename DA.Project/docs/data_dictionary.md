# Data Dictionary — Healthcare Claims Denial Analysis

All data is **synthetic** (generated via `scripts/generate_data.py`) and contains
**zero PHI**. ~10,000 claims spanning **2024-01-01 → 2025-12-31** with weekday
seasonality and a mild upward volume trend.

## Warehouse

DuckDB file: `data/claims.duckdb` (also written as parquet in `data/parquet/`).

## Tables

### `raw_patients` — 1 row per patient
| column | type | notes |
|---|---|---|
| patient_id | varchar | **PK**, `PT######` |
| first_name / last_name | varchar | faker-generated |
| dob | date (ISO string) | age 1–95 |
| gender | varchar | `M` / `F` |
| zip | varchar | faker US zip |
| insurance_type | varchar | `commercial` / `medicare` / `medicaid` (62/23/15) |

### `raw_encounters` — 1 row per visit
| column | type | notes |
|---|---|---|
| encounter_id | varchar | **PK**, `ENC#######` |
| patient_id | varchar | FK → raw_patients |
| provider_id | varchar | FK → dim_providers |
| encounter_date | date | weekday-seasonal |
| procedure_code | varchar | CPT |
| procedure_desc | varchar | CPT description |
| procedure_category | varchar | office_visit / cardiology / surgery / imaging / lab / oncology / dermatology / gi / emergency |
| diagnosis_code | varchar | ICD-10 |

### `raw_claims` — 1 row per claim (1:1 with encounter)
| column | type | notes |
|---|---|---|
| claim_id | varchar | **PK**, `CLM#######` |
| encounter_id | varchar | FK → raw_encounters (unique) |
| payer_id | varchar | FK → dim_payers |
| billed_amount | double | provider charge |
| allowed_amount | double | payer fee-schedule allowed |
| paid_amount | double | = allowed if paid, else 0 |
| status | varchar | `paid` (~70%) / `denied` (~25%) / `pending` (~5%) |
| claim_date | date | = encounter_date |

### `raw_denials` — 1 row per denial (only for `status='denied'`)
| column | type | notes |
|---|---|---|
| denial_id | varchar | **PK**, `DNL#######` |
| claim_id | varchar | FK → raw_claims (unique) |
| carc_code | varchar | FK → dim_carc_codes (X12 CARC) |
| rarc_code | varchar | companion remark code |
| denial_date | date | 7–35 days after claim |
| appeal_status | varchar | not_appealed / appeal_pending / appeal_won / appeal_lost |

### `dim_carc_codes` — 1 row per CARC code (top-20 real X12 codes)
| column | type | notes |
|---|---|---|
| carc_code | varchar | **PK** |
| description | varchar | official-style text |
| category | varchar | `technical` / `coding` / `coverage` / `medical_necessity` |
| appeal_win_rate | double | historical win rate by category (see below) |
| category_multiplier | double | recoverability weight by category |

### `dim_providers` — 1 row per provider
`provider_id` (**PK**), provider_name, specialty (8 specialties), npi, region.

### `dim_payers` — 1 row per payer
`payer_id` (**PK**), payer_name, payer_type (`commercial` / `medicare` / `medicaid`).

## Appeal economics (by CARC category)

Used downstream to size recoverable dollars:
`recoverable = denied_billed_amount × appeal_win_rate × category_multiplier`

| category | appeal_win_rate | multiplier | rationale |
|---|---|---|---|
| technical | 0.72 | 1.00 | Missing auth/info/docs — usually fixable & winnable |
| coding | 0.68 | 0.95 | Dx/procedure mismatch, bundling — correctable |
| coverage | 0.30 | 0.50 | Deductible/COB/non-covered — largely legitimate |
| medical_necessity | 0.18 | 0.35 | Clinical judgment calls — hardest to overturn |

## Embedded denial patterns (what the analysis should find)

| # | Pattern | Dominant CARC | Category | Takeaway |
|---|---|---|---|---|
| P1 | **Cardiology × Commercial** | 197 (prior auth absent) | technical | High $ recoverable — fix front-end auth workflow |
| P2 | **Orthopedics × Medicare** | 16 / 252 (missing info/docs) | technical | Documentation checklist at submission |
| P3 | **Radiology × Medicaid** | 50 (medical necessity) | medical_necessity | Low recoverable — pursue policy/utilization mgmt, not appeals |
| P4 | **Primary Care × Commercial** | 11 (dx inconsistent w/ procedure) | coding | Coding QA before submit |

These four (payer × specialty × CARC) triples carry elevated denial rates
(33–44% vs a ~25% baseline), so both **count-based** and **dollar-based**
denial-density analyses will surface them.
