/*
Phase 8 delivery root-cause analysis

Job completion is derived consistently as the latest operation end_time for
each job. A job is Late only when that completion time is after jobs.due_at.
*/


-- Hypothesis: establish the size of the delivery-performance problem.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
)
SELECT
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE jc.completion_time <= j.due_at) AS on_time_jobs,
    COUNT(*) FILTER (WHERE jc.completion_time > j.due_at) AS late_jobs,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE jc.completion_time <= j.due_at)
        / NULLIF(COUNT(*), 0),
        2
    ) AS on_time_percentage,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE jc.completion_time > j.due_at)
        / NULLIF(COUNT(*), 0),
        2
    ) AS late_percentage
FROM jobs AS j
JOIN job_completion AS jc
    ON jc.job_id = j.job_id;


-- Hypothesis: one product may account for a disproportionate share of lateness.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
)
SELECT
    p.product_id,
    p.product_code,
    p.product_name,
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE jc.completion_time > j.due_at) AS late_jobs,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE jc.completion_time > j.due_at)
        / NULLIF(COUNT(*), 0),
        2
    ) AS late_percentage
FROM jobs AS j
JOIN products AS p
    ON p.product_id = j.product_id
JOIN job_completion AS jc
    ON jc.job_id = j.job_id
GROUP BY
    p.product_id,
    p.product_code,
    p.product_name
ORDER BY late_percentage DESC, p.product_id;


-- Hypothesis: late jobs spend more time waiting in queues overall.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
),
job_outcomes AS (
    SELECT
        j.job_id,
        CASE
            WHEN jc.completion_time > j.due_at THEN 'Late'
            ELSE 'On-Time'
        END AS delivery_status
    FROM jobs AS j
    JOIN job_completion AS jc
        ON jc.job_id = j.job_id
)
SELECT
    outcome.delivery_status,
    ROUND(AVG(operation.wait_time_minutes)::numeric, 2) AS avg_wait_minutes
FROM job_outcomes AS outcome
JOIN job_operations AS operation
    ON operation.job_id = outcome.job_id
GROUP BY outcome.delivery_status
ORDER BY outcome.delivery_status;


-- Hypothesis: a specific work center's queue is associated with late jobs.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
),
job_outcomes AS (
    SELECT
        j.job_id,
        CASE
            WHEN jc.completion_time > j.due_at THEN 'Late'
            ELSE 'On-Time'
        END AS delivery_status
    FROM jobs AS j
    JOIN job_completion AS jc
        ON jc.job_id = j.job_id
)
SELECT
    operation.work_center_id,
    work_center.work_center_code,
    work_center.name AS work_center_name,
    outcome.delivery_status,
    ROUND(AVG(operation.wait_time_minutes)::numeric, 2) AS avg_wait_minutes
FROM job_outcomes AS outcome
JOIN job_operations AS operation
    ON operation.job_id = outcome.job_id
JOIN work_centers AS work_center
    ON work_center.work_center_id = operation.work_center_id
GROUP BY
    operation.work_center_id,
    work_center.work_center_code,
    work_center.name,
    outcome.delivery_status
ORDER BY operation.work_center_id, outcome.delivery_status;


-- Hypothesis: late jobs require more processing time per operation overall.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
),
job_outcomes AS (
    SELECT
        j.job_id,
        CASE
            WHEN jc.completion_time > j.due_at THEN 'Late'
            ELSE 'On-Time'
        END AS delivery_status
    FROM jobs AS j
    JOIN job_completion AS jc
        ON jc.job_id = j.job_id
)
SELECT
    outcome.delivery_status,
    ROUND(
        AVG(operation.processing_time_minutes)::numeric,
        2
    ) AS avg_processing_minutes
FROM job_outcomes AS outcome
JOIN job_operations AS operation
    ON operation.job_id = outcome.job_id
GROUP BY outcome.delivery_status
ORDER BY outcome.delivery_status;


-- Hypothesis: processing-time differences are concentrated at a work center.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
),
job_outcomes AS (
    SELECT
        j.job_id,
        CASE
            WHEN jc.completion_time > j.due_at THEN 'Late'
            ELSE 'On-Time'
        END AS delivery_status
    FROM jobs AS j
    JOIN job_completion AS jc
        ON jc.job_id = j.job_id
)
SELECT
    operation.work_center_id,
    work_center.work_center_code,
    work_center.name AS work_center_name,
    outcome.delivery_status,
    ROUND(
        AVG(operation.processing_time_minutes)::numeric,
        2
    ) AS avg_processing_minutes
FROM job_outcomes AS outcome
JOIN job_operations AS operation
    ON operation.job_id = outcome.job_id
JOIN work_centers AS work_center
    ON work_center.work_center_id = operation.work_center_id
GROUP BY
    operation.work_center_id,
    work_center.work_center_code,
    work_center.name,
    outcome.delivery_status
ORDER BY operation.work_center_id, outcome.delivery_status;


