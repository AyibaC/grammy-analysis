from unittest.mock import patch
import pandas as pd
from pathlib import Path
from common.utils.utils import upload_csv_to_s3

#test csv exists
def test_csv_exists():
    csv_path = Path('./dags/data/Grammy_Awards_Winners_20260208_055452.csv')
    assert csv_path.exists()

#test sql file exists
def test_sql_file_exists():
    sql_path = Path('./dags/sql/ingest-grammy-csv.sql')
    assert sql_path.exists()

#test s3 load file is called
@patch("airflow.providers.amazon.aws.hooks.s3.S3Hook.load_file")
def test_upload_calls_s3(mock_load_file):
    upload_csv_to_s3('./../data/Grammy_Awards_Winners_20260208_055452.csv')

    mock_load_file.assert_called_once_with(
        filename='./../data/Grammy_Awards_Winners_20260208_055452.csv',
        key="Grammy_Awards_Winners_20260208_055452.csv",
        bucket_name="grammy-analysis-552153077634-us-east-1-an",
        replace=True,
    )

#test sql query operator is called
def test_sql_operator_config(dagbag):
    dag = dagbag.get_dag("import_dag")
    task = dag.get_task("s3_to_snowflake")

    expected_sql = Path("./dags/sql/ingest-grammy-csv.sql").read_text()

    assert task.conn_id == "snowflake"
    assert task.sql == expected_sql

#test sql script is not an empty sql statement

#test for dag import errors
def test_dag_import_errors(dagbag):
    assert dagbag.import_errors == {}


#test expected dags are loaded 
def test_expected_dags_loaded(dagbag):
    loaded_dag_ids = list(dagbag.dags.keys())
    expected_dag_ids = ["import_dag"]

    for dag_id in expected_dag_ids:
        assert dag_id in loaded_dag_ids

#test task dependencies (failure in first means second doesn't run)
def test_task_dependencies(dagbag):
    dag = dagbag.get_dag("import_dag")

    upload = dag.get_task("grammy_csv_to_s3")
    load = dag.get_task("s3_to_snowflake")

    assert load.task_id in upload.downstream_task_ids

#test csv format fits sql load statement
def test_csv_format():
    expected_headers = [
        "Year",
        "Ceremony_Number",
        "Decade",
        "Era",
        "Category",
        "Award_Group",
        "Winner",
        "Artist",
        "Status",
        "Total_Wins",
        "Category_Total_Winners",
        "Data_Source",
        "Collection_Date"
    ]

    grammy_csv = pd.read_csv('./dags/data/Grammy_Awards_Winners_20260208_055452.csv')
    csv_headers = list(grammy_csv.head(1))

    assert csv_headers == expected_headers