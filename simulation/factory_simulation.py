"""Discrete-event simulation for factory capacity and scheduling scenarios."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import random

import simpy


RANDOM_SEED = 2026
BASELINE_JOB_COUNT = 100
JOB_ARRIVAL_INTERVAL_MINUTES = 12.0
DEFAULT_MACHINES_PER_WORK_CENTER = 3
SCHEDULING_COMPARISON_VARIATION = 0.25
HIGH_PRIORITY_PROBABILITY = 0.15
PRIORITY_RANDOM_SEED_OFFSET = 1

# Fixed baseline processing times in minutes. Scheduling comparisons can add
# seeded job-level variation without changing the original capacity experiment.
WORK_CENTER_PROCESSING_TIMES = {
    "Photolithography": 45.0,
    "Etching": 35.0,
    "Deposition": 40.0,
    "Inspection": 20.0,
    "Testing": 30.0,
}

DEFAULT_WORK_CENTER_CAPACITIES = {
    work_center: DEFAULT_MACHINES_PER_WORK_CENTER
    for work_center in WORK_CENTER_PROCESSING_TIMES
}

# Pass this partial override to FactorySimulation to evaluate the requested
# capacity scenario while every unlisted work center remains at its default.
PHOTOLITHOGRAPHY_4_MACHINE_SCENARIO = {"Photolithography": 4}


class SchedulingPolicy(str, Enum):
    """Supported non-preemptive work-center queue disciplines."""

    FIFO = "FIFO"
    SPT = "SPT"
    PRIORITY = "Priority"


@dataclass
class OperationRecord:
    """Timing details for one job at one work center."""

    work_center: str
    arrival_time: float
    waiting_time: float
    processing_time: float
    start_time: float
    completion_time: float


@dataclass
class JobRecord:
    """System-level and operation-level timing details for a job."""

    job_id: int
    arrival_time: float
    priority: str
    required_processing_times: dict[str, float]
    operations: list[OperationRecord] = field(default_factory=list)
    completion_time: float | None = None
    total_cycle_time: float | None = None


class WorkCenter:
    """A manufacturing stage backed by configurable parallel SimPy machines."""

    def __init__(
        self,
        environment: simpy.Environment,
        name: str,
        processing_time: float,
        capacity: int,
        scheduling_policy: SchedulingPolicy,
    ) -> None:
        self.name = name
        self.processing_time = processing_time
        self.capacity = capacity
        self.scheduling_policy = scheduling_policy
        resource_class = (
            simpy.PriorityResource
            if scheduling_policy in (SchedulingPolicy.SPT, SchedulingPolicy.PRIORITY)
            else simpy.Resource
        )
        self.machines = resource_class(environment, capacity=capacity)

    def request_machine(self, required_processing_time: float, job_priority: str):
        """Create a queue request using this work center's scheduling policy."""
        if self.scheduling_policy is SchedulingPolicy.SPT:
            return self.machines.request(priority=required_processing_time)
        if self.scheduling_policy is SchedulingPolicy.PRIORITY:
            # SimPy serves lower values first and preserves request order for
            # equal values, giving FIFO behavior within each priority level.
            queue_priority = 0 if job_priority == "High" else 1
            return self.machines.request(priority=queue_priority)
        return self.machines.request()


class FactorySimulation:
    """Coordinate job arrivals and sequential processing through the factory."""

    def __init__(
        self,
        random_seed: int = RANDOM_SEED,
        work_center_capacities: Mapping[str, int] | None = None,
        scheduling_policy: SchedulingPolicy | str = SchedulingPolicy.FIFO,
        processing_time_variation: float = 0.0,
    ) -> None:
        self.environment = simpy.Environment()
        self.random_generator = random.Random(random_seed)
        # A separate deterministic stream adds priorities without changing the
        # existing FIFO/SPT processing-time workload for the same random seed.
        self.priority_random_generator = random.Random(
            random_seed + PRIORITY_RANDOM_SEED_OFFSET
        )
        self.scheduling_policy = SchedulingPolicy(scheduling_policy)
        if not 0.0 <= processing_time_variation < 1.0:
            raise ValueError("processing_time_variation must be between 0 and 1.")
        self.processing_time_variation = processing_time_variation
        self.work_center_capacities = build_work_center_capacities(
            work_center_capacities
        )
        self.work_centers = [
            WorkCenter(
                self.environment,
                name,
                processing_time,
                capacity=self.work_center_capacities[name],
                scheduling_policy=self.scheduling_policy,
            )
            for name, processing_time in WORK_CENTER_PROCESSING_TIMES.items()
        ]
        self.jobs: list[JobRecord] = []

    def process_job(self, job: JobRecord):
        """Move one job through all five work centers in order."""
        for work_center in self.work_centers:
            operation_arrival = self.environment.now
            processing_time = job.required_processing_times[work_center.name]

            with work_center.request_machine(
                processing_time, job.priority
            ) as machine_request:
                yield machine_request
                start_time = self.environment.now
                waiting_time = start_time - operation_arrival

                yield self.environment.timeout(processing_time)
                completion_time = self.environment.now

            job.operations.append(
                OperationRecord(
                    work_center=work_center.name,
                    arrival_time=operation_arrival,
                    waiting_time=waiting_time,
                    processing_time=processing_time,
                    start_time=start_time,
                    completion_time=completion_time,
                )
            )

        job.completion_time = self.environment.now
        job.total_cycle_time = job.completion_time - job.arrival_time

    def generate_jobs(
        self,
        job_count: int,
        arrival_interval: float,
    ):
        """Generate jobs at a fixed interval and start their factory processes."""
        for job_id in range(1, job_count + 1):
            required_processing_times = {
                work_center: baseline_time
                * self.random_generator.uniform(
                    1.0 - self.processing_time_variation,
                    1.0 + self.processing_time_variation,
                )
                for work_center, baseline_time in WORK_CENTER_PROCESSING_TIMES.items()
            }
            job = JobRecord(
                job_id=job_id,
                arrival_time=self.environment.now,
                priority=(
                    "High"
                    if self.priority_random_generator.random()
                    < HIGH_PRIORITY_PROBABILITY
                    else "Standard"
                ),
                required_processing_times=required_processing_times,
            )
            self.jobs.append(job)
            self.environment.process(self.process_job(job))

            if job_id < job_count:
                yield self.environment.timeout(arrival_interval)

    def run(
        self,
        job_count: int = BASELINE_JOB_COUNT,
        arrival_interval: float = JOB_ARRIVAL_INTERVAL_MINUTES,
    ) -> list[JobRecord]:
        """Run the factory until all generated jobs have completed."""
        self.environment.process(self.generate_jobs(job_count, arrival_interval))
        self.environment.run()
        return self.jobs


