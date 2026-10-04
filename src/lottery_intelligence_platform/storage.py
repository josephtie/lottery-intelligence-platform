from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

from lottery_intelligence_platform.raw import S3RawObjectStore


def s3_client_from_environment(environ: Mapping[str, str] | None = None):
    values = os.environ if environ is None else environ
    endpoint_url = values.get("LOTTERY_S3_ENDPOINT_URL") or None
    region_name = values.get("LOTTERY_S3_REGION", "us-east-1")
    access_key = values.get("LOTTERY_S3_ACCESS_KEY") or None
    secret_key = values.get("LOTTERY_S3_SECRET_KEY") or None

    if bool(access_key) != bool(secret_key):
        raise ValueError("both LOTTERY_S3_ACCESS_KEY and LOTTERY_S3_SECRET_KEY must be set together")
    if endpoint_url:
        parsed = urlsplit(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("LOTTERY_S3_ENDPOINT_URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("S3 credentials must not be embedded in LOTTERY_S3_ENDPOINT_URL")
        if not access_key or not secret_key:
            raise ValueError("S3-compatible endpoints require explicit credentials")

    options = {"region_name": region_name}
    if endpoint_url:
        options["endpoint_url"] = endpoint_url
        options["config"] = Config(s3={"addressing_style": "path"})
    if access_key and secret_key:
        options["aws_access_key_id"] = access_key
        options["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **options)


def raw_object_store_from_environment() -> S3RawObjectStore:
    bucket = os.environ.get("LOTTERY_S3_BUCKET", "").strip()
    if not bucket:
        raise ValueError("LOTTERY_S3_BUCKET must be set")
    return S3RawObjectStore(s3_client_from_environment(), bucket)
