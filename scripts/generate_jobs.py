"""Generate a reproducible synthetic production-jobs dataset."""

from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 2026
JOB_COUNT = 30_000
PERIOD_START = pd.Timestamp("2026-01-01 00:00:00")
PERIOD_DAYS = 90
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "jobs.csv"


def generate_jobs(job_count: int = JOB_COUNT, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Return synthetic production jobs generated from a fixed random seed."""
    rng = np.random.default_rng(seed)

    # Sample to the second across the full 90-day period.
    period_seconds = PERIOD_DAYS * 24 * 60 * 60
    created_offsets = rng.integers(0, period_seconds, size=job_count)
    created_at = PERIOD_START + pd.to_timedelta(created_offsets, unit="s")

    jobs = pd.DataFrame(
        {
            "job_code": [f"JOB-{number:06d}" for number in range(1, job_count + 1)],
            "product_id": rng.choice([1, 2, 3], size=job_count),
            "quantity": rng.integers(50, 501, size=job_count),
            "priority": rng.choice(
                ["Standard", "High"], size=job_count, p=[0.85, 0.15]
            ),
            "status": "Queued",
            "created_at": created_at,
            "due_at": created_at
            + pd.to_timedelta(rng.integers(1, 6, size=job_count), unit="D"),
        }
    )

    return jobs


def validate_jobs(jobs: pd.DataFrame) -> None:
    """Raise ValueError when the generated dataset violates its requirements."""
    if len(jobs) != JOB_COUNT:
        raise ValueError(f"Expected {JOB_COUNT:,} rows, generated {len(jobs):,}.")
    if (jobs["quantity"] <= 0).any():
        raise ValueError("All job quantities must be positive.")
    if (jobs["due_at"] <= jobs["created_at"]).any():
        raise ValueError("Every due_at timestamp must be after created_at.")
    if not jobs["job_code"].is_unique:
        raise ValueError("Job codes must be unique.")


def save_jobs(jobs: pd.DataFrame, output_path: Path = OUTPUT_PATH) -> None:
    """Write jobs to CSV, creating the output directory when necessary."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(output_path, index=False, date_format="%Y-%m-%d %H:%M:%S")


def main() -> None:
    """Generate, validate, and save the production-jobs dataset."""
    jobs = generate_jobs()
    validate_jobs(jobs)
    save_jobs(jobs)
    print(f"Generated {len(jobs):,} jobs at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
