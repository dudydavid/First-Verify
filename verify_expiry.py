# %%
from pathlib import Path
import re

import pandas as pd
from dateutil.easter import easter


# ============================================================
# CONFIG
# ============================================================

try:
    ROOT = Path(__file__).resolve().parents[1]
except NameError:
    ROOT = Path.cwd().resolve()
    if ROOT.name.lower() == "src":
        ROOT = ROOT.parent


VX_PATH = ROOT / "data" / "raw" / "VX_master.csv"

OUT_DIR = ROOT / "output" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# %%
# ============================================================
# HELPERS
# ============================================================

def canonicalize_columns(df):
    df = df.copy()

    df.columns = [
        re.sub(
            r"[^a-z0-9]+",
            "_",
            str(c).strip().lower()
        ).strip("_")
        for c in df.columns
    ]

    return df


MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_contract(series):
    """
    Parse:
        F (Jan 2020)
        G (Feb 2020)
        ...
    """

    extracted = series.astype(str).str.extract(
        r"\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\)",
        flags=re.IGNORECASE,
    )

    result = pd.DataFrame(index=series.index)

    result["expiry_month"] = (
        extracted[0]
        .str.lower()
        .map(MONTH_MAP)
        .astype("Int64")
    )

    result["expiry_year"] = (
        pd.to_numeric(
            extracted[1],
            errors="coerce"     
        )
        .astype("Int64")
    )

    return result


# %%
# ============================================================
# FIND THIRD FRIDAY
# ============================================================

def third_friday(year: int, month: int) -> pd.Timestamp:
    """
    Return the third Friday of a calendar month. Independent of calendar module global state.
    """

    first_of_month = pd.Timestamp(
        year=year,
        month=month,
        day=1
    )

    days_until_friday = (
        4 - first_of_month.weekday()
    ) % 7

    first_friday = (
        first_of_month
        + pd.Timedelta(days=days_until_friday)
    )

    return (
        first_friday
        + pd.Timedelta(days=14)
    )


# %%
# ============================================================
# CBOE HOLIDAYS RELEVANT TO VX EXPIRY
# ============================================================

def good_friday(year: int) -> pd.Timestamp:
    """
    Cboe Options is closed on Good Friday.
    """

    easter_sunday = pd.Timestamp(
        easter(year)
    )

    return (
        easter_sunday
        - pd.Timedelta(days=2)
    )


def juneteenth_observed(year: int):
    """
    Cboe began observing Juneteenth as a market holiday
    starting in 2022.

    Return the observed date.
    """

    if year < 2022:
        return None

    actual = pd.Timestamp(
        year=year,
        month=6,
        day=19
    )

    weekday = actual.weekday()

    # Saturday -> Friday
    if weekday == 5:
        return actual - pd.Timedelta(days=1)

    # Sunday -> Monday
    if weekday == 6:
        return actual + pd.Timedelta(days=1)

    return actual


def relevant_cboe_holidays(start_year, end_year):
    """
    We only need holidays capable of affecting the VX
    monthly settlement formula.

    The settlement Wednesday/reference Friday live in the
    middle of the month, so most normal exchange holidays
    cannot coincide with them.

    Good Friday and Juneteenth are the material recurring
    cases in our 2013-2026 sample.
    """

    holidays = set()

    for year in range(
        start_year,
        end_year + 1
    ):
        holidays.add(
            good_friday(year).normalize()
        )

        june = juneteenth_observed(year)

        if june is not None:
            holidays.add(
                june.normalize()
            )

    return holidays


# %%
# ============================================================
# BUSINESS-DAY PREDECESSOR
# ============================================================

def previous_business_day(
    date: pd.Timestamp,
    holiday_set: set
) -> pd.Timestamp:

    candidate = (
        date
        - pd.Timedelta(days=1)
    )

    while (
        candidate.weekday() >= 5
        or candidate.normalize()
        in holiday_set
    ):
        candidate -= pd.Timedelta(days=1)

    return candidate


# %%
# ============================================================
# CALCULATE VX MONTHLY EXPIRY
# ============================================================

