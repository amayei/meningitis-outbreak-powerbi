# Meningitis Outbreak Prediction – Power BI Practice Dataset (Sierra Leone)

> ⚠️ **All data in this repository are FICTITIOUS.** They are simulated for Power BI training and do not represent real surveillance data, real patients or the real epidemiological situation in Sierra Leone.

A realistic, KoboToolbox-shaped dataset for building a **meningitis early-warning and outbreak-prediction dashboard** in Power BI. It mimics a weekly IDSR district report (main Kobo form) with a **case line list as a repeat group**, plus climate drivers (Harmattan dust, humidity), vaccination coverage, and a trained **logistic-regression model** that predicts which districts will cross the WHO alert threshold in the next two weeks.

## What's inside

| File | Rows | Description |
|---|---|---|
| `data/meningitis_surveillance_kobo.xlsx` | – | All tables, one sheet each (same structure as a Kobo XLSX export) |
| `data/csv/weekly_surveillance.csv` | 3,152 | 16 districts × 197 weeks (2023-W01 → 2026-W41). Cases, deaths, lab results by pathogen, attack rate, WHO threshold status, climate, vaccination, model prediction |
| `data/csv/cases.csv` | 19,145 | Repeat group: one row per suspected case (age, sex, symptoms, vaccination, CSF/lab, pathogen, outcome) |
| `data/csv/districts.csv` | 16 | Region, latitude/longitude (for maps), population, MenFive campaign flag |
| `data/csv/forecast.csv` | 256 | 16-week-ahead forecast per district (expected cases with 95% band, outbreak probability, risk level) |
| `data/csv/model_performance.csv` | 2 | AUC, sensitivity, specificity, PPV on train (2023–25) and test (2026) |
| `data/csv/model_coefficients.csv` | 9 | Odds ratios of the prediction model |
| `data/csv/data_dictionary.csv` | – | Column and table definitions |
| `powerbi/load_from_github.pq` | – | Power Query (M) code to load the CSVs live from GitHub |
| `powerbi/measures.dax` | – | Ready-made DAX measures and a Calendar table |
| `scripts/generate_data.py` | – | Reproducible generator (seeded) |

**Join key (like Kobo):** `cases[_parent_index]` → `weekly_surveillance[_index]`

### The story hidden in the data
- Strong **dry-season seasonality**: outbreaks start Dec–Mar when Harmattan dust is high and humidity low.
- The **northern belt** (Falaba, Koinadugu, Kambia, Karene, Bombali) carries the highest risk in 2023–2025, and **2024** was a severe Harmattan year.
- A **MenFive campaign (Nov 2025)** in 7 northern districts cuts their 2026 risk sharply.
- The **forecast for Jan 2027** shows risk moving to the **unvaccinated East and South** (Kono, Kenema, Bo, Kailahun), which suggests where to extend vaccination next.
- **NmW** and **NmC** drive the outbreaks. *S. pneumoniae* dominates sporadic cases and has the highest case fatality rate.
- Model test performance (2026, unseen data): **AUC 0.98, sensitivity 71%, specificity 99.8%**.

## Connect Power BI (refreshable, no download needed)

1. Power BI Desktop → **Get data → Web**.
2. Paste a raw URL, for example
   `https://raw.githubusercontent.com/amayei/meningitis-outbreak-powerbi/main/data/csv/weekly_surveillance.csv`
3. Choose **Anonymous**, then **Connect** → **Transform data**.
4. Repeat for `cases.csv`, `districts.csv`, `forecast.csv`, `model_performance.csv`, `model_coefficients.csv`.

Or paste the queries in [`powerbi/load_from_github.pq`](powerbi/load_from_github.pq), which use a single `BaseUrl` parameter. Because this is a web source, **Refresh** pulls the latest data, and in the Power BI Service you can turn on **scheduled refresh** with no gateway. A Kobo synchronous-export link works the same way.

## Data model (Model view)

```
Calendar[Date] 1 ──── * weekly_surveillance[week_start_date]
Calendar[Date] 1 ──── * forecast[week_start_date]
districts[district] 1 ──── * weekly_surveillance[district]
districts[district] 1 ──── * forecast[district]
weekly_surveillance[_index] 1 ──── * cases[_parent_index]
```
Set **cross-filter direction = Single** for all. Mark `Calendar` as a date table.

## Suggested dashboard (5 pages)

1. **Situation overview.** KPI cards: Suspected cases, Confirmed, Deaths, CFR %, Districts in Epidemic, Districts High Risk Now. Line chart of weekly cases by year (shows seasonality). Filled map (district) coloured by attack rate. Slicers for year, region and district.
2. **Early warning and prediction.** Matrix heatmap with district rows, epi_week columns and conditional colour on `predicted_outbreak_prob`. Line chart of predicted probability vs actual `alert_next_2wks`. Table of model performance and a bar chart of odds ratios.
3. **16-week forecast.** Line chart of expected cases with lower and upper band (error bars or area). Map of the forecast risk level. Ranked bar chart of districts by peak probability.
4. **Drivers.** Scatter of dust index vs attack rate (size = cases, legend = region). Combo chart of humidity (line) and cases (columns) over time. Before/after MenFive comparison.
5. **Case profile and lab.** Age-group × sex pyramid, pathogen donut, CFR by pathogen, vaccination status, CSF collection rate, onset-to-admission delay, reporting completeness and timeliness by district.

**Colour tip:** use one sequential colour scale for risk (light blue → dark red) and keep it the same on every page.

## Regenerate the data

```bash
pip install pandas numpy openpyxl
python scripts/generate_data.py
```

## Thresholds used
WHO weekly thresholds for districts with more than 30,000 people: **Alert ≥ 3 suspected cases per 100,000**, **Epidemic ≥ 10 per 100,000**.

---
*Created for Power BI training. Fictitious data, MIT licence.*
