import hashlib
import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from api.config import settings


class RawStorage:
    def __init__(self):
        self.use_s3 = False
        self.local_dir = Path("/tmp/eios-raw-storage")
        self.local_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name="us-east-1",
            )
            self.client.head_bucket(Bucket=settings.s3_bucket)
            self.use_s3 = True
            self.bucket = settings.s3_bucket
        except Exception:
            self.client = None

    def put(self, content: bytes, key_prefix: str = "documents") -> str:
        content_hash = hashlib.sha256(content).hexdigest()
        key = f"{key_prefix}/{content_hash}"
        if self.use_s3:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content)
            return f"s3://{self.bucket}/{key}"
        path = self.local_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"file://{path}"

    def get(self, ref: str) -> bytes:
        if ref.startswith("s3://"):
            key = ref.replace(f"s3://{self.bucket}/", "")
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        path = Path(ref.replace("file://", ""))
        return path.read_bytes()


raw_storage = RawStorage()