def calculate_vx_expiry(
    contract_year: int,
    contract_month: int,
    holiday_set: set,
):
    """
    Standard monthly VX rule:

    1. Find the third Friday of the FOLLOWING calendar month.
    2. Go back exactly 30 calendar days.
       This normally lands on Wednesday.
    3. If either:
         - that Wednesday, or
         - the Friday 30 days later
       is a Cboe Options holiday,
       move expiry to the immediately preceding
       Cboe business day.
    """

    # Following month
    if contract_month == 12:
        next_month = 1
        next_year = contract_year + 1
    else:
        next_month = contract_month + 1
        next_year = contract_year

    reference_friday = third_friday(
        next_year,
        next_month
    )

    nominal_expiry = (
        reference_friday
        - pd.Timedelta(days=30)
    )

    holiday_adjustment = False
    adjustment_reason = ""

    nominal_is_holiday = (
        nominal_expiry.normalize()
        in holiday_set
    )

    friday_is_holiday = (
        reference_friday.normalize()
        in holiday_set
    )

    if (
        nominal_is_holiday
        or friday_is_holiday
    ):

        actual_expiry = (
            previous_business_day(
                nominal_expiry,
                holiday_set
            )
        )

        holiday_adjustment = True

        reasons = []

        if nominal_is_holiday:
            reasons.append(
                "nominal settlement day holiday"
            )

        if friday_is_holiday:
            reasons.append(
                "reference third-Friday holiday"
            )

        adjustment_reason = "; ".join(
            reasons
        )

    else:
        actual_expiry = nominal_expiry

    return {
        "reference_friday":
            reference_friday,

        "nominal_expiry":
            nominal_expiry,

        "calculated_expiry":
            actual_expiry,

        "holiday_adjusted":
            holiday_adjustment,

        "adjustment_reason":
            adjustment_reason,
    }


# %%
# ============================================================
# LOAD DATA
# ============================================================

vx = canonicalize_columns(
    pd.read_csv(
        VX_PATH,
        low_memory=False
    )
)

vx["trade_date"] = pd.to_datetime(
    vx["trade_date"],
    errors="raise"
)

parsed = parse_contract(
    vx["futures"]
)

vx = pd.concat(
    [vx, parsed],
    axis=1
)

if (
    vx["expiry_year"].isna().any()
    or vx["expiry_month"].isna().any()
):
    raise ValueError(
        "Unparseable contract labels found."
    )


# %%
# ============================================================
# CONTRACT METADATA
# ============================================================

contract_meta = (
    vx.groupby(
        [
            "futures",
            "expiry_year",
            "expiry_month",
        ]
    )
    .agg(
        first_observation=(
            "trade_date",
            "min"
        ),

        last_observation=(
            "trade_date",
            "max"
        ),

        rows=(
            "trade_date",
            "size"
        ),
    )
    .reset_index()
)


dataset_end = vx[
    "trade_date"
].max()


print(
    "Dataset end:",
    dataset_end.date()
)


# %%
# ============================================================
# BUILD HOLIDAY SET
# ============================================================

min_year = int(
    contract_meta[
        "expiry_year"
    ].min()
)

max_year = int(
    contract_meta[
        "expiry_year"
    ].max()
) + 1


holiday_set = relevant_cboe_holidays(
    min_year,
    max_year
)


# %%
# ============================================================
# CALCULATE EXPIRIES INDEPENDENTLY
# ============================================================

calculated_rows = []

for _, row in contract_meta.iterrows():

    result = calculate_vx_expiry(
        int(row["expiry_year"]),
        int(row["expiry_month"]),
        holiday_set,
    )

    calculated_rows.append(
        result
    )


calc_df = pd.DataFrame(
    calculated_rows
)


contract_meta = pd.concat(
    [
        contract_meta.reset_index(drop=True),
        calc_df.reset_index(drop=True),
    ],
    axis=1,
)


# %%
# ============================================================
# CLASSIFY CONTRACT STATUS
# ============================================================

contract_meta["expired_by_dataset_end"] = (
    contract_meta["calculated_expiry"]
    <= dataset_end
)


contract_meta["days_terminal_difference"] = (
    contract_meta["last_observation"]
    - contract_meta["calculated_expiry"]
).dt.days