-- Hypothesis: late jobs have larger production quantities.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
)
SELECT
    CASE
        WHEN jc.completion_time > j.due_at THEN 'Late'
        ELSE 'On-Time'
    END AS delivery_status,
    ROUND(AVG(j.quantity)::numeric, 2) AS avg_quantity
FROM jobs AS j
JOIN job_completion AS jc
    ON jc.job_id = j.job_id
GROUP BY delivery_status
ORDER BY delivery_status;


-- Hypothesis: larger jobs receive more time between creation and due date.
WITH quantity_groups AS (
    SELECT
        job_id,
        created_at,
        due_at,
        CASE
            WHEN quantity BETWEEN 1 AND 100 THEN '1-100'
            WHEN quantity BETWEEN 101 AND 200 THEN '101-200'
            WHEN quantity BETWEEN 201 AND 300 THEN '201-300'
            WHEN quantity BETWEEN 301 AND 400 THEN '301-400'
            WHEN quantity BETWEEN 401 AND 500 THEN '401-500'
        END AS quantity_range,
        CASE
            WHEN quantity BETWEEN 1 AND 100 THEN 1
            WHEN quantity BETWEEN 101 AND 200 THEN 2
            WHEN quantity BETWEEN 201 AND 300 THEN 3
            WHEN quantity BETWEEN 301 AND 400 THEN 4
            WHEN quantity BETWEEN 401 AND 500 THEN 5
        END AS range_order
    FROM jobs
)
SELECT
    quantity_range,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (due_at - created_at)) / 3600.0)::numeric,
        2
    ) AS avg_deadline_allowance_hours
FROM quantity_groups
WHERE quantity_range IS NOT NULL
GROUP BY quantity_range, range_order
ORDER BY range_order;


-- Hypothesis: quantity primarily increases processing rather than queue time.
WITH quantity_groups AS (
    SELECT
        job_id,
        CASE
            WHEN quantity BETWEEN 1 AND 100 THEN '1-100'
            WHEN quantity BETWEEN 101 AND 200 THEN '101-200'
            WHEN quantity BETWEEN 201 AND 300 THEN '201-300'
            WHEN quantity BETWEEN 301 AND 400 THEN '301-400'
            WHEN quantity BETWEEN 401 AND 500 THEN '401-500'
        END AS quantity_range,
        CASE
            WHEN quantity BETWEEN 1 AND 100 THEN 1
            WHEN quantity BETWEEN 101 AND 200 THEN 2
            WHEN quantity BETWEEN 201 AND 300 THEN 3
            WHEN quantity BETWEEN 301 AND 400 THEN 4
            WHEN quantity BETWEEN 401 AND 500 THEN 5
        END AS range_order
    FROM jobs
)
SELECT
    quantity_group.quantity_range,
    ROUND(
        AVG(operation.processing_time_minutes)::numeric,
        2
    ) AS avg_processing_minutes,
    ROUND(AVG(operation.wait_time_minutes)::numeric, 2) AS avg_wait_minutes
FROM quantity_groups AS quantity_group
JOIN job_operations AS operation
    ON operation.job_id = quantity_group.job_id
WHERE quantity_group.quantity_range IS NOT NULL
GROUP BY quantity_group.quantity_range, quantity_group.range_order
ORDER BY quantity_group.range_order;


-- Hypothesis: late-job frequency increases with production quantity.
WITH job_completion AS (
    SELECT
        job_id,
        MAX(end_time) AS completion_time
    FROM job_operations
    GROUP BY job_id
),
quantity_outcomes AS (
    SELECT
        j.job_id,
        CASE
            WHEN j.quantity BETWEEN 1 AND 100 THEN '1-100'
            WHEN j.quantity BETWEEN 101 AND 200 THEN '101-200'
            WHEN j.quantity BETWEEN 201 AND 300 THEN '201-300'
            WHEN j.quantity BETWEEN 301 AND 400 THEN '301-400'
            WHEN j.quantity BETWEEN 401 AND 500 THEN '401-500'
        END AS quantity_range,
        CASE
            WHEN j.quantity BETWEEN 1 AND 100 THEN 1
            WHEN j.quantity BETWEEN 101 AND 200 THEN 2
            WHEN j.quantity BETWEEN 201 AND 300 THEN 3
            WHEN j.quantity BETWEEN 301 AND 400 THEN 4
            WHEN j.quantity BETWEEN 401 AND 500 THEN 5
        END AS range_order,
        jc.completion_time > j.due_at AS is_late
    FROM jobs AS j
    JOIN job_completion AS jc
        ON jc.job_id = j.job_id
)
SELECT
    quantity_range,
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE is_late) AS late_jobs,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE is_late)
        / NULLIF(COUNT(*), 0),
        2
    ) AS late_percentage
FROM quantity_outcomes
WHERE quantity_range IS NOT NULL
GROUP BY quantity_range, range_order
ORDER BY range_order;
