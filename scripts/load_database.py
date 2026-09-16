"""Load validated manufacturing CSV datasets into the existing PostgreSQL schema."""

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from validate_data import (
    validate_cross_dataset,
    validate_downtime,
    validate_jobs,
    validate_operations,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = PROJECT_ROOT / "data" / "jobs.csv"
OPERATIONS_PATH = PROJECT_ROOT / "data" / "job_operations.csv"
DOWNTIME_PATH = PROJECT_ROOT / "data" / "downtime_events.csv"

BATCH_SIZE = 5_000
EXPECTED_COUNTS = {
    "jobs": 30_000,
    "job_operations": 150_000,
    "downtime_events": 220,
    "products": 3,
    "machines": 15,
}

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


def load_database_settings() -> dict[str, str]:
    """Read required database settings from .env without displaying secrets."""
    load_dotenv(PROJECT_ROOT / ".env")
    variable_names = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    settings = {name: os.getenv(name, "").strip() for name in variable_names}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise ValueError(
            "Missing required database settings: " + ", ".join(sorted(missing))
        )

    try:
        port = int(settings["DB_PORT"])
    except ValueError as error:
        raise ValueError("DB_PORT must be a valid integer.") from error
    if not 1 <= port <= 65_535:
        raise ValueError("DB_PORT must be between 1 and 65535.")
    return settings


def create_database_engine(settings: dict[str, str]) -> Engine:
    """Create a SQLAlchemy engine using the psycopg PostgreSQL driver."""
    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=settings["DB_USER"],
        password=settings["DB_PASSWORD"],
        host=settings["DB_HOST"],
        port=int(settings["DB_PORT"]),
        database=settings["DB_NAME"],
    )
    return create_engine(database_url, pool_pre_ping=True)


def read_csv_datasets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read source CSVs and convert their timestamp columns."""
    for path in (JOBS_PATH, OPERATIONS_PATH, DOWNTIME_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file not found: {path}")

    jobs = pd.read_csv(
        JOBS_PATH,
        usecols=JOB_COLUMNS,
        parse_dates=["created_at", "due_at"],
    )
    operations = pd.read_csv(
        OPERATIONS_PATH,
        usecols=OPERATION_COLUMNS,
        parse_dates=["arrival_time", "start_time", "end_time"],
    )
    downtime = pd.read_csv(
        DOWNTIME_PATH,
        usecols=DOWNTIME_COLUMNS,
        parse_dates=["start_time", "end_time"],
    )
    return jobs, operations, downtime


def validate_before_load(
    jobs: pd.DataFrame,
    operations: pd.DataFrame,
    downtime: pd.DataFrame,
) -> None:
    """Refuse to alter the database unless every CSV validation passes."""
    errors = [
        *validate_jobs(jobs),
        *validate_operations(operations),
        *validate_downtime(downtime),
        *validate_cross_dataset(jobs, operations, downtime),
    ]
    if errors:
        raise ValueError(
            "CSV validation failed; database was not modified:\n- "
            + "\n- ".join(errors)
        )


def clear_generated_tables(connection) -> None:
    """Clear generated tables and reset their identity sequences atomically."""
    # Foreign-key-related tables must share one PostgreSQL TRUNCATE command.
    # CASCADE is omitted so reference tables and unexpected dependents stay safe.
    connection.execute(
        text(
            "TRUNCATE TABLE job_operations, downtime_events, jobs "
            "RESTART IDENTITY"
        )
    )


def append_in_batches(
    data: pd.DataFrame, table_name: str, connection
) -> None:
    """Append a dataframe efficiently without replacing the existing table."""
    data.to_sql(
        name=table_name,
        con=connection,
        if_exists="append",
        index=False,
        chunksize=BATCH_SIZE,
        method="multi",
    )


def load_datasets(
    connection,
    jobs: pd.DataFrame,
    operations: pd.DataFrame,
    downtime: pd.DataFrame,
) -> None:
    """Load generated data in foreign-key-safe order."""
    append_in_batches(jobs, "jobs", connection)
    append_in_batches(operations, "job_operations", connection)
    append_in_batches(downtime, "downtime_events", connection)


def query_and_verify_counts(connection) -> dict[str, int]:
    """Query final table counts and verify referential integrity."""
    counts = {
        table: int(
            connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        )
        for table in EXPECTED_COUNTS
    }

    mismatches = [
        f"{table}: expected {expected:,}, found {counts[table]:,}"
        for table, expected in EXPECTED_COUNTS.items()
        if counts[table] != expected
    ]
    orphan_count = int(
        connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM job_operations AS operation "
                "LEFT JOIN jobs AS job ON job.job_id = operation.job_id "
                "WHERE job.job_id IS NULL"
            )
        ).scalar_one()
    )
    if orphan_count:
        mismatches.append(
            f"job_operations: found {orphan_count:,} rows without a matching job"
        )
    if mismatches:
        raise ValueError("Database verification failed:\n- " + "\n- ".join(mismatches))
    return counts


def print_success_report(counts: dict[str, int]) -> None:
    """Print final database row counts without exposing connection secrets."""
    print("Database load completed successfully")
    print(f"Jobs: {counts['jobs']:,}")
    print(f"Job operations: {counts['job_operations']:,}")
    print(f"Downtime events: {counts['downtime_events']:,}")
    print(f"Products: {counts['products']:,}")
    print(f"Machines: {counts['machines']:,}")
    print("Job-operation references valid: YES")


def main() -> None:
    """Validate CSVs, load them in one transaction, and verify the result."""
    engine: Engine | None = None
    try:
        jobs, operations, downtime = read_csv_datasets()
        validate_before_load(jobs, operations, downtime)
        settings = load_database_settings()
        engine = create_database_engine(settings)

        # The block commits only after loading and verification succeed. Any
        # exception rolls back the table clear and all inserts together.
        with engine.begin() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            print("PostgreSQL connection verified.")
            clear_generated_tables(connection)
            load_datasets(connection, jobs, operations, downtime)
            counts = query_and_verify_counts(connection)

        print_success_report(counts)
    except (FileNotFoundError, ValueError, SQLAlchemyError) as error:
        print(f"Database load failed; transaction rolled back: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
