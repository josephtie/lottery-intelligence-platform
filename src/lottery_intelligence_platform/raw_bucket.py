from __future__ import annotations

import os

from botocore.exceptions import ClientError

from lottery_intelligence_platform.storage import s3_client_from_environment


def ensure_bucket(client, bucket: str) -> bool:
    if not bucket.strip():
        raise ValueError("bucket cannot be empty")
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as exc:
        error = exc.response.get("Error", {})
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if error.get("Code") not in {"404", "NoSuchBucket", "NotFound"} and status != 404:
            raise
    try:
        client.create_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "BucketAlreadyOwnedByYou":
            return False
        raise


def main() -> int:
    bucket = os.environ.get("LOTTERY_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("LOTTERY_S3_BUCKET must be set")
    created = ensure_bucket(s3_client_from_environment(), bucket)
    print(f"RAW bucket {'created' if created else 'already exists'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
