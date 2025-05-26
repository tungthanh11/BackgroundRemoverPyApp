import boto3
import os

rekognition = boto3.client('rekognition',
    region_name='ap-southeast-1',  # thay bằng region của bạn
    aws_access_key_id=os.getenv("REK_AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("REK_AWS_SECRET_ACCESS_KEY")
)

def detect_labels(image_bytes):
    response = rekognition.detect_labels(
        Image={'Bytes': image_bytes},
        MaxLabels=5,
        MinConfidence=70
    )
    return response['Labels']