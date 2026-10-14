// Power Query (M) — load every table straight from GitHub.
// Power BI Desktop: Home → Transform data → New Source → Blank Query → Advanced Editor → paste one block per query.
// Name each query exactly as in the comment above it. Authentication: Anonymous (the repo is public).

// ---- Query name: BaseUrl  (Home → Manage Parameters → New: Text) -----------------------------
// https://raw.githubusercontent.com/amayei/meningitis-outbreak-powerbi/main/data/csv/

// ---- Query name: weekly_surveillance -------------------------------------------------------
let
    Source = Csv.Document(Web.Contents(BaseUrl & "weekly_surveillance.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"district", type text}, {"region", type text}, {"epi_year", Int64.Type}, {"epi_week", Int64.Type},
        {"week_start_date", type date}, {"week_end_date", type date}, {"population", Int64.Type},
        {"suspected_cases", Int64.Type}, {"csf_samples_collected", Int64.Type}, {"confirmed_cases", Int64.Type},
        {"deaths", Int64.Type}, {"positive_nma", Int64.Type}, {"positive_nmc", Int64.Type}, {"positive_nmw", Int64.Type},
        {"positive_nmx", Int64.Type}, {"positive_spn", Int64.Type}, {"positive_hib", Int64.Type},
        {"attack_rate_per_100k", type number}, {"threshold_status", type text}, {"dry_season", type text},
        {"dust_aod_index", type number}, {"relative_humidity_pct", type number}, {"max_temperature_c", type number},
        {"rainfall_mm", type number}, {"menafrivac_coverage_pct", type number}, {"menfive_coverage_pct", type number},
        {"reporting_completeness_pct", type number}, {"report_on_time", type text},
        {"predicted_outbreak_prob", type number}, {"predicted_risk_level", type text}, {"alert_next_2wks", type text},
        {"model_split", type text}, {"_id", Int64.Type}, {"_uuid", type text}, {"_submission_time", type datetime},
        {"_index", Int64.Type}, {"_submitted_by", type text}, {"_status", type text}}, "en-US")
in
    Typed

// ---- Query name: cases ---------------------------------------------------------------------
let
    Source = Csv.Document(Web.Contents(BaseUrl & "cases.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"epi_year", Int64.Type}, {"epi_week", Int64.Type}, {"age_years", type number},
        {"date_of_onset", type date}, {"date_of_admission", type date},
        {"_index", Int64.Type}, {"_parent_index", Int64.Type}, {"_submission__id", Int64.Type}}, "en-US"),
    Pathogen = Table.ReplaceValue(Typed, "", "Not identified", Replacer.ReplaceValue, {"pathogen"}),
    Delay = Table.AddColumn(Pathogen, "days_onset_to_admission",
        each Duration.Days([date_of_admission] - [date_of_onset]), Int64.Type)
in
    Delay

// ---- Query name: districts / forecast / model_performance / model_coefficients --------------
// Same pattern: replace the file name, then set types (Home → Detect data type works fine).
let
    Source = Csv.Document(Web.Contents(BaseUrl & "districts.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"latitude", type number}, {"longitude", type number}, {"population_2023", Int64.Type}}, "en-US")
in
    Typed
