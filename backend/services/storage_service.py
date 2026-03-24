import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger("proctorshield.storage")

# Connect to our local MinIO Docker container
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='supersecretpassword',
    region_name='us-east-1' # Required by boto3, even for local MinIO
)

BUCKET_NAME = "exam-recordings"

def ensure_bucket_exists():
    """Creates the storage bucket if it doesn't exist yet"""
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError:
        logger.info(f"Creating MinIO bucket: {BUCKET_NAME}")
        s3_client.create_bucket(Bucket=BUCKET_NAME)

def generate_evidence_link(session_id: str) -> str:
    """
    Generates a secure, temporary link for the Java ERP team 
    to watch the student's exam video. Expires in 7 days.
    """
    try:
        # The filename LiveKit Egress will save it as
        object_name = f"{session_id}_full_recording.mp4"
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': object_name},
            ExpiresIn=604800 # 7 days in seconds
        )
        return url
    except Exception as e:
        logger.error(f"Failed to generate video link: {e}")
        return "https://your-domain.com/video-not-found"