def build_work_center_capacities(
    overrides: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Merge partial capacity overrides into the three-machine baseline."""
    capacities = DEFAULT_WORK_CENTER_CAPACITIES.copy()
    if overrides is None:
        return capacities

    unknown_work_centers = set(overrides).difference(capacities)
    if unknown_work_centers:
        unknown = ", ".join(sorted(unknown_work_centers))
        raise ValueError(f"Unknown work center capacity override: {unknown}")

    for work_center, capacity in overrides.items():
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError(
                f"Capacity for {work_center} must be a positive integer."
            )
        capacities[work_center] = capacity
    return capacities


def calculate_summary(jobs: list[JobRecord]) -> dict[str, object]:
    """Calculate completion, cycle-time, and work-center waiting metrics."""
    completed_jobs = [job for job in jobs if job.completion_time is not None]
    if not completed_jobs:
        raise ValueError("The simulation completed without producing any jobs.")

    average_cycle_time = sum(
        job.total_cycle_time for job in completed_jobs if job.total_cycle_time is not None
    ) / len(completed_jobs)

    waits_by_work_center = {
        work_center: [
            operation.waiting_time
            for job in completed_jobs
            for operation in job.operations
            if operation.work_center == work_center
        ]
        for work_center in WORK_CENTER_PROCESSING_TIMES
    }
    average_waits = {
        work_center: sum(wait_times) / len(wait_times)
        for work_center, wait_times in waits_by_work_center.items()
    }
    cycle_times_by_priority = {
        priority: [
            job.total_cycle_time
            for job in completed_jobs
            if job.priority == priority and job.total_cycle_time is not None
        ]
        for priority in ("High", "Standard")
    }
    average_cycle_time_by_priority = {
        priority: sum(cycle_times) / len(cycle_times)
        for priority, cycle_times in cycle_times_by_priority.items()
        if cycle_times
    }

    return {
        "jobs_completed": len(completed_jobs),
        "average_cycle_time": average_cycle_time,
        "average_wait_by_work_center": average_waits,
        "average_cycle_time_by_priority": average_cycle_time_by_priority,
    }


def print_summary(
    summary: dict[str, object], scenario_name: str = "Baseline factory simulation"
) -> None:
    """Print concise simulation metrics in minutes."""
    print(scenario_name)
    print(f"Jobs completed: {summary['jobs_completed']}")
    print(f"Average cycle time: {summary['average_cycle_time']:.2f} minutes")
    print("Average wait time by work center:")

    average_waits = summary["average_wait_by_work_center"]
    for work_center, average_wait in average_waits.items():
        print(f"  {work_center}: {average_wait:.2f} minutes")

    print("Average cycle time by job priority:")
    priority_cycle_times = summary["average_cycle_time_by_priority"]
    for priority in ("High", "Standard"):
        if priority in priority_cycle_times:
            print(f"  {priority}: {priority_cycle_times[priority]:.2f} minutes")


def run_scenario(
    scenario_name: str,
    work_center_capacities: Mapping[str, int] | None = None,
    scheduling_policy: SchedulingPolicy | str = SchedulingPolicy.FIFO,
    processing_time_variation: float = 0.0,
) -> dict[str, object]:
    """Run a named scenario with configurable capacity and queue discipline."""
    simulation = FactorySimulation(
        random_seed=RANDOM_SEED,
        work_center_capacities=work_center_capacities,
        scheduling_policy=scheduling_policy,
        processing_time_variation=processing_time_variation,
    )
    jobs = simulation.run(
        job_count=BASELINE_JOB_COUNT,
        arrival_interval=JOB_ARRIVAL_INTERVAL_MINUTES,
    )
    summary = calculate_summary(jobs)
    print_summary(summary, scenario_name=scenario_name)
    return summary


def main() -> None:
    """Compare scheduling policies, then retain the capacity experiment."""

    run_scenario(
        "FIFO baseline: 3 machines per work center",
        scheduling_policy=SchedulingPolicy.FIFO,
        processing_time_variation=SCHEDULING_COMPARISON_VARIATION,
    )

    print("\n" + "=" * 50 + "\n")

    run_scenario(
        "SPT scenario: 3 machines per work center",
        scheduling_policy=SchedulingPolicy.SPT,
        processing_time_variation=SCHEDULING_COMPARISON_VARIATION,
    )

    print("\n" + "=" * 50 + "\n")

    run_scenario(
        "Priority scenario: 3 machines per work center",
        scheduling_policy=SchedulingPolicy.PRIORITY,
        processing_time_variation=SCHEDULING_COMPARISON_VARIATION,
    )

    print("\n" + "=" * 50 + "\n")

    run_scenario(
        "FIFO capacity experiment: Photolithography has 4 machines",
        work_center_capacities=PHOTOLITHOGRAPHY_4_MACHINE_SCENARIO,
        scheduling_policy=SchedulingPolicy.FIFO,
    )


if __name__ == "__main__":
    main()
