"""
Custom S3 artifact service for ADK.
Drop-in replacement for GcsArtifactService when deploying on AWS.
"""
from typing import Optional
import boto3
from botocore.exceptions import ClientError
import google.genai.types as types
from google.adk.artifacts.base_artifact_service import BaseArtifactService


class S3ArtifactService(BaseArtifactService):
    """Stores ADK artifacts in an AWS S3 bucket.

    Object key format:
      {app_name}/{user_id}/{session_id}/{filename}/version_{n}
    User-scoped (filename starts with "user:"):
      {app_name}/{user_id}/user/{filename_without_prefix}/version_{n}
    """

    def __init__(self, bucket_name: str, region_name: Optional[str] = None):
        self._bucket = bucket_name
        self._s3 = boto3.client("s3", region_name=region_name)

    def _object_key(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        version: int,
    ) -> str:
        if filename.startswith("user:"):
            clean = filename[len("user:"):]
            return f"{app_name}/{user_id}/user/{clean}/version_{version}"
        return f"{app_name}/{user_id}/{session_id}/{filename}/version_{version}"

    def _prefix(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
    ) -> str:
        if filename.startswith("user:"):
            clean = filename[len("user:"):]
            return f"{app_name}/{user_id}/user/{clean}/"
        return f"{app_name}/{user_id}/{session_id}/{filename}/"

    def _next_version(
        self, app_name: str, user_id: str, session_id: str, filename: str
    ) -> int:
        prefix = self._prefix(app_name, user_id, session_id, filename)
        resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        return len(resp.get("Contents", []))

    async def save_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        artifact: types.Part,
    ) -> int:
        version = self._next_version(app_name, user_id, session_id, filename)
        key = self._object_key(app_name, user_id, session_id, filename, version)
        mime = artifact.inline_data.mime_type or "application/octet-stream"
        data = artifact.inline_data.data
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=mime,
        )
        return version

    async def load_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        version: Optional[int] = None,
    ) -> Optional[types.Part]:
        if version is None:
            version = self._next_version(app_name, user_id, session_id, filename) - 1
        if version < 0:
            return None
        key = self._object_key(app_name, user_id, session_id, filename, version)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            data = resp["Body"].read()
            mime = resp.get("ContentType", "application/octet-stream")
            return types.Part.from_bytes(data=data, mime_type=mime)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    async def list_artifact_keys(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> list[str]:
        prefix = f"{app_name}/{user_id}/{session_id}/"
        resp = self._s3.list_objects_v2(
            Bucket=self._bucket, Prefix=prefix, Delimiter="/"
        )
        filenames = []
        for cp in resp.get("CommonPrefixes", []):
            # key looks like app/user/session/filename/
            part = cp["Prefix"].rstrip("/").split("/")[-1]
            filenames.append(part)
        return filenames

    async def delete_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
    ) -> None:
        prefix = self._prefix(app_name, user_id, session_id, filename)
        resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        objects = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
        if objects:
            self._s3.delete_objects(
                Bucket=self._bucket, Delete={"Objects": objects}
            )

    async def list_versions(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
    ) -> list[int]:
        prefix = self._prefix(app_name, user_id, session_id, filename)
        resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        versions = []
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            # key ends with /version_N
            try:
                v = int(key.rsplit("version_", 1)[-1])
                versions.append(v)
            except ValueError:
                pass
        return sorted(versions)
