"""
Phase 1 — Synthetic Healthcare Claims + Denial Layer
=====================================================
Generates a realistic (but fully synthetic, zero-PHI) healthcare claims dataset
for a denial-pattern analysis portfolio project.

Outputs:
  - parquet files in data/parquet/
  - a DuckDB database at data/claims.duckdb with all tables loaded

Design goals:
  - ~10,000 claims across 2 years (2024-2025) with weekly seasonality
  - status mix: 70% paid / 25% denied / 5% pending
  - denial CARC codes drawn from the top-20 real X12 codes, weighted so that
    3-4 CLEAR patterns exist for the downstream analysis to surface:
        P1  Cardiology     x Commercial  -> CARC 197 (missing prior auth)      [technical, recoverable]
        P2  Orthopedics    x Medicare    -> CARC 16 / 252 (missing info/docs)  [technical, recoverable]
        P3  Radiology      x Medicaid    -> CARC 50 (medical necessity)        [low recoverable]
        P4  Primary Care   x Commercial  -> CARC 11 (dx inconsistent w/ proc)  [coding, recoverable]

Run:  python scripts/generate_data.py
"""

import os
import random
import numpy as np
import pandas as pd
from datetime import date, timedelta
from faker import Faker

# --------------------------------------------------------------------------- #
# Config / reproducibility
# --------------------------------------------------------------------------- #
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker("en_US")
Faker.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DATA_DIR = os.path.join(ROOT, "data")
PARQUET_DIR = os.path.join(DATA_DIR, "parquet")
os.makedirs(PARQUET_DIR, exist_ok=True)

N_PATIENTS = 3000
N_ENCOUNTERS = 10000          # one claim per encounter
START = date(2024, 1, 1)
END = date(2025, 12, 31)

# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #

# Top-20 real X12 Claim Adjustment Reason Codes, bucketed into the 4 operational
# categories used to size appeal win-rate. (technical/coding = high win rate;
# coverage/medical_necessity = low.)
CARC_CODES = [
    # code, description, category
    ("1",   "Deductible amount",                                              "coverage"),
    ("2",   "Coinsurance amount",                                             "coverage"),
    ("3",   "Co-payment amount",                                              "coverage"),
    ("11",  "The diagnosis is inconsistent with the procedure",              "coding"),
    ("16",  "Claim/service lacks information or has a submission/billing error","technical"),
    ("18",  "Exact duplicate claim/service",                                  "technical"),
    ("22",  "This care may be covered by another payer per coordination of benefits","coverage"),
    ("27",  "Expenses incurred after coverage terminated",                    "coverage"),
    ("29",  "The time limit for filing has expired",                          "technical"),
    ("45",  "Charge exceeds fee schedule/maximum allowable",                  "coverage"),
    ("50",  "Non-covered service - not deemed a medical necessity by payer",  "medical_necessity"),
    ("96",  "Non-covered charge(s)",                                          "coverage"),
    ("97",  "Benefit for this service is bundled into another service",       "coding"),
    ("109", "Claim not covered by this payer/contractor",                     "technical"),
    ("119", "Benefit maximum for this time period has been reached",          "coverage"),
    ("167", "This (these) diagnosis(es) is (are) not covered",                "medical_necessity"),
    ("197", "Precertification/authorization/notification absent",             "technical"),
    ("198", "Precertification/authorization exceeded",                        "technical"),
    ("204", "Service not covered under the patient's current benefit plan",   "coverage"),
    ("252", "An attachment/other documentation is required to adjudicate",    "technical"),
]

# Companion RARC codes (adds realism; loosely associated w/ the CARC)
RARC_POOL = ["N130", "N657", "M76", "N522", "MA04", "N30", "N479", "M51", "N286", "N56"]

# Category-level appeal economics used later by dbt. Kept here for the data
# dictionary; the marts recompute these from dim_carc_codes so the numbers live
# in one place.
CATEGORY_APPEAL = {
    "technical":         {"win_rate": 0.72, "multiplier": 1.00},
    "coding":            {"win_rate": 0.68, "multiplier": 0.95},
    "coverage":          {"win_rate": 0.30, "multiplier": 0.50},
    "medical_necessity": {"win_rate": 0.18, "multiplier": 0.35},
}

SPECIALTIES = [
    "Cardiology", "Orthopedics", "Radiology", "Primary Care",
    "Emergency Medicine", "Oncology", "Dermatology", "Gastroenterology",
]

# CPT procedure codes -> (description, procedure_category, base_billed)
CPT = {
    "99213": ("Office/outpatient visit, established, low",   "office_visit", 180),
    "99214": ("Office/outpatient visit, established, mod",   "office_visit", 260),
    "99204": ("Office/outpatient visit, new, moderate",      "office_visit", 320),
    "93000": ("Electrocardiogram, complete",                 "cardiology",   140),
    "93306": ("Echocardiography, transthoracic",             "cardiology",   950),
    "93458": ("Cardiac catheterization w/ angiography",      "cardiology",   4200),
    "27447": ("Total knee arthroplasty",                     "surgery",      28000),
    "29881": ("Knee arthroscopy w/ meniscectomy",            "surgery",      6500),
    "27130": ("Total hip arthroplasty",                      "surgery",      30000),
    "70553": ("MRI brain w/ & w/o contrast",                 "imaging",      2400),
    "72148": ("MRI lumbar spine w/o contrast",               "imaging",      1600),
    "74177": ("CT abdomen & pelvis w/ contrast",             "imaging",      1500),
    "80053": ("Comprehensive metabolic panel",               "lab",          90),
    "85025": ("Complete blood count w/ differential",        "lab",          55),
    "96413": ("Chemotherapy IV infusion, up to 1 hr",        "oncology",     3800),
    "11100": ("Biopsy of skin lesion",                       "dermatology",  260),
    "45378": ("Colonoscopy, diagnostic",                     "gi",           1900),
    "43239": ("Upper GI endoscopy w/ biopsy",                "gi",           1700),
    "99283": ("Emergency dept visit, moderate severity",     "emergency",    900),
    "99285": ("Emergency dept visit, high severity",         "emergency",    1800),
}

# Which CPTs each specialty tends to bill
SPECIALTY_CPT = {
    "Cardiology":         ["93000", "93306", "93458", "99214", "99204"],
    "Orthopedics":        ["27447", "29881", "27130", "99214", "72148"],
    "Radiology":          ["70553", "72148", "74177", "93306"],
    "Primary Care":       ["99213", "99214", "99204", "80053", "85025"],
    "Emergency Medicine": ["99283", "99285", "80053", "85025", "74177"],
    "Oncology":           ["96413", "80053", "85025", "99214"],
    "Dermatology":        ["11100", "99213", "99214"],
    "Gastroenterology":   ["45378", "43239", "99214", "99204"],
}

ICD10 = {
    "office_visit": ["I10", "E11.9", "Z00.00", "M54.5", "J06.9"],
    "cardiology":   ["I25.10", "I48.91", "I50.9", "I21.4"],
    "surgery":      ["M17.11", "M16.11", "M23.205", "S83.241A"],
    "imaging":      ["G43.909", "M54.16", "R10.9", "C34.90"],
    "lab":          ["E11.9", "E78.5", "D64.9", "N18.3"],
    "oncology":     ["C50.911", "C34.90", "C18.9", "Z51.11"],
    "dermatology":  ["L57.0", "D22.9", "C44.90"],
    "gi":           ["K21.9", "K57.30", "D12.6", "K50.90"],
    "emergency":    ["R07.9", "R10.9", "S06.0X0A", "J18.9"],
}

# --------------------------------------------------------------------------- #
# Dimension tables
# --------------------------------------------------------------------------- #
def build_dim_carc():
    rows = []
    for code, desc, cat in CARC_CODES:
        rows.append({
            "carc_code": code,
            "description": desc,
            "category": cat,
            "appeal_win_rate": CATEGORY_APPEAL[cat]["win_rate"],
            "category_multiplier": CATEGORY_APPEAL[cat]["multiplier"],
        })
    return pd.DataFrame(rows)


def build_dim_payers():
    payers = [
        ("PAY001", "BlueCross Commercial", "commercial"),
        ("PAY002", "Aetna Choice",         "commercial"),
        ("PAY003", "UnitedHealth PPO",     "commercial"),
        ("PAY004", "Cigna Open Access",    "commercial"),
        ("PAY005", "Medicare Part B",      "medicare"),
        ("PAY006", "State Medicaid",       "medicaid"),
    ]
    return pd.DataFrame(payers, columns=["payer_id", "payer_name", "payer_type"])


def build_dim_providers(n=40):
    rows = []
    regions = ["Northeast", "Midwest", "South", "West"]
    for i in range(1, n + 1):
        spec = SPECIALTIES[(i - 1) % len(SPECIALTIES)]
        rows.append({
            "provider_id": f"PRV{i:04d}",
            "provider_name": f"Dr. {fake.last_name()}",
            "specialty": spec,
            "npi": fake.numerify("##########"),
            "region": random.choice(regions),
        })
    return pd.DataFrame(rows)


def build_patients(n=N_PATIENTS):
    rows = []
    ins_types = ["commercial", "medicare", "medicaid"]
    ins_w = [0.62, 0.23, 0.15]
    for i in range(1, n + 1):
        g = random.choice(["M", "F"])
        rows.append({
            "patient_id": f"PT{i:06d}",
            "first_name": fake.first_name_male() if g == "M" else fake.first_name_female(),
            "last_name": fake.last_name(),
            "dob": fake.date_of_birth(minimum_age=1, maximum_age=95).isoformat(),
            "gender": g,
            "zip": fake.zipcode(),
            "insurance_type": np.random.choice(ins_types, p=ins_w),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Encounter date sampling with weekly seasonality + slight upward trend
# --------------------------------------------------------------------------- #
def sample_dates(n):
    days = [(START + timedelta(days=d)) for d in range((END - START).days + 1)]
    weights = []
    total_days = len(days)
    for idx, d in enumerate(days):
        # weekday seasonality: weekdays busy, weekends light
        wd = d.weekday()  # 0=Mon .. 6=Sun
        w = 1.0
        if wd == 5:      # Sat
            w = 0.35
        elif wd == 6:    # Sun
            w = 0.25
        elif wd == 0:    # Monday bump
            w = 1.25
        # mild upward volume trend across the 2 years (+30% end vs start)
        trend = 1.0 + 0.30 * (idx / total_days)
        # gentle year-end lull in the last two weeks of December
        if d.month == 12 and d.day >= 20:
            w *= 0.6
        weights.append(w * trend)
    weights = np.array(weights) / np.sum(weights)
    chosen = np.random.choice(len(days), size=n, p=weights)
    return [days[c] for c in chosen]


# --------------------------------------------------------------------------- #
# Denial CARC selection — this is where the PATTERNS are embedded
# --------------------------------------------------------------------------- #
BASE_DENIAL_WEIGHTS = {
    "1": 3, "2": 3, "3": 3, "11": 4, "16": 6, "18": 3, "22": 3, "27": 2,
    "29": 3, "45": 5, "50": 4, "96": 5, "97": 4, "109": 3, "119": 2,
    "167": 3, "197": 5, "198": 3, "204": 4, "252": 4,
}


def denial_carc_for(specialty, payer_type, proc_category):
    """Return a CARC code, biasing toward the 4 designed patterns."""
    w = dict(BASE_DENIAL_WEIGHTS)

    # P1: Cardiology x Commercial -> prior-auth absent (197)
    if specialty == "Cardiology" and payer_type == "commercial":
        w["197"] += 55
        w["198"] += 15

    # P2: Orthopedics x Medicare -> missing info / documentation (16, 252)
    if specialty == "Orthopedics" and payer_type == "medicare":
        w["16"] += 40
        w["252"] += 30

    # P3: Radiology x Medicaid -> medical necessity (50)
    if specialty == "Radiology" and payer_type == "medicaid":
        w["50"] += 55
        w["167"] += 15

    # P4: Primary Care x Commercial -> dx inconsistent with procedure (11)
    if specialty == "Primary Care" and payer_type == "commercial":
        w["11"] += 45
        w["97"] += 15

    # light realism: high-cost surgery draws more auth denials
    if proc_category == "surgery":
        w["197"] += 8
        w["252"] += 6

    codes = list(w.keys())
    probs = np.array([w[c] for c in codes], dtype=float)
    probs /= probs.sum()
    return np.random.choice(codes, p=probs)


# --------------------------------------------------------------------------- #
# Build encounters + claims + denials
# --------------------------------------------------------------------------- #
def build_transactions(patients, providers, payers):
    prov_by_spec = {s: providers[providers.specialty == s].provider_id.tolist()
                    for s in SPECIALTIES}
    payer_by_type = {t: payers[payers.payer_type == t].payer_id.tolist()
                     for t in ["commercial", "medicare", "medicaid"]}

    pat_ins = dict(zip(patients.patient_id, patients.insurance_type))
    pat_ids = patients.patient_id.tolist()
    dates = sample_dates(N_ENCOUNTERS)

    enc_rows, claim_rows, denial_rows = [], [], []

    for i in range(N_ENCOUNTERS):
        enc_id = f"ENC{i+1:07d}"
        claim_id = f"CLM{i+1:07d}"
        pid = random.choice(pat_ids)
        ins = pat_ins[pid]

        specialty = random.choice(SPECIALTIES)
        provider_id = random.choice(prov_by_spec[specialty])
        # payer usually matches patient insurance type
        ptype = ins if random.random() < 0.9 else random.choice(["commercial", "medicare", "medicaid"])
        payer_id = random.choice(payer_by_type[ptype])

        cpt = random.choice(SPECIALTY_CPT[specialty])
        desc, proc_cat, base = CPT[cpt]
        icd = random.choice(ICD10[proc_cat])
        dt = dates[i]

        # billed amount w/ noise
        billed = round(base * np.random.uniform(0.85, 1.35), 2)
        # allowed schedule differs by payer type
        allow_rate = {"commercial": 0.68, "medicare": 0.55, "medicaid": 0.48}[ptype]
        allowed = round(billed * allow_rate * np.random.uniform(0.9, 1.05), 2)

        enc_rows.append({
            "encounter_id": enc_id,
            "patient_id": pid,
            "provider_id": provider_id,
            "encounter_date": dt.isoformat(),
            "procedure_code": cpt,
            "procedure_desc": desc,
            "procedure_category": proc_cat,
            "diagnosis_code": icd,
        })

        # ---- status: 70 paid / 25 denied / 5 pending, with pattern lift ----
        p_deny = 0.25
        if specialty == "Cardiology" and ptype == "commercial":
            p_deny = 0.42
        elif specialty == "Orthopedics" and ptype == "medicare":
            p_deny = 0.40
        elif specialty == "Radiology" and ptype == "medicaid":
            p_deny = 0.44
        elif specialty == "Primary Care" and ptype == "commercial":
            p_deny = 0.33
        p_pending = 0.05
        p_paid = 1 - p_deny - p_pending
        status = np.random.choice(["paid", "denied", "pending"],
                                  p=[p_paid, p_deny, p_pending])

        if status == "paid":
            paid = allowed
        elif status == "pending":
            paid = 0.0
        else:
            paid = 0.0

        claim_rows.append({
            "claim_id": claim_id,
            "encounter_id": enc_id,
            "payer_id": payer_id,
            "billed_amount": billed,
            "allowed_amount": allowed,
            "paid_amount": round(paid, 2),
            "status": status,
            "claim_date": dt.isoformat(),
        })

        if status == "denied":
            carc = denial_carc_for(specialty, ptype, proc_cat)
            denial_dt = dt + timedelta(days=int(np.random.uniform(7, 35)))
            appeal_status = np.random.choice(
                ["not_appealed", "appeal_pending", "appeal_won", "appeal_lost"],
                p=[0.55, 0.15, 0.18, 0.12],
            )
            denial_rows.append({
                "denial_id": f"DNL{len(denial_rows)+1:07d}",
                "claim_id": claim_id,
                "carc_code": carc,
                "rarc_code": random.choice(RARC_POOL),
                "denial_date": denial_dt.isoformat(),
                "appeal_status": appeal_status,
            })

    return (pd.DataFrame(enc_rows),
            pd.DataFrame(claim_rows),
            pd.DataFrame(denial_rows))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    print("Building dimensions...")
    dim_carc = build_dim_carc()
    dim_payers = build_dim_payers()
    dim_providers = build_dim_providers()
    patients = build_patients()

    print("Building encounters / claims / denials...")
    encounters, claims, denials = build_transactions(patients, dim_providers, dim_payers)

    tables = {
        "raw_patients": patients,
        "raw_encounters": encounters,
        "raw_claims": claims,
        "raw_denials": denials,
        "dim_carc_codes": dim_carc,
        "dim_providers": dim_providers,
        "dim_payers": dim_payers,
    }

    # ---- write parquet ----
    for name, df in tables.items():
        path = os.path.join(PARQUET_DIR, f"{name}.parquet")
        df.to_parquet(path, index=False)
        print(f"  parquet -> {name:16s} rows={len(df):6d}")

    # ---- quick sanity on status mix ----
    mix = claims.status.value_counts(normalize=True).round(3).to_dict()
    print(f"\nStatus mix: {mix}")
    print(f"Denials: {len(denials)}  ({len(denials)/len(claims):.1%} of claims)")

    print("\nDone. Now run: python scripts/load_duckdb.py")


if __name__ == "__main__":
    main()
