# Healthcare Claims Denial Pattern Analysis

> At payers and provider RCM shops, claim denials quietly eat recoverable
> revenue — and teams react to *individual* denials instead of denial
> **patterns**. This project clusters denials by root cause (payer × specialty ×
> procedure × CARC reason code), sizes each cluster in **dollars recoverable**,
> and recommends the top workflow fixes ranked by ROI. Data is synthetic (zero
> PHI); the analytical pattern is production-ready.

## What's here

```
DA.Project/
├── scripts/
│   ├── generate_data.py      # synthetic patients/encounters/claims + denial layer
│   └── load_duckdb.py         # parquet -> DuckDB warehouse
├── data/                      # (gitignored) claims.duckdb + parquet, produced by scripts
├── docs/
│   └── data_dictionary.md     # schema, appeal economics, embedded patterns
└── claims_denial_analytics/   # dbt project (staging -> intermediate -> marts)
    ├── dbt_project.yml
    ├── profiles.yml
    ├── packages.yml
    ├── macros/generate_surrogate_key.sql
    └── models/
        ├── staging/           # stg_*  (views, 1:1 with raw, cleaned/cast)
        ├── intermediate/      # int_*  (business logic: claim+denial join, appeal economics)
        └── marts/             # fct_denials, agg_denial_patterns,
                               # agg_recoverable_dollars, mart_workflow_recommendations
```

## The data (Phase 1)

~10,000 synthetic claims over **2024–2025** with weekday seasonality, status
mix **70% paid / 25% denied / 5% pending**, and denial CARC codes drawn from the
top-20 real X12 [Claim Adjustment Reason Codes](https://x12.org/codes/claim-adjustment-reason-codes).

Four denial **patterns** are deliberately embedded so the analysis has real
signal to surface (denial rates 33–44% vs a ~25% baseline in these segments):

| Pattern | Segment | Dominant CARC | Category | Story |
|---|---|---|---|---|
| P1 | Cardiology × Commercial | 197 – prior auth absent | technical | Highest denial *count*; fix front-end auth |
| P2 | Orthopedics × Medicare | 16 / 252 – missing info/docs | technical | Highest recoverable *$* (big-ticket surgery); documentation checklist |
| P3 | Radiology × Medicaid | 50 – medical necessity | medical_necessity | Low recoverable; pursue policy, not appeals |
| P4 | Primary Care × Commercial | 11 – dx inconsistent w/ procedure | coding | Pre-submission coding QA |

See [`docs/data_dictionary.md`](docs/data_dictionary.md) for full schema + the
appeal-economics assumptions.

## Key metric — recoverable dollars

```
recoverable_amount = billed_amount
                     × appeal_win_rate      (prob. an appeal is paid, by CARC category)
                     × category_multiplier  (fraction of billed realistically recovered)
```

| CARC category | appeal_win_rate | multiplier | why |
|---|---|---|---|
| technical | 0.72 | 1.00 | missing auth/info/docs — fixable & winnable |
| coding | 0.68 | 0.95 | dx/procedure mismatch, bundling — correctable |
| coverage | 0.30 | 0.50 | deductible/COB/non-covered — mostly legitimate |
| medical_necessity | 0.18 | 0.35 | clinical judgement — hardest to overturn |

Both factors are applied in `fct_denials`; the logic lives in
`int_denial_categories` so the assumptions are tunable in one place. In the
generated data **technical + coding denials hold ~87% of the recoverable pool** —
i.e. the money is in fixable defects, not in fighting medical-necessity calls.

## How to run

### 0. Install
```bash
pip install -r requirements.txt
```

### 1. Generate data + build the warehouse
```bash
python scripts/generate_data.py     # writes data/parquet/*.parquet
python scripts/load_duckdb.py        # writes data/claims.duckdb
```

### 2. Build + test the dbt project
```bash
cd claims_denial_analytics
dbt deps                             # installs dbt_utils (needs network)
dbt run       --profiles-dir .       # builds 13 models
dbt test      --profiles-dir .       # 52 data tests
dbt docs generate --profiles-dir .   # catalog + lineage
dbt docs serve    --profiles-dir .   # browse the docs site
```

> `packages.yml` pins `dbt_utils`. A local drop-in `generate_surrogate_key`
> macro is included, so the project also builds offline if `dbt deps` can't reach
> the package hub.

## The output — `mart_workflow_recommendations`

Top-5 fix opportunities ranked by `priority_score = recoverable_$ × fix_probability`,
each with a concrete recommended workflow change. Example from a build:

| rank | segment | CARC | recoverable $ | recommended action |
|---|---|---|---|---|
| 1 | Medicare × Orthopedics | 252 (docs) | ~$352k | Automate documentation capture at intake |
| 2 | Medicare × Orthopedics | 16 (missing info) | ~$349k | Same — front-end completeness checks |
| 5 | Commercial × Cardiology | 197 (auth) | ~$121k (115 denials) | Automate prior-auth verification |

Note the tension the analysis exposes: Orthopedics wins on **dollars** (big-ticket
surgery), while Cardiology 197 wins on **denial count** (115) — different fixes,
different owners.

## Verification

Every build is checked for: PK uniqueness/not-null and FK relationships on all
staging models; `accepted_values` on categoricals; **grain integrity**
(`fct_denials` rows = denial rows, `int_claims_with_denials` = 10,000 with no
join fan-out); and that `recoverable_amount` exactly equals
`billed × win_rate × multiplier` for every row. `dbt test` → 52 passing.

## Stack

DuckDB (warehouse) · dbt-core + dbt-duckdb (transformation) · Python/pandas/faker
(synthetic data) · parquet (interchange).
