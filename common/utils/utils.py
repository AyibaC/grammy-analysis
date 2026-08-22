from airflow.providers.amazon.aws.hooks.s3 import S3Hook

def upload_csv_to_s3(csv_path):
    hook = S3Hook(aws_conn_id="s3-bucket")
    hook.load_file(
        filename=csv_path,
        key="Grammy_Awards_Winners_20260208_055452.csv",
        bucket_name="grammy-analysis-552153077634-us-east-1-an",
        replace=True,
    )