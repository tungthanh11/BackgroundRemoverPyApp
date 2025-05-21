import boto3
import os
from botocore.exceptions import ClientError
import logging
from dotenv import load_dotenv
from io import BytesIO

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_DEFAULT_REGION')

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def upload_to_s3(file_obj, bucket_name, object_name):
    try:
        s3_client.upload_fileobj(
            file_obj,
            bucket_name,
            object_name,
            ExtraArgs={
                'ACL': 'public-read', 
                'ContentType': 'image/png'  
            }
        )
        return True
    except ClientError as e:
        logging.error(e)
        return False


def get_s3_url(bucket_name, filename):
    cloudfront_domain = os.getenv("CLOUDFRONT_URL")  
    return f"https://{cloudfront_domain}/{filename}"


def download_from_s3(bucket_name, object_name):
    try:
        file_stream = BytesIO()
        s3_client.download_fileobj(bucket_name, object_name, file_stream)
        file_stream.seek(0)
        return file_stream
    except ClientError as e:
        logging.error(f"Download failed: {e}")
        return None