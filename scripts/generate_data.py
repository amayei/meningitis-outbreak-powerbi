"""
Generate a FICTITIOUS meningitis surveillance and outbreak-prediction dataset
for Sierra Leone, shaped like a KoboToolbox export (main form + repeat group).

All numbers are simulated. They are not real surveillance data.

Outputs (in ../data):
  meningitis_surveillance_kobo.xlsx   all tables, one sheet each
  csv/*.csv                           the same tables as CSV (for Power BI Web connector)

Run:  python generate_data.py
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, time
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
rng = np.random.default_rng(SEED)
OUT = Path(__file__).resolve().parent.parent / "data"
(OUT / "csv").mkdir(parents=True, exist_ok=True)

START = date(2023, 1, 2)    # Monday of ISO 2023-W01
END = date(2026, 10, 5)     # Monday of ISO 2026-W41 (last complete week)
FORECAST_WEEKS = 16

ALERT_PER_100K = 3.0        # WHO weekly alert threshold (district > 30,000 pop.)
EPIDEMIC_PER_100K = 10.0    # WHO weekly epidemic threshold

# district, region, lat, lon, population (2023), baseline risk multiplier, dryness (0-1, north = drier)
DISTRICTS = [
    ("Kailahun", "Eastern", 8.28, -10.57, 551_000, 0.9, 0.35),
    ("Kenema", "Eastern", 7.88, -11.19, 703_000, 0.9, 0.30),
    ("Kono", "Eastern", 8.65, -10.97, 548_000, 1.1, 0.45),
    ("Bombali", "Northern", 9.20, -12.15, 452_000, 1.5, 0.70),
    ("Falaba", "Northern", 9.85, -11.35, 221_000, 2.2, 0.95),
    ("Koinadugu", "Northern", 9.50, -11.40, 254_000, 2.0, 0.90),
    ("Tonkolili", "Northern", 8.75, -11.80, 601_000, 1.3, 0.60),
    ("Kambia", "North West", 9.12, -12.92, 398_000, 1.6, 0.75),
    ("Karene", "North West", 9.30, -12.45, 352_000, 1.6, 0.80),
    ("Port Loko", "North West", 8.77, -12.78, 648_000, 1.3, 0.60),
    ("Bo", "Southern", 7.95, -11.75, 652_000, 0.9, 0.30),
    ("Bonthe", "Southern", 7.53, -12.50, 219_000, 0.8, 0.15),
    ("Moyamba", "Southern", 8.16, -12.43, 351_000, 0.8, 0.25),
    ("Pujehun", "Southern", 7.35, -11.72, 401_000, 0.7, 0.15),
    ("Western Area Rural", "Western", 8.35, -13.10, 552_000, 1.0, 0.20),
    ("Western Area Urban", "Western", 8.47, -13.23, 1_221_000, 1.0, 0.20),
]
MENFIVE_DISTRICTS = {"Falaba", "Koinadugu", "Bombali", "Kambia", "Karene", "Tonkolili", "Port Loko"}
MENFIVE_CAMPAIGN = date(2025, 11, 10)
ANNUAL_POP_GROWTH = 0.021

# Severe Harmattan years push dust up and humidity down
YEAR_DUST_SHIFT = {2023: 0.00, 2024: 0.25, 2025: -0.05, 2026: 0.10, 2027: 0.0}

PATHOGENS_OUTBREAK = ["NmW", "NmC", "NmX"]
PATHOGEN_SPORADIC = (["S. pneumoniae", "NmW", "NmC", "Hib", "NmX", "NmA"],
                     [0.42, 0.22, 0.12, 0.12, 0.08, 0.04])


def mondays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def climate(week_start: date, dryness: float) -> dict:
    """Weekly climate for a district. Dry season Nov-Apr, Harmattan peak mid-Jan."""
    doy = week_start.timetuple().tm_yday
    # Harmattan intensity: Gaussian bump centred on day 20 (wraps around new year)
    dist = min(abs(doy - 20), 365 - abs(doy - 20))
    harm = np.exp(-(dist / 45.0) ** 2)
    # Rainy season intensity: peak around early August (day 215)
    rain_int = np.exp(-((doy - 215) / 55.0) ** 2)
    year_shift = YEAR_DUST_SHIFT.get(week_start.year if doy > 200 else week_start.year, 0)
    if doy > 300:
        year_shift = YEAR_DUST_SHIFT.get(week_start.year + 1, 0)

    dust = 0.15 + harm * (0.55 + 0.6 * dryness + year_shift) + rng.normal(0, 0.07)
    humidity = 86 - harm * (30 + 28 * dryness + 20 * year_shift) - (1 - rain_int) * 6 + rng.normal(0, 3.5)
    tmax = 29.5 + harm * 2.0 + (1 - rain_int) * 3.0 * (0.6 + dryness) + rng.normal(0, 0.8)
    if 60 <= doy <= 120:  # hot pre-rains period
        tmax += 1.5 * dryness
    rain = max(0.0, rain_int * (95 + 60 * (1 - dryness)) + rng.gamma(1.2, 6) * (rain_int > 0.15) - 3)
    return dict(
        dust_aod_index=round(float(np.clip(dust, 0.05, 2.0)), 2),
        relative_humidity_pct=round(float(np.clip(humidity, 12, 98)), 1),
        max_temperature_c=round(float(tmax), 1),
        rainfall_mm=round(float(rain), 1),
        harmattan_intensity=float(harm),
    )


def outbreak_curve(length: int, peak: float) -> np.ndarray:
    x = np.arange(length)
    k = 2.6
    shape = (x + 1) ** (k - 1) * np.exp(-(x + 1) / (length / (k + 0.6)))
    return peak * shape / shape.max()


# ---------------------------------------------------------------------------
# 1. District-week skeleton, climate and outbreak process
# ---------------------------------------------------------------------------
weeks = mondays(START, END)
fc_weeks = mondays(END + timedelta(days=7), END + timedelta(days=7 * FORECAST_WEEKS))

rows = []
for (name, region, lat, lon, pop0, riskf, dryness) in DISTRICTS:
    active_curve, curve_pos, curve_pathogen = None, 0, None
    season_had_outbreak = {}
    for ws in weeks:
        iso = ws.isocalendar()
        years_since = (ws - START).days / 365.25
        pop = int(pop0 * (1 + ANNUAL_POP_GROWTH) ** years_since)
        c = climate(ws, dryness)
        month = ws.month
        dry_season = month in (11, 12, 1, 2, 3, 4)
        season_key = ws.year + (1 if month >= 11 else 0)

        menafrivac = round(float(np.clip(78 + 6 * (1 - dryness) + rng.normal(0, 2.5) - 2 * years_since, 55, 95)), 1)
        menfive = 0.0
        if name in MENFIVE_DISTRICTS and ws >= MENFIVE_CAMPAIGN:
            menfive = round(float(np.clip(84 + rng.normal(0, 3), 70, 95)), 1)

        # Outbreak hazard
        if active_curve is None and dry_season and not season_had_outbreak.get(season_key):
            z = (-6.4 + 3.2 * c["dust_aod_index"] - 0.035 * (c["relative_humidity_pct"] - 60)
                 + np.log(riskf) * 1.6 - 0.04 * (menfive) - 0.02 * (menafrivac - 75))
            if rng.random() < sigmoid(z):
                length = int(rng.integers(6, 12))
                peak = float(rng.uniform(4, 22) * riskf ** 0.8 * (0.35 if menfive > 0 else 1))
                active_curve, curve_pos = outbreak_curve(length, peak), 0
                curve_pathogen = rng.choice(PATHOGENS_OUTBREAK, p=[0.6, 0.3, 0.1])
                season_had_outbreak[season_key] = True

        base_rate = 0.18 + 0.55 * c["harmattan_intensity"] * riskf * (1 - 0.5 * (menfive > 0))
        outbreak_rate = 0.0
        if active_curve is not None:
            outbreak_rate = active_curve[curve_pos]
            curve_pos += 1
            if curve_pos >= len(active_curve):
                active_curve = None

        expected = (base_rate + outbreak_rate) * pop / 1e5
        n_cases = int(rng.poisson(expected))
        rows.append(dict(
            district=name, region=region, population=pop,
            epi_year=iso[0], epi_week=iso[1], week_start_date=ws, week_end_date=ws + timedelta(days=6),
            dry_season="yes" if dry_season else "no",
            **{k: v for k, v in c.items() if k != "harmattan_intensity"},
            menafrivac_coverage_pct=menafrivac, menfive_coverage_pct=menfive,
            _n_cases=n_cases, _outbreak_pathogen=curve_pathogen if outbreak_rate > 0 else None,
            _in_outbreak=outbreak_rate > 0,
        ))

weekly = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# 2. Case line list (the Kobo repeat group)
# ---------------------------------------------------------------------------
AGE_GROUP_BINS = [(0, 1, "<1"), (1, 5, "1-4"), (5, 15, "5-14"), (15, 30, "15-29"), (30, 200, "30+")]
FACILITY_TYPES = (["Hospital", "CHC", "CHP", "MCHP"], [0.45, 0.30, 0.15, 0.10])


def draw_age(pathogen: str | None) -> float:
    if pathogen in ("S. pneumoniae", "Hib") and rng.random() < 0.45:
        return round(float(rng.uniform(0.1, 4.9)), 1)
    if pathogen and pathogen.startswith("Nm"):
        return round(float(np.clip(rng.gamma(3.2, 4.2), 0.3, 70)), 1)
    return round(float(np.clip(rng.gamma(2.0, 9.0), 0.1, 80)), 1)


def age_group(age: float) -> str:
    for lo, hi, lab in AGE_GROUP_BINS:
        if lo <= age < hi:
            return lab
    return "30+"


cases = []
case_counter = 0
for idx, w in weekly.iterrows():
    for _ in range(w["_n_cases"]):
        case_counter += 1
        csf_collected = rng.random() < (0.72 if w["_in_outbreak"] else 0.58)
        if csf_collected:
            if w["_in_outbreak"] and rng.random() < 0.55:
                true_path = w["_outbreak_pathogen"]
            else:
                true_path = rng.choice(PATHOGEN_SPORADIC[0], p=PATHOGEN_SPORADIC[1])
            r = rng.random()
            if r < 0.06:
                lab_result, pathogen = "Pending", None
            elif r < 0.50:
                lab_result, pathogen = "Negative", None
            else:
                lab_result, pathogen = "Positive", true_path
            lab_test = rng.choice(["PCR", "Latex", "Culture"], p=[0.5, 0.35, 0.15])
            csf_look = rng.choice(["Turbid", "Clear", "Bloody", "Xanthochromic"], p=[0.55, 0.33, 0.08, 0.04])
        else:
            true_path = w["_outbreak_pathogen"] if w["_in_outbreak"] else None
            lab_result, pathogen, lab_test, csf_look = "Not tested", None, None, None

        age = draw_age(pathogen or true_path)
        cfr = 0.09
        if pathogen == "S. pneumoniae":
            cfr = 0.18
        elif pathogen in ("NmW", "NmC"):
            cfr = 0.11
        if age < 1:
            cfr += 0.04
        outcome = rng.choice(["Recovered", "Died", "Recovered with sequelae", "Unknown"],
                             p=[0.80 - cfr, cfr, 0.12, 0.08])
        onset = w["week_start_date"] + timedelta(days=int(rng.integers(0, 7)))
        admitted = onset + timedelta(days=int(rng.choice([0, 1, 1, 2, 2, 3, 4])))
        vacc = rng.choice(["Yes - card", "Yes - verbal", "No", "Unknown"],
                          p=[0.32, 0.18, 0.30, 0.20] if age >= 1 else [0.05, 0.05, 0.70, 0.20])
        cases.append(dict(
            case_id=f"SL-MEN-{w['epi_year']}-{case_counter:05d}",
            _parent_row=idx,
            district=w["district"],
            age_years=age, age_group=age_group(age),
            sex=rng.choice(["Male", "Female"], p=[0.53, 0.47]),
            date_of_onset=onset, date_of_admission=admitted,
            fever="yes",
            neck_stiffness="yes" if rng.random() < 0.72 else "no",
            altered_consciousness="yes" if rng.random() < 0.41 else "no",
            petechial_rash="yes" if rng.random() < (0.22 if (pathogen or "").startswith("Nm") else 0.07) else "no",
            bulging_fontanelle=("yes" if rng.random() < 0.5 else "no") if age < 1 else "n/a",
            vaccination_status=vacc,
            facility_type=rng.choice(FACILITY_TYPES[0], p=FACILITY_TYPES[1]),
            csf_collected="yes" if csf_collected else "no",
            csf_appearance=csf_look, lab_test=lab_test, lab_result=lab_result, pathogen=pathogen,
            outcome=outcome,
        ))
case_df = pd.DataFrame(cases)

# ---------------------------------------------------------------------------
# 3. Aggregate line list back into the weekly report (consistency guaranteed)
# ---------------------------------------------------------------------------
agg = case_df.groupby("_parent_row").agg(
    suspected_cases=("case_id", "size"),
    csf_samples_collected=("csf_collected", lambda s: (s == "yes").sum()),
    confirmed_cases=("lab_result", lambda s: (s == "Positive").sum()),
    deaths=("outcome", lambda s: (s == "Died").sum()),
)
weekly = weekly.join(agg)
for col in ["suspected_cases", "csf_samples_collected", "confirmed_cases", "deaths"]:
    weekly[col] = weekly[col].fillna(0).astype(int)
for p in ["NmA", "NmC", "NmW", "NmX", "S. pneumoniae", "Hib"]:
    col = "positive_" + p.lower().replace("s. pneumoniae", "spn")
    counts = case_df[case_df["pathogen"] == p].groupby("_parent_row").size()
    weekly[col] = weekly.index.map(counts).fillna(0).astype(int)

weekly["attack_rate_per_100k"] = (weekly["suspected_cases"] / weekly["population"] * 1e5).round(2)
weekly["threshold_status"] = np.select(
    [weekly["attack_rate_per_100k"] >= EPIDEMIC_PER_100K, weekly["attack_rate_per_100k"] >= ALERT_PER_100K],
    ["Epidemic", "Alert"], "Normal")
weekly["reporting_completeness_pct"] = np.clip(rng.normal(92, 6, len(weekly)), 60, 100).round(0)
weekly["report_on_time"] = np.where(rng.random(len(weekly)) < 0.86, "yes", "no")

# ---------------------------------------------------------------------------
# 4. Outbreak prediction model (logistic regression, fitted with IRLS)
#    Target: district crosses the ALERT threshold in either of the next 2 weeks
#    Features use only information available at the end of the current week.
# ---------------------------------------------------------------------------
weekly = weekly.sort_values(["district", "week_start_date"]).reset_index()
g = weekly.groupby("district")
weekly["ar_lag1"] = g["attack_rate_per_100k"].shift(1)
weekly["ar_change"] = weekly["attack_rate_per_100k"] - weekly["ar_lag1"]
alert = (weekly["attack_rate_per_100k"] >= ALERT_PER_100K).astype(int)
weekly["_alert"] = alert
weekly["alert_next_2wks"] = (
    g["_alert"].shift(-1).fillna(0).astype(int) | g["_alert"].shift(-2).fillna(0).astype(int))
weekly.loc[g.cumcount(ascending=False) < 2, "alert_next_2wks"] = np.nan  # unknown future

FEATURES = ["attack_rate_per_100k", "ar_change", "dust_aod_index", "relative_humidity_pct",
            "max_temperature_c", "menafrivac_coverage_pct", "menfive_coverage_pct", "risk_mult"]
risk_lookup = {d[0]: d[5] for d in DISTRICTS}
weekly["risk_mult"] = weekly["district"].map(risk_lookup)


def design(df, mu=None, sd=None):
    X = df[FEATURES].fillna(0).to_numpy(float)
    if mu is None:
        mu, sd = X.mean(0), X.std(0) + 1e-9
    X = (X - mu) / sd
    return np.column_stack([np.ones(len(X)), X]), mu, sd


def fit_logistic(X, y, l2=1.0, iters=50):
    beta = np.zeros(X.shape[1])
    pen = l2 * np.eye(X.shape[1]); pen[0, 0] = 0
    for _ in range(iters):
        p = sigmoid(X @ beta)
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + pen
        grad = X.T @ (y - p) - pen @ beta
        step = np.linalg.solve(H, grad)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def auc(y, s):
    order = np.argsort(s)
    ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


known = weekly["alert_next_2wks"].notna()
train = known & (weekly["week_start_date"] < date(2026, 1, 1))
test = known & (weekly["week_start_date"] >= date(2026, 1, 1))
Xtr, mu, sd = design(weekly[train])
beta = fit_logistic(Xtr, weekly.loc[train, "alert_next_2wks"].to_numpy(float))
Xall, _, _ = design(weekly, mu, sd)
weekly["predicted_outbreak_prob"] = sigmoid(Xall @ beta).round(4)
weekly["predicted_risk_level"] = pd.cut(weekly["predicted_outbreak_prob"], [-1, 0.15, 0.40, 0.70, 2],
                                        labels=["Low", "Moderate", "High", "Very high"]).astype(str)
weekly["model_split"] = np.where(train, "Train (2023-2025)", np.where(test, "Test (2026)", "Not yet observed"))

THRESH = 0.40
perf_rows = []
for split, mask in [("Train (2023-2025)", train), ("Test (2026)", test)]:
    y = weekly.loc[mask, "alert_next_2wks"].to_numpy(int)
    s = weekly.loc[mask, "predicted_outbreak_prob"].to_numpy()
    pred = (s >= THRESH).astype(int)
    tp, fp = int(((pred == 1) & (y == 1)).sum()), int(((pred == 1) & (y == 0)).sum())
    fn, tn = int(((pred == 0) & (y == 1)).sum()), int(((pred == 0) & (y == 0)).sum())
    perf_rows.append(dict(
        dataset=split, district_weeks=len(y), observed_alerts=int(y.sum()),
        auc_roc=round(auc(y, s), 3) if 0 < y.sum() < len(y) else None,
        decision_threshold=THRESH, true_positives=tp, false_positives=fp, false_negatives=fn, true_negatives=tn,
        sensitivity=round(tp / (tp + fn), 3) if tp + fn else None,
        specificity=round(tn / (tn + fp), 3) if tn + fp else None,
        ppv=round(tp / (tp + fp), 3) if tp + fp else None,
    ))
performance = pd.DataFrame(perf_rows)
coefficients = pd.DataFrame({
    "feature": ["(intercept)"] + FEATURES,
    "coefficient_standardised": beta.round(4),
    "odds_ratio_per_sd": np.exp(beta).round(3),
})

# ---------------------------------------------------------------------------
# 5. Forecast: next 8 weeks, driven by expected climate and current situation
# ---------------------------------------------------------------------------
fc_rows = []
latest = weekly.sort_values("week_start_date").groupby("district").tail(1).set_index("district")
for (name, region, lat, lon, pop0, riskf, dryness) in DISTRICTS:
    last = latest.loc[name]
    ar_prev = last["attack_rate_per_100k"]
    p_onset_cum = 0.0
    for h, ws in enumerate(fc_weeks, start=1):
        c = climate(ws, dryness)
        menfive = 84.0 if name in MENFIVE_DISTRICTS else 0.0
        base = 0.18 + 0.55 * c["harmattan_intensity"] * riskf * (1 - 0.5 * (menfive > 0))
        # chance an outbreak has started by now (same hazard as the simulation), times a typical outbreak size
        z = (-6.4 + 3.2 * c["dust_aod_index"] - 0.035 * (c["relative_humidity_pct"] - 60)
             + np.log(riskf) * 1.6 - 0.04 * menfive - 0.02 * (last["menafrivac_coverage_pct"] - 75))
        dry = ws.month in (11, 12, 1, 2, 3, 4)
        p_onset_cum = 1 - (1 - p_onset_cum) * (1 - (sigmoid(z) if dry else 0))
        outbreak_ar = p_onset_cum * 9.0 * riskf ** 0.8 * (0.35 if menfive > 0 else 1)
        exp_ar = 0.5 * ar_prev * (0.7 ** h) + base + outbreak_ar
        row = dict(attack_rate_per_100k=exp_ar, ar_change=exp_ar - ar_prev,
                   dust_aod_index=c["dust_aod_index"], relative_humidity_pct=c["relative_humidity_pct"],
                   max_temperature_c=c["max_temperature_c"], menafrivac_coverage_pct=last["menafrivac_coverage_pct"],
                   menfive_coverage_pct=menfive, risk_mult=riskf)
        X, _, _ = design(pd.DataFrame([row]), mu, sd)
        prob = float(sigmoid(X @ beta)[0])
        pop = int(last["population"] * (1 + ANNUAL_POP_GROWTH) ** (h / 52))
        iso = ws.isocalendar()
        fc_rows.append(dict(
            district=name, region=region, forecast_horizon_weeks=h,
            epi_year=iso[0], epi_week=iso[1], week_start_date=ws,
            expected_dust_aod_index=c["dust_aod_index"], expected_relative_humidity_pct=c["relative_humidity_pct"],
            expected_attack_rate_per_100k=round(exp_ar, 2),
            expected_cases=round(exp_ar * pop / 1e5, 1),
            expected_cases_lower=round(max(0, exp_ar * pop / 1e5 - 1.96 * np.sqrt(exp_ar * pop / 1e5 + 1)), 1),
            expected_cases_upper=round(exp_ar * pop / 1e5 + 1.96 * np.sqrt(exp_ar * pop / 1e5 + 1), 1),
            predicted_outbreak_prob=round(prob, 4),
        ))
forecast = pd.DataFrame(fc_rows)
forecast["predicted_risk_level"] = pd.cut(forecast["predicted_outbreak_prob"], [-1, 0.15, 0.40, 0.70, 2],
                                          labels=["Low", "Moderate", "High", "Very high"]).astype(str)

# ---------------------------------------------------------------------------
# 6. Kobo-style metadata and final column order
# ---------------------------------------------------------------------------
weekly = weekly.sort_values(["week_start_date", "district"]).reset_index(drop=True)
weekly["_index"] = np.arange(1, len(weekly) + 1)
weekly["_id"] = 41_000_000 + weekly["_index"] * 7
weekly["_uuid"] = [str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)))) for _ in range(len(weekly))]
weekly["_submission_time"] = [
    datetime.combine(d + timedelta(days=int(rng.integers(1, 4)) if t == "yes" else int(rng.integers(4, 10))),
                     time(int(rng.integers(8, 19)), int(rng.integers(0, 60))))
    for d, t in zip(weekly["week_end_date"], weekly["report_on_time"])]
weekly["_submitted_by"] = "dso_" + weekly["district"].str.lower().str.replace(" ", "_")
weekly["_status"] = "submitted_via_web"

parent_map = weekly.set_index("index")[["_index", "_id", "_uuid", "epi_year", "epi_week", "week_start_date"]]
case_df = case_df.join(parent_map, on="_parent_row", rsuffix="_parent")
case_df = case_df.rename(columns={"_index": "_parent_index", "_id": "_submission__id", "_uuid": "_submission__uuid"})
case_df = case_df.sort_values(["week_start_date", "district", "case_id"]).reset_index(drop=True)
case_df["_index"] = np.arange(1, len(case_df) + 1)
case_df["_parent_table_name"] = "meningitis_weekly_report"
case_df = case_df[["case_id", "district", "epi_year", "epi_week", "age_years", "age_group", "sex",
                   "date_of_onset", "date_of_admission", "fever", "neck_stiffness", "altered_consciousness",
                   "petechial_rash", "bulging_fontanelle", "vaccination_status", "facility_type",
                   "csf_collected", "csf_appearance", "lab_test", "lab_result", "pathogen", "outcome",
                   "_index", "_parent_index", "_parent_table_name", "_submission__id", "_submission__uuid"]]

weekly_cols = ["district", "region", "epi_year", "epi_week", "week_start_date", "week_end_date", "population",
               "suspected_cases", "csf_samples_collected", "confirmed_cases", "deaths",
               "positive_nma", "positive_nmc", "positive_nmw", "positive_nmx", "positive_spn", "positive_hib",
               "attack_rate_per_100k", "threshold_status", "dry_season", "dust_aod_index",
               "relative_humidity_pct", "max_temperature_c", "rainfall_mm",
               "menafrivac_coverage_pct", "menfive_coverage_pct",
               "reporting_completeness_pct", "report_on_time",
               "predicted_outbreak_prob", "predicted_risk_level", "alert_next_2wks", "model_split",
               "_id", "_uuid", "_submission_time", "_index", "_submitted_by", "_status"]
weekly = weekly[weekly_cols]
weekly["alert_next_2wks"] = weekly["alert_next_2wks"].map({1.0: "yes", 0.0: "no"})

districts = pd.DataFrame([dict(district=d[0], region=d[1], latitude=d[2], longitude=d[3], population_2023=d[4],
                               menfive_campaign_nov_2025="yes" if d[0] in MENFIVE_DISTRICTS else "no")
                          for d in DISTRICTS])

dictionary = pd.DataFrame([
    ("weekly_surveillance", "Main Kobo form: one district weekly meningitis report (IDSR style)."),
    ("cases", "Kobo repeat group: one row per suspected case. Join cases._parent_index = weekly_surveillance._index."),
    ("districts", "Lookup: district, region, map coordinates, population, MenFive campaign flag."),
    ("forecast", "16-week ahead forecast per district from the prediction model."),
    ("model_performance", "Accuracy of the outbreak prediction model on training (2023-2025) and test (2026) data."),
    ("model_coefficients", "Logistic regression coefficients (standardised features) and odds ratios."),
    ("attack_rate_per_100k", "Suspected cases / population x 100,000 for the week."),
    ("threshold_status", "WHO thresholds: Alert >= 3 per 100k per week, Epidemic >= 10 per 100k per week."),
    ("dust_aod_index", "Aerosol optical depth proxy for Harmattan dust (higher = dustier)."),
    ("predicted_outbreak_prob", "Model probability that the district crosses the Alert threshold in the next 2 weeks."),
    ("predicted_risk_level", "Low < 0.15, Moderate 0.15-0.40, High 0.40-0.70, Very high >= 0.70."),
    ("alert_next_2wks", "What actually happened: yes if Alert threshold was crossed in either of the next 2 weeks."),
    ("model_split", "Train = data used to fit the model; Test = 2026 data the model never saw."),
    ("DISCLAIMER", "All data are FICTITIOUS and simulated for training purposes. Not real surveillance data."),
], columns=["item", "description"])

tables = {
    "weekly_surveillance": weekly, "cases": case_df, "districts": districts, "forecast": forecast,
    "model_performance": performance, "model_coefficients": coefficients, "data_dictionary": dictionary,
}
with pd.ExcelWriter(OUT / "meningitis_surveillance_kobo.xlsx", engine="openpyxl") as xw:
    for name, df in tables.items():
        df.to_excel(xw, sheet_name=name, index=False)
for name, df in tables.items():
    df.to_csv(OUT / "csv" / f"{name}.csv", index=False)

print(f"weekly rows: {len(weekly):,}   cases: {len(case_df):,}   forecast rows: {len(forecast)}")
print(weekly["threshold_status"].value_counts().to_string())
print(performance.to_string(index=False))