def classify(row):

    # Contract expiry occurs after our dataset ends:
    # impossible to validate terminal row yet.
    if not row["expired_by_dataset_end"]:
        return "PENDING_NOT_EXPIRED"

    # Expired and terminal row matches calculated expiry.
    if (
        row["last_observation"]
        == row["calculated_expiry"]
    ):
        return "PASS"

    # Contract should have expired within the sample,
    # but data doesn't terminate on expected expiry.
    return "FAIL_TERMINAL_DATE_MISMATCH"


contract_meta["verification_status"] = (
    contract_meta.apply(
        classify,
        axis=1
    )
)


# %%
# ============================================================
# SUMMARY
# ============================================================

print("\n========================================")
print("VERIFICATION STATUS")
print("========================================")

print(
    contract_meta[
        "verification_status"
    ]
    .value_counts()
    .to_string()
)


# %%
# ============================================================
# HARD FAILURES ONLY
# ============================================================

failures = contract_meta[
    contract_meta[
        "verification_status"
    ]
    == "FAIL_TERMINAL_DATE_MISMATCH"
]


print("\n========================================")
print("HARD FAILURES")
print("========================================")

if failures.empty:

    print("NONE")

else:

    print(
        failures[
            [
                "futures",
                "reference_friday",
                "nominal_expiry",
                "calculated_expiry",
                "last_observation",
                "days_terminal_difference",
                "holiday_adjusted",
                "adjustment_reason",
            ]
        ]
        .to_string(index=False)
    )


# %%
# ============================================================
# PENDING / ACTIVE CONTRACTS
# ============================================================

pending = contract_meta[
    contract_meta[
        "verification_status"
    ]
    == "PENDING_NOT_EXPIRED"
]


print("\n========================================")
print("PENDING — NOT YET EXPIRED")
print("========================================")

if pending.empty:

    print("NONE")

else:

    print(
        pending[
            [
                "futures",
                "last_observation",
                "calculated_expiry",
            ]
        ]
        .sort_values(
            "calculated_expiry"
        )
        .to_string(index=False)
    )


# %%
# ============================================================
# HOLIDAY-ADJUSTED CONTRACTS
# ============================================================

adjusted = contract_meta[
    contract_meta[
        "holiday_adjusted"
    ]
]


print("\n========================================")
print("HOLIDAY-ADJUSTED EXPIRIES")
print("========================================")

if adjusted.empty:

    print("NONE")

else:

    print(
        adjusted[
            [
                "futures",
                "reference_friday",
                "nominal_expiry",
                "calculated_expiry",
                "last_observation",
                "adjustment_reason",
                "verification_status",
            ]
        ]
        .sort_values(
            "calculated_expiry"
        )
        .to_string(index=False)
    )


# %%
# ============================================================
# PASS SAMPLE
# ============================================================

passed = contract_meta[
    contract_meta[
        "verification_status"
    ]
    == "PASS"
]


print("\n========================================")
print("PASS COUNT BY EXPIRY YEAR")
print("========================================")

print(
    passed.groupby(
        "expiry_year"
    )
    .size()
    .to_string()
)


# %%
# ============================================================
# FULL TABLE
# ============================================================

display_cols = [
    "futures",
    "first_observation",
    "last_observation",
    "reference_friday",
    "nominal_expiry",
    "calculated_expiry",
    "holiday_adjusted",
    "verification_status",
]


print("\n========================================")
print("FULL EXPIRY VERIFICATION TABLE")
print("========================================")

print(
    contract_meta[
        display_cols
    ]
    .sort_values(
        "calculated_expiry"
    )
    .to_string(index=False)
)


# %%
# ============================================================
# SAVE
# ============================================================

output_path = (
    OUT_DIR
    / "expiry_date_verification.csv"
)

contract_meta.to_csv(
    output_path,
    index=False
)


print("\nSaved:")
print(output_path)


# %%
# ============================================================
# FINAL HARD-FAIL ASSERTION
# ============================================================

n_failures = len(failures)
n_pending = len(pending)
n_passed = len(passed)


print("\n========================================")
print("FINAL RESULT")
print("========================================")

print(
    f"PASS:    {n_passed}"
)

print(
    f"PENDING: {n_pending}"
)

print(
    f"FAIL:    {n_failures}"
)


if n_failures > 0:

    raise RuntimeError(
        f"{n_failures} expired contracts "
        "failed independent expiry verification."
    )

else:

    print(
        "\nNo expired contract failed "
        "independent expiry verification."
    )
