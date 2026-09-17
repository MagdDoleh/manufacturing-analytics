# Phase 8 Root-Cause Analysis: Late Production Jobs

## Scope

This investigation examined delivery performance in the project's synthetic
manufacturing dataset. Job completion was defined as the latest operation
`end_time` for each job and compared with `jobs.due_at`. The analysis identifies
associations in synthetic data; it does not establish causation in a real
manufacturing environment.

## Problem Statement

Of 30,000 jobs, 28,863 finished on time and 1,137 finished late. Overall delivery
performance was **96.21% on time** and **3.79% late**.

## Investigation Results

### Product

| Product | Late rate |
| --- | ---: |
| PROD-A | 4.06% |
| PROD-C | 3.67% |
| PROD-B | 3.63% |

Lateness is distributed fairly evenly across products, so product type does not
appear to be a major driver.

### Waiting and processing

| Delivery status | Average wait per operation | Average processing per operation |
| --- | ---: | ---: |
| On-Time | 57.09 minutes | 139.19 minutes |
| Late | 67.62 minutes | 233.79 minutes |

Late jobs waited about 10.5 minutes longer per operation on average, indicating
that waiting contributes to lateness but does not by itself explain the full
difference. Processing time showed a substantially stronger relationship with
late delivery.

### Production quantity

On-Time jobs averaged **266.88 units**, while Late jobs averaged **446.52
units**. Processing time rose strongly with quantity, while waiting time remained
nearly constant.

| Quantity range | Avg. processing | Avg. waiting | Avg. deadline allowance | Late jobs | Late rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1-100 | 39.03 min | 57.52 min | 70.45 hr | 0 | 0.00% |
| 101-200 | 78.13 min | 57.72 min | 72.16 hr | 0 | 0.00% |
| 201-300 | 130.57 min | 57.53 min | 72.03 hr | 0 | 0.00% |
| 301-400 | 182.94 min | 57.29 min | 71.58 hr | 133 | 2.00% |
| 401-500 | 234.94 min | 57.40 min | 72.19 hr | 1,004 | 15.36% |

Deadline allowance remained roughly 72 hours regardless of batch quantity. At
the same time, average processing time increased from 39.03 minutes per operation
in the smallest range to 234.94 minutes in the largest. **1,004 of the 1,137 late
jobs (88.30%) occurred in the 401-500 quantity range.**

## Root-Cause Finding

The strongest finding is a workload/deadline mismatch: larger production batches
require substantially more processing time, but the synthetic scheduling and
data-generation logic gives jobs approximately the same deadline allowance
regardless of batch quantity. This mismatch is strongly associated with the
observed late jobs, particularly in the 401-500 range.

Because this analysis uses synthetic project data, the result should be treated
as an identified relationship within the model—not proof of causation or evidence
about an actual semiconductor factory. No corrective action has yet been tested.
