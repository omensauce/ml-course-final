from __future__ import annotations

import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


DEFAULT_ARGS = {
    "owner": "mlops",
    "retries": 2,
}


def _resolve_source_path(**context):
    dag_run = context.get("dag_run")
    conf = dag_run.conf if dag_run else {}
    source_path = conf.get("source_path")
    if not source_path:
        raise ValueError("source_path missing in DAG run conf")

    context["ti"].xcom_push(key="source_path", value=source_path)


def _validate_with_gx(**context):
    import pandas as pd
    import great_expectations as gx
    from great_expectations.core import ExpectationSuite
    from great_expectations import ValidationDefinition
    from great_expectations.expectations import (
        ExpectColumnToExist,
        ExpectColumnValuesToNotBeNull,
        ExpectColumnValuesToBeInSet,
        ExpectColumnValuesToBeUnique,
        ExpectTableRowCountToBeBetween,
    )

    source_path = context["ti"].xcom_pull(key="source_path")
    if not source_path:
        raise ValueError("No source path in XCom")

    df = pd.read_csv(source_path)

    gx_ctx = gx.get_context(mode="ephemeral")

    suite = gx_ctx.suites.add(ExpectationSuite(name="plant_alarm_ingestion_suite"))
    suite.add_expectation(ExpectColumnToExist(column="timestamp"))
    suite.add_expectation(ExpectColumnToExist(column="anomaly_label"))
    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="timestamp"))
    suite.add_expectation(
        ExpectColumnValuesToBeInSet(column="anomaly_label", value_set=[0, 1, 0.0, 1.0])
    )
    suite.add_expectation(ExpectColumnValuesToBeUnique(column="timestamp"))
    suite.add_expectation(ExpectTableRowCountToBeBetween(min_value=1))

    datasource = gx_ctx.data_sources.add_pandas("pandas_ingest")
    asset = datasource.add_dataframe_asset("sensor_frame")
    batch_def = asset.add_batch_definition_whole_dataframe("all_rows")

    val_def = gx_ctx.validation_definitions.add(
        ValidationDefinition(name="ingest_validation", data=batch_def, suite=suite)
    )

    result = val_def.run(batch_parameters={"dataframe": df})

    if not result.success:
        failures = [
            f"{r.expectation_config.type}: {r.result}"
            for r in result.results
            if not r.success
        ]
        raise ValueError("GX validation failed:\n" + "\n".join(failures))


def _run_etl(**context):
    source_path = context["ti"].xcom_pull(
        task_ids="resolve_source_path", key="source_path"
    )
    if not source_path:
        raise ValueError("No source path in XCom")

    original_argv = sys.argv[:]
    try:
        sys.argv = [
            "etl_job.py",
            "--input-path", source_path,
            "--output-root", "/workspace/data_lake/features",
        ]
        import runpy
        runpy.run_path("/opt/airflow/jobs/etl_job.py", run_name="__main__")
    finally:
        sys.argv = original_argv


with DAG(
    dag_id="ingest_etl_local_drop",
    default_args=DEFAULT_ARGS,
    description="Watch local drops, validate, run ETL",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["ingestion", "etl"],
) as dag:
    resolve_path = PythonOperator(
        task_id="resolve_source_path",
        python_callable=_resolve_source_path,
    )

    gx_validate = PythonOperator(
        task_id="great_expectations_validation",
        python_callable=_validate_with_gx,
    )

    run_etl = PythonOperator(
        task_id="etl",
        python_callable=_run_etl,
    )

    resolve_path >> gx_validate >> run_etl
