"""Run final data-quality checks before loading CSV data into PostgreSQL."""

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = PROJECT_ROOT / "data" / "jobs.csv"
OPERATIONS_PATH = PROJECT_ROOT / "data" / "job_operations.csv"
DOWNTIME_PATH = PROJECT_ROOT / "data" / "downtime_events.csv"

EXPECTED_JOB_COUNT = 30_000
EXPECTED_OPERATION_COUNT = 150_000
OPERATIONS_PER_JOB = 5

JOB_COLUMNS = [
    "job_code",
    "product_id",
    "quantity",
    "priority",
    "status",
    "created_at",
    "due_at",
]
OPERATION_COLUMNS = [
    "job_id",
    "work_center_id",
    "machine_id",
    "operation_sequence",
    "arrival_time",
    "start_time",
    "end_time",
    "wait_time_minutes",
    "processing_time_minutes",
    "status",
]
DOWNTIME_COLUMNS = [
    "machine_id",
    "start_time",
    "end_time",
    "reason",
    "downtime_minutes",
]


def require_columns(
    data: pd.DataFrame, required: list[str], dataset_name: str
) -> list[str]:
    """Return an error when a dataset is missing required columns."""
    missing = sorted(set(required).difference(data.columns))
    if missing:
        return [f"{dataset_name}: missing required columns: {', '.join(missing)}"]
    return []


def load_datasets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read all source CSVs without changing them."""
    for path in (JOBS_PATH, OPERATIONS_PATH, DOWNTIME_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Required dataset not found: {path}")

    jobs = pd.read_csv(JOBS_PATH)
    operations = pd.read_csv(OPERATIONS_PATH)
    downtime = pd.read_csv(DOWNTIME_PATH)

    column_errors = []
    column_errors.extend(require_columns(jobs, JOB_COLUMNS, "JOBS"))
    column_errors.extend(
        require_columns(operations, OPERATION_COLUMNS, "JOB OPERATIONS")
    )
    column_errors.extend(require_columns(downtime, DOWNTIME_COLUMNS, "DOWNTIME"))
    if column_errors:
        raise ValueError("Data validation failed:\n- " + "\n- ".join(column_errors))

    for column in ("created_at", "due_at"):
        jobs[column] = pd.to_datetime(jobs[column], errors="coerce")
    for column in ("arrival_time", "start_time", "end_time"):
        operations[column] = pd.to_datetime(operations[column], errors="coerce")
    for column in ("start_time", "end_time"):
        downtime[column] = pd.to_datetime(downtime[column], errors="coerce")

    numeric_columns = {
        "jobs": (jobs, ["product_id", "quantity"]),
        "operations": (
            operations,
            [
                "job_id",
                "work_center_id",
                "machine_id",
                "operation_sequence",
                "wait_time_minutes",
                "processing_time_minutes",
            ],
        ),
        "downtime": (downtime, ["machine_id", "downtime_minutes"]),
    }
    for data, columns in numeric_columns.values():
        for column in columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    return jobs, operations, downtime


def validate_jobs(jobs: pd.DataFrame) -> list[str]:
    """Validate job-level requirements and return any failures."""
    errors: list[str] = []
    if len(jobs) != EXPECTED_JOB_COUNT:
        errors.append(
            f"JOBS: expected {EXPECTED_JOB_COUNT:,} rows, found {len(jobs):,}"
        )
    if jobs[JOB_COLUMNS].isna().any().any():
        errors.append("JOBS: required values are missing or invalid")
    if not jobs["job_code"].is_unique:
        errors.append("JOBS: job_code values are not unique")
    if not jobs["product_id"].isin([1, 2, 3]).all():
        errors.append("JOBS: product_id contains a value other than 1, 2, or 3")
    if not jobs["quantity"].gt(0).all():
        errors.append("JOBS: quantity must be positive for every row")
    if not jobs["due_at"].gt(jobs["created_at"]).all():
        errors.append("JOBS: due_at must be after created_at for every row")
    return errors


def validate_operations(operations: pd.DataFrame) -> list[str]:
    """Validate job-operation requirements and return any failures."""
    errors: list[str] = []
    if len(operations) != EXPECTED_OPERATION_COUNT:
        errors.append(
            "JOB OPERATIONS: expected "
            f"{EXPECTED_OPERATION_COUNT:,} rows, found {len(operations):,}"
        )
    if operations[OPERATION_COLUMNS].isna().any().any():
        errors.append("JOB OPERATIONS: required values are missing or invalid")

    counts = operations.groupby("job_id").size()
    if len(counts) != EXPECTED_JOB_COUNT or not counts.eq(OPERATIONS_PER_JOB).all():
        errors.append("JOB OPERATIONS: every job must have exactly 5 operations")
    if not operations["work_center_id"].between(1, 5).all():
        errors.append("JOB OPERATIONS: work_center_id must be between 1 and 5")
    if not operations["machine_id"].between(1, 15).all():
        errors.append("JOB OPERATIONS: machine_id must be between 1 and 15")

    expected_work_center = ((operations["machine_id"] - 1) // 3) + 1
    if not operations["work_center_id"].eq(expected_work_center).all():
        errors.append("JOB OPERATIONS: machine assigned to the wrong work center")
    if not operations["operation_sequence"].between(1, 5).all():
        errors.append("JOB OPERATIONS: operation_sequence must be between 1 and 5")
    if not operations["operation_sequence"].eq(operations["work_center_id"]).all():
        errors.append(
            "JOB OPERATIONS: operation sequence does not follow work centers 1 through 5"
        )
    if operations.duplicated(["job_id", "operation_sequence"]).any():
        errors.append("JOB OPERATIONS: duplicate job_id + operation_sequence found")
    if not operations["start_time"].ge(operations["arrival_time"]).all():
        errors.append("JOB OPERATIONS: start_time occurs before arrival_time")
    if not operations["end_time"].gt(operations["start_time"]).all():
        errors.append("JOB OPERATIONS: end_time must be after start_time")
    if not operations["wait_time_minutes"].ge(0).all():
        errors.append("JOB OPERATIONS: wait_time_minutes cannot be negative")
    if not operations["processing_time_minutes"].gt(0).all():
        errors.append("JOB OPERATIONS: processing_time_minutes must be positive")

    ordered = operations.sort_values(["job_id", "operation_sequence"])
    previous_end = ordered.groupby("job_id")["end_time"].shift()
    later_operation = ordered["operation_sequence"].gt(1)
    if not ordered.loc[later_operation, "arrival_time"].ge(
        previous_end[later_operation]
    ).all():
        errors.append(
            "JOB OPERATIONS: an operation arrives before its preceding operation ends"
        )
    return errors


def validate_downtime(downtime: pd.DataFrame) -> list[str]:
    """Validate downtime-event requirements and return any failures."""
    errors: list[str] = []
    if downtime[DOWNTIME_COLUMNS].isna().any().any():
        errors.append("DOWNTIME: required values are missing or invalid")
    if not downtime["machine_id"].between(1, 15).all():
        errors.append("DOWNTIME: machine_id must be between 1 and 15")
    if not downtime["end_time"].gt(downtime["start_time"]).all():
        errors.append("DOWNTIME: end_time must be after start_time")
    if not downtime["downtime_minutes"].gt(0).all():
        errors.append("DOWNTIME: downtime_minutes must be positive")

    ordered = downtime.sort_values(["machine_id", "start_time"])
    previous_end = ordered.groupby("machine_id")["end_time"].shift()
    if (ordered["start_time"] < previous_end).fillna(False).any():
        errors.append("DOWNTIME: overlapping events found for the same machine")
    return errors


def validate_cross_dataset(
    jobs: pd.DataFrame, operations: pd.DataFrame, downtime: pd.DataFrame
) -> list[str]:
    """Validate relationships that span more than one dataset."""
    errors: list[str] = []

    # jobs.csv has no job_id column; its PostgreSQL IDs are expected to be assigned
    # in one-based CSV row order, matching generate_operations.py.
    expected_job_ids = pd.Index(np.arange(1, len(jobs) + 1))
    operation_job_ids = pd.Index(operations["job_id"].dropna().unique())
    unknown_job_ids = operation_job_ids.difference(expected_job_ids)
    missing_job_ids = expected_job_ids.difference(operation_job_ids)
    if len(unknown_job_ids):
        errors.append(
            f"CROSS-DATASET: {len(unknown_job_ids):,} operation job IDs do not exist"
        )
    if len(missing_job_ids):
        errors.append(
            f"CROSS-DATASET: {len(missing_job_ids):,} jobs have no operations"
        )

    first_operations = operations.loc[
        operations["operation_sequence"].eq(1), ["job_id", "arrival_time"]
    ].drop_duplicates("job_id").set_index("job_id")
    expected_creation_times = pd.Series(
        jobs["created_at"].to_numpy(), index=expected_job_ids
    )
    common_ids = first_operations.index.intersection(expected_job_ids)
    if not first_operations.loc[common_ids, "arrival_time"].eq(
        expected_creation_times.loc[common_ids]
    ).all():
        errors.append(
            "CROSS-DATASET: first-operation arrival does not match job created_at"
        )

    operation_machines = set(operations["machine_id"].dropna().astype(int))
    downtime_machines = set(downtime["machine_id"].dropna().astype(int))
    if not downtime_machines.issubset(operation_machines):
        errors.append("CROSS-DATASET: downtime references an unused machine")
    return errors


def print_report(
    jobs: pd.DataFrame,
    operations: pd.DataFrame,
    downtime: pd.DataFrame,
    passed: bool,
) -> None:
    """Print a concise final validation report."""
    machines = set(operations["machine_id"].dropna()).union(
        downtime["machine_id"].dropna()
    )
    print("Final data validation report")
    print(f"Job count: {len(jobs):,}")
    print(f"Operation count: {len(operations):,}")
    print(f"Downtime event count: {len(downtime):,}")
    print(f"Products represented: {jobs['product_id'].nunique(dropna=True):,}")
    print(f"Machines represented: {len(machines):,}")
    print(f"All validations passed: {'YES' if passed else 'NO'}")


def main() -> None:
    """Load all datasets, execute every check, and report the result."""
    jobs, operations, downtime = load_datasets()
    errors = [
        *validate_jobs(jobs),
        *validate_operations(operations),
        *validate_downtime(downtime),
        *validate_cross_dataset(jobs, operations, downtime),
    ]
    print_report(jobs, operations, downtime, passed=not errors)
    if errors:
        raise ValueError("Data validation failed:\n- " + "\n- ".join(errors))


if __name__ == "__main__":
    main()
