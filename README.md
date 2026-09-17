# Manufacturing Analytics & Scheduling System

A data-driven manufacturing analytics project using PostgreSQL, Python, Power BI, simulation, and scheduling optimization.

## Status

Currently under development.

## Automated ETL Pipeline

The project's complete synthetic-data workflow can be reproduced with one
command:

```bash
python scripts/run_pipeline.py
```

The command generates jobs → generates operations → generates downtime →
validates and loads the datasets into PostgreSQL → verifies the final database
counts. It is a reproducible automated ETL workflow for this project, not an
enterprise production orchestration system.

## Root-Cause Analysis

Phase 8 investigated 1,137 late jobs among 30,000 records in the project's
synthetic manufacturing dataset. Product late rates were similar, while late jobs
had substantially higher processing times and quantities than On-Time jobs.

| Quantity range | Avg. processing per operation | Late rate |
| --- | ---: | ---: |
| 1-100 | 39.03 minutes | 0.00% |
| 101-200 | 78.13 minutes | 0.00% |
| 201-300 | 130.57 minutes | 0.00% |
| 301-400 | 182.94 minutes | 2.00% |
| 401-500 | 234.94 minutes | 15.36% |

The strongest finding is a workload/deadline mismatch: processing time increases
sharply with batch quantity, but deadline allowance remains approximately 72
hours across all quantity ranges. This relationship is strongly associated with
lateness—1,004 of the 1,137 late jobs are in the 401-500 range. These findings
come from synthetic data and do not establish real-world causation. A corrective
action has not yet been tested.

## Simulation Experiments

The first experiment modeled 100 jobs moving through five work centers in a
synthetic discrete-event manufacturing simulation.

| Scenario | Jobs completed | Average cycle time | Key average waits |
| --- | ---: | ---: | --- |
| Baseline (3 machines per work center) | 100 | 315.53 minutes | Photolithography: 145.53 minutes; other work centers: approximately 0 minutes |
| Photolithography capacity increase (4 machines; all others unchanged) | 100 | 234.68 minutes | Photolithography: 0 minutes; Deposition: 64.68 minutes |

Increasing capacity at the original Photolithography bottleneck reduced average
cycle time by **25.62%**, but shifted the bottleneck downstream to Deposition.

### Scheduling Comparison

FIFO, Shortest Processing Time (SPT), and Priority scheduling were compared using
the same seeded 100-job workload and three machines per work center.

| Scheduling policy | Jobs completed | Average cycle time | High-priority cycle time | Standard cycle time |
| --- | ---: | ---: | ---: | ---: |
| FIFO | 100 | 308.47 minutes | 276.09 minutes | 312.88 minutes |
| SPT | 100 | 289.93 minutes | 311.70 minutes | 286.96 minutes |
| Priority | 100 | 309.95 minutes | 180.06 minutes | 327.67 minutes |

SPT produced the lowest overall average cycle time, improving it by approximately
**6%** compared with FIFO. Priority scheduling dramatically reduced cycle time
for High-priority jobs, but increased it for Standard jobs. This illustrates the
tradeoff between optimizing overall system performance and prioritizing urgent
work.

The scheduling results also come from a synthetic discrete-event manufacturing
simulation and should not be interpreted as real-factory performance.

These results are from a synthetic baseline model and do not represent the
performance of a real semiconductor factory.
