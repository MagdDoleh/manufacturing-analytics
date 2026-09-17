"""Run the project's reproducible synthetic-data ETL pipeline."""

import sys
from collections.abc import Callable
from time import perf_counter

import generate_downtime
import generate_jobs
import generate_operations
import load_database


PIPELINE_STAGES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("Generating jobs", generate_jobs.main),
    ("Generating job operations", generate_operations.main),
    ("Generating downtime events", generate_downtime.main),
    ("Validating and loading PostgreSQL", load_database.main),
)


def run_pipeline() -> int:
    """Execute each ETL stage in order, stopping immediately on failure."""
    pipeline_start = perf_counter()
    stage_count = len(PIPELINE_STAGES)

    for stage_number, (stage_name, stage_main) in enumerate(
        PIPELINE_STAGES, start=1
    ):
        print(f"[{stage_number}/{stage_count}] {stage_name}...", flush=True)
        try:
            stage_main()
        except SystemExit as error:
            exit_code = error.code if isinstance(error.code, int) else 1
            if exit_code == 0:
                continue
            print(
                f"Pipeline failed during stage {stage_number}: {stage_name}.",
                file=sys.stderr,
            )
            return exit_code
        except Exception as error:
            print(
                f"Pipeline failed during stage {stage_number}: {stage_name} "
                f"({type(error).__name__}).",
                file=sys.stderr,
            )
            return 1

    elapsed_seconds = perf_counter() - pipeline_start
    print(
        f"Pipeline completed successfully in {elapsed_seconds:.2f} seconds."
    )
    return 0


def main() -> int:
    """Run the full ETL pipeline and return a process exit code."""
    return run_pipeline()


if __name__ == "__main__":
    raise SystemExit(main())
