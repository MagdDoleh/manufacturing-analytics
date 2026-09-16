"""Generate sequential manufacturing operations for synthetic production jobs."""

from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 2026
EXPECTED_JOB_COUNT = 30_000
OPERATIONS_PER_JOB = 5
EXPECTED_OPERATION_COUNT = EXPECTED_JOB_COUNT * OPERATIONS_PER_JOB

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = PROJECT_ROOT / "data" / "jobs.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "job_operations.csv"

WORK_CENTER_MACHINES = {
    1: np.array([1, 2, 3]),
    2: np.array([4, 5, 6]),
    3: np.array([7, 8, 9]),
    4: np.array([10, 11, 12]),
    5: np.array([13, 14, 15]),
}

MACHINE_CAPACITY_PER_HOUR = {
    1: 120,
    2: 110,
    3: 125,
    4: 100,
    5: 105,
    6: 95,
    7: 90,
    8: 100,
    9: 95,
    10: 150,
    11: 140,
    12: 155,
    13: 130,
    14: 125,
    15: 135,
}


def load_jobs(path: Path = JOBS_PATH) -> pd.DataFrame:
    """Load jobs and assign stable job IDs based on their CSV row order."""
    jobs = pd.read_csv(path, parse_dates=["created_at"])
    required_columns = {"quantity", "priority", "created_at"}
    missing_columns = required_columns.difference(jobs.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Jobs file is missing required columns: {missing}.")
    if len(jobs) != EXPECTED_JOB_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_JOB_COUNT:,} jobs, found {len(jobs):,}."
        )

    jobs = jobs.copy()
    jobs.insert(0, "job_id", np.arange(1, len(jobs) + 1, dtype=np.int64))
    return jobs


def generate_queue_waits(
    priorities: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Generate positive queue waits, favoring High-priority jobs."""
    high_priority = priorities == "High"
    waits = np.empty(len(priorities), dtype=np.int64)
    waits[high_priority] = rng.integers(2, 31, size=high_priority.sum())
    waits[~high_priority] = rng.integers(10, 121, size=(~high_priority).sum())
    return waits


def generate_operations(
    jobs: pd.DataFrame, seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """Generate five ordered operations for each job."""
    rng = np.random.default_rng(seed)
    operation_frames: list[pd.DataFrame] = []
    arrival_time = jobs["created_at"].reset_index(drop=True)
    quantities = jobs["quantity"].to_numpy()
    priorities = jobs["priority"].to_numpy()

    for work_center_id in range(1, OPERATIONS_PER_JOB + 1):
        machine_ids = rng.choice(WORK_CENTER_MACHINES[work_center_id], size=len(jobs))
        capacities = np.fromiter(
            (MACHINE_CAPACITY_PER_HOUR[machine] for machine in machine_ids),
            dtype=float,
            count=len(machine_ids),
        )

        wait_minutes = generate_queue_waits(priorities, rng)
        # Capacity gives the baseline duration; bounded noise represents normal
        # process variation without allowing zero or negative durations.
        variation = rng.uniform(0.90, 1.10, size=len(jobs))
        processing_seconds = np.maximum(
            1, np.ceil((quantities / capacities) * 60 * 60 * variation)
        ).astype(np.int64)
        processing_minutes = processing_seconds / 60.0

        start_time = arrival_time + pd.to_timedelta(wait_minutes, unit="m")
        end_time = start_time + pd.to_timedelta(processing_seconds, unit="s")

        operation_frames.append(
            pd.DataFrame(
                {
                    "job_id": jobs["job_id"].to_numpy(),
                    "work_center_id": work_center_id,
                    "machine_id": machine_ids,
                    "operation_sequence": work_center_id,
                    "arrival_time": arrival_time,
                    "start_time": start_time,
                    "end_time": end_time,
                    "wait_time_minutes": wait_minutes,
                    "processing_time_minutes": np.round(processing_minutes, 2),
                    "status": "Completed",
                }
            )
        )

        if work_center_id < OPERATIONS_PER_JOB:
            transfer_minutes = rng.integers(5, 31, size=len(jobs))
            arrival_time = end_time + pd.to_timedelta(transfer_minutes, unit="m")

    operations = pd.concat(operation_frames, ignore_index=True)
    return operations.sort_values(
        ["job_id", "operation_sequence"], ignore_index=True
    )


def validate_operations(operations: pd.DataFrame) -> None:
    """Raise ValueError if any operation-generation rule is violated."""
    if len(operations) != EXPECTED_OPERATION_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_OPERATION_COUNT:,} rows, generated "
            f"{len(operations):,}."
        )

    counts = operations.groupby("job_id")["operation_sequence"].count()
    if len(counts) != EXPECTED_JOB_COUNT or not counts.eq(OPERATIONS_PER_JOB).all():
        raise ValueError("Every job must have exactly five operations.")

    expected_sequences = np.arange(1, OPERATIONS_PER_JOB + 1)
    actual_sequences = operations["operation_sequence"].to_numpy().reshape(
        -1, OPERATIONS_PER_JOB
    )
    if not np.all(actual_sequences == expected_sequences):
        raise ValueError("Every job must contain operation sequences 1 through 5.")

    valid_machine = np.fromiter(
        (
            machine in WORK_CENTER_MACHINES[work_center]
            for work_center, machine in zip(
                operations["work_center_id"], operations["machine_id"]
            )
        ),
        dtype=bool,
        count=len(operations),
    )
    if not valid_machine.all():
        raise ValueError("A machine was assigned to the wrong work center.")

    if (operations["start_time"] < operations["arrival_time"]).any():
        raise ValueError("start_time cannot be before arrival_time.")
    if (operations["end_time"] <= operations["start_time"]).any():
        raise ValueError("end_time must be after start_time.")
    if (operations[["wait_time_minutes", "processing_time_minutes"]] < 0).any().any():
        raise ValueError("Wait and processing times must be non-negative.")

    previous_end = operations.groupby("job_id")["end_time"].shift()
    later_operations = operations["operation_sequence"] > 1
    if (operations.loc[later_operations, "arrival_time"] < previous_end[later_operations]).any():
        raise ValueError("A later operation occurs before the prior operation finishes.")

    if operations.duplicated(["job_id", "operation_sequence"]).any():
        raise ValueError("Duplicate job_id and operation_sequence pairs found.")


def save_operations(
    operations: pd.DataFrame, output_path: Path = OUTPUT_PATH
) -> None:
    """Save operation records as a PostgreSQL-friendly CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    operations.to_csv(
        output_path, index=False, date_format="%Y-%m-%d %H:%M:%S"
    )


def main() -> None:
    """Load jobs, generate and validate operations, then write the CSV."""
    jobs = load_jobs()
    operations = generate_operations(jobs)
    validate_operations(operations)
    save_operations(operations)
    print(f"Generated {len(operations):,} operations at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
