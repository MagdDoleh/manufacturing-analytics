-- Work-center operation volume and average queue/processing performance.
CREATE OR REPLACE VIEW v_work_center_performance AS
SELECT
    wc.work_center_id,
    wc.work_center_code,
    wc.name,
    COUNT(jo.operation_id) AS total_operations,
    ROUND(AVG(jo.wait_time_minutes)::numeric, 2) AS avg_wait_minutes,
    ROUND(AVG(jo.processing_time_minutes)::numeric, 2) AS avg_processing_minutes
FROM work_centers AS wc
JOIN job_operations AS jo
    ON jo.work_center_id = wc.work_center_id
GROUP BY
    wc.work_center_id,
    wc.work_center_code,
    wc.name;


-- Machine-level operation performance with work-center and capacity context.
CREATE OR REPLACE VIEW v_machine_performance AS
SELECT
    m.machine_id,
    m.machine_code,
    m.work_center_id,
    wc.name,
    m.capacity_per_hour,
    COUNT(jo.operation_id) AS total_operations,
    ROUND(AVG(jo.wait_time_minutes)::numeric, 2) AS avg_wait_minutes,
    ROUND(AVG(jo.processing_time_minutes)::numeric, 2) AS avg_processing_minutes
FROM machines AS m
JOIN work_centers AS wc
    ON wc.work_center_id = m.work_center_id
JOIN job_operations AS jo
    ON jo.machine_id = m.machine_id
GROUP BY
    m.machine_id,
    m.machine_code,
    m.work_center_id,
    wc.name,
    m.capacity_per_hour;


-- Downtime frequency and duration summarized for each affected machine.
CREATE OR REPLACE VIEW v_machine_downtime AS
SELECT
    m.machine_id,
    m.machine_code,
    wc.name,
    COUNT(de.downtime_id) AS downtime_events,
    ROUND((SUM(de.downtime_minutes) / 60.0)::numeric, 2) AS total_downtime_hours,
    ROUND(AVG(de.downtime_minutes)::numeric, 2) AS avg_downtime_minutes
FROM machines AS m
JOIN work_centers AS wc
    ON wc.work_center_id = m.work_center_id
JOIN downtime_events AS de
    ON de.machine_id = m.machine_id
GROUP BY
    m.machine_id,
    m.machine_code,
    wc.name;


-- Product cycle time from job creation through completion of operation five.
CREATE OR REPLACE VIEW v_product_cycle_time AS
SELECT
    p.product_id,
    p.product_code,
    p.product_name,
    COUNT(j.job_id) AS total_jobs,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (jo.end_time - j.created_at)) / 3600.0)::numeric,
        2
    ) AS avg_cycle_time_hours
FROM products AS p
JOIN jobs AS j
    ON j.product_id = p.product_id
JOIN job_operations AS jo
    ON jo.job_id = j.job_id
   AND jo.operation_sequence = 5
GROUP BY
    p.product_id,
    p.product_code,
    p.product_name;


-- Daily completed-job throughput based on the final manufacturing operation.
CREATE OR REPLACE VIEW v_daily_throughput AS
SELECT
    jo.end_time::date AS completion_date,
    COUNT(DISTINCT jo.job_id) AS jobs_completed
FROM job_operations AS jo
WHERE jo.operation_sequence = 5
GROUP BY jo.end_time::date;


-- Overall on-time delivery performance using operation five as job completion.
CREATE OR REPLACE VIEW v_delivery_performance AS
SELECT
    COUNT(*) AS total_jobs,
    COUNT(*) FILTER (WHERE jo.end_time <= j.due_at) AS on_time_jobs,
    COUNT(*) FILTER (WHERE jo.end_time > j.due_at) AS late_jobs,
    ROUND(
        CASE
            WHEN COUNT(*) = 0 THEN 0::numeric
            ELSE (
                COUNT(*) FILTER (WHERE jo.end_time <= j.due_at) * 100.0
                / COUNT(*)
            )::numeric
        END,
        2
    ) AS on_time_percentage
FROM jobs AS j
JOIN job_operations AS jo
    ON jo.job_id = j.job_id
   AND jo.operation_sequence = 5;
