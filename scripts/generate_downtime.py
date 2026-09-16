"""Generate reproducible synthetic downtime events for manufacturing machines."""

from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 2026
MACHINE_IDS = np.arange(1, 16)
PERIOD_START = pd.Timestamp("2026-01-01 00:00:00")
PERIOD_END = PERIOD_START + pd.Timedelta(days=90)
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "downtime_events.csv"
)

REASONS = np.array(
    [
        "Preventive Maintenance",
        "Equipment Failure",
        "Calibration",
        "Sensor Fault",
        "Cleaning",
    ]
)
REASON_PROBABILITIES = np.array([0.25, 0.20, 0.20, 0.15, 0.20])
REASON_DURATION_RANGES = {
    "Preventive Maintenance": (120, 480),
    "Equipment Failure": (240, 1_440),
    "Calibration": (30, 120),
    "Sensor Fault": (45, 240),
    "Cleaning": (30, 90),
}


def events_overlap(
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
    existing_events: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> bool:
    """Return whether an interval overlaps any existing machine interval."""
    return any(
        start_time < existing_end and end_time > existing_start
        for existing_start, existing_end in existing_events
    )


def generate_machine_events(
    machine_id: int,
    event_count: int,
    duration_factor: float,
    rng: np.random.Generator,
) -> list[dict]:
    """Generate non-overlapping downtime events for one machine."""
    events: list[dict] = []
    occupied_intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    period_minutes = int((PERIOD_END - PERIOD_START).total_seconds() // 60)

    for _ in range(event_count):
        reason = str(rng.choice(REASONS, p=REASON_PROBABILITIES))
        minimum, maximum = REASON_DURATION_RANGES[reason]
        downtime_minutes = max(
            1, int(round(rng.integers(minimum, maximum + 1) * duration_factor))
        )

        # Overall utilization is low enough that rejection sampling remains fast
        # while allowing events to occur uniformly throughout the 90-day period.
        for _attempt in range(1_000):
            latest_start = period_minutes - downtime_minutes
            start_offset = int(rng.integers(0, latest_start + 1))
            start_time = PERIOD_START + pd.Timedelta(minutes=start_offset)
            end_time = start_time + pd.Timedelta(minutes=downtime_minutes)

            if not events_overlap(start_time, end_time, occupied_intervals):
                occupied_intervals.append((start_time, end_time))
                events.append(
                    {
                        "machine_id": machine_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "reason": reason,
                        "downtime_minutes": downtime_minutes,
                    }
                )
                break
        else:
            raise RuntimeError(
                f"Could not schedule a non-overlapping event for machine {machine_id}."
            )

    return events


def generate_downtime(seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Generate downtime events with machine-specific frequency and duration."""
    rng = np.random.default_rng(seed)
    records: list[dict] = []

    # Machine-specific rates and duration factors create realistic differences in
    # reliability and repair time while guaranteeing multiple events per machine.
    expected_event_counts = rng.integers(9, 21, size=len(MACHINE_IDS))
    event_counts = np.maximum(3, rng.poisson(expected_event_counts))
    duration_factors = rng.uniform(0.80, 1.25, size=len(MACHINE_IDS))

    for machine_id, event_count, duration_factor in zip(
        MACHINE_IDS, event_counts, duration_factors
    ):
        records.extend(
            generate_machine_events(
                int(machine_id), int(event_count), float(duration_factor), rng
            )
        )

    return pd.DataFrame(records).sort_values(
        ["machine_id", "start_time"], ignore_index=True
    )


def validate_downtime(events: pd.DataFrame) -> None:
    """Raise ValueError when generated downtime violates a required rule."""
    if events.empty:
        raise ValueError("No downtime events were generated.")
    if not events["machine_id"].between(1, 15).all():
        raise ValueError("All machine IDs must be between 1 and 15.")
    if not events.groupby("machine_id").size().reindex(MACHINE_IDS, fill_value=0).gt(1).all():
        raise ValueError("Every machine must have multiple downtime events.")
    if (events["downtime_minutes"] <= 0).any():
        raise ValueError("Every downtime duration must be positive.")
    if (events["end_time"] <= events["start_time"]).any():
        raise ValueError("Every end_time must be after start_time.")

    calculated_minutes = (
        (events["end_time"] - events["start_time"]).dt.total_seconds() / 60
    )
    if not np.allclose(events["downtime_minutes"], calculated_minutes):
        raise ValueError("downtime_minutes does not match the event timestamps.")
    if (events["start_time"] < PERIOD_START).any() or (
        events["end_time"] > PERIOD_END
    ).any():
        raise ValueError("All events must fall within the 90-day period.")

    previous_end = events.groupby("machine_id")["end_time"].shift()
    if (events["start_time"] < previous_end).fillna(False).any():
        raise ValueError("Overlapping downtime events found for a machine.")


def save_downtime(events: pd.DataFrame, output_path: Path = OUTPUT_PATH) -> None:
    """Save downtime events in a PostgreSQL-friendly CSV format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(output_path, index=False, date_format="%Y-%m-%d %H:%M:%S")


def print_summary(events: pd.DataFrame) -> None:
    """Print the requested downtime summary statistics."""
    total_hours = events["downtime_minutes"].sum() / 60
    counts_by_reason = events["reason"].value_counts().sort_index()
    hours_by_machine = (
        events.groupby("machine_id")["downtime_minutes"].sum() / 60
    )

    print(f"Total downtime events: {len(events):,}")
    print(f"Total downtime hours: {total_hours:,.2f}")
    print("\nDowntime event count by reason:")
    print(counts_by_reason.to_string())
    print("\nTotal downtime hours by machine:")
    for machine_id, hours in hours_by_machine.items():
        print(f"Machine {machine_id:>2}: {hours:,.2f}")


def main() -> None:
    """Generate, validate, save, and summarize machine downtime events."""
    events = generate_downtime()
    validate_downtime(events)
    save_downtime(events)
    print_summary(events)
    print(f"\nSaved downtime events to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
