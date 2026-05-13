FROM docker.io/apache/airflow:2.10.3-python3.11

# Install system libraries required by LightGBM (libgomp = OpenMP runtime).
# Must run as root before switching back to the airflow user.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Pre-install all Python packages at build time so startup is fast and
# does not require internet access.  Previously these were listed in
# _PIP_ADDITIONAL_REQUIREMENTS which re-ran pip on every container start.
#
# pyspark and apache-airflow-providers-apache-spark are intentionally omitted:
# the ETL and training jobs (etl_job.py / train_job.py) run via PythonOperator
# + runpy and do not import PySpark.  The Spark cluster is connected separately.
USER airflow
RUN pip install --no-cache-dir \
    apache-airflow-providers-amazon==8.28.0 \
    mlflow==2.17.2 \
    pandas==2.1.4 \
    scikit-learn==1.5.2 \
    imbalanced-learn==0.12.4 \
    xgboost==2.1.2 \
    lightgbm \
    great-expectations==1.2.4
