from airflow.sdk import task, dag
from common.utils.utils import upload_csv_to_s3
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

@dag
def import_dag():

    @task
    def grammy_csv_to_s3():
        upload_csv_to_s3('./../data/Grammy_Awards_Winners_20260208_055452.csv')

    s3_to_snowflake = SQLExecuteQueryOperator(
        task_id="s3_to_snowflake",
        conn_id="snowflake",
        sql="./sql/ingest-grammy-csv.sql",
    )
    
    grammy_csv_to_s3() >> s3_to_snowflake

import_dag()

