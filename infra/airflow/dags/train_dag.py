from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def run_training_job():
    import runpy

    runpy.run_path("/opt/airflow/jobs/train_job.py", run_name="__main__")


with DAG(
    dag_id="train_models_local",
    description="Train IsolationForest, RandomForest, XGBoost champion, Ridge deviation forecaster, calibrated XGBoost forecasters and register in MLflow",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["training", "mlflow"],
) as dag:
    train = PythonOperator(
        task_id="train_and_register",
        python_callable=run_training_job,
    )

    train