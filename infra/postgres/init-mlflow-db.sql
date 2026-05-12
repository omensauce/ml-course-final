-- Creates the MLflow backend database on first postgres init.
-- mlflow server uses postgresql://.../mlflow (separate from the mlops app db).
CREATE DATABASE mlflow;
