from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from botocore.exceptions import ClientError

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RawObjectIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RawObjectRef:
    sha256: str
    object_key: str
    byte_size: int
    content_type: str

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hex digest")
        if self.object_key != raw_object_key(self.sha256):
            raise ValueError("object_key must be derived from sha256")
        if self.byte_size < 0:
            raise ValueError("byte_size cannot be negative")
        if not self.content_type.strip():
            raise ValueError("content_type cannot be empty")


class S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


class RawObjectStore(Protocol):
    def put(self, payload: bytes, content_type: str = "application/octet-stream") -> RawObjectRef: ...


def raw_object_key(sha256_hex: str) -> str:
    if not _SHA256_PATTERN.fullmatch(sha256_hex):
        raise ValueError("sha256 must be a lowercase 64-character hex digest")
    return f"raw/sha256/{sha256_hex[:2]}/{sha256_hex}"


class S3RawObjectStore:
    def __init__(self, client: S3Client, bucket: str, *, conflict_retries: int = 3) -> None:
        if not bucket.strip():
            raise ValueError("bucket cannot be empty")
        if conflict_retries < 1:
            raise ValueError("conflict_retries must be at least one")
        self._client = client
        self._bucket = bucket
        self._conflict_retries = conflict_retries

    def put(self, payload: bytes, content_type: str = "application/octet-stream") -> RawObjectRef:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not content_type.strip():
            raise ValueError("content_type cannot be empty")

        digest = hashlib.sha256(payload).hexdigest()
        key = raw_object_key(digest)
        for attempt in range(self._conflict_retries):
            try:
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=payload,
                    ContentLength=len(payload),
                    ContentType=content_type,
                    Metadata={"sha256": digest},
                    IfNoneMatch="*",
                )
                break
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"412", "PreconditionFailed"}:
                    self._verify_existing(key, payload, digest)
                    break
                if code in {"409", "ConditionalRequestConflict"} and attempt + 1 < self._conflict_retries:
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise

        return RawObjectRef(digest, key, len(payload), content_type)

    def _verify_existing(self, key: str, expected_payload: bytes, expected_sha256: str) -> None:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            existing_payload = body.read()
        finally:
            body.close()
        existing_sha256 = hashlib.sha256(existing_payload).hexdigest()
        if existing_sha256 != expected_sha256 or existing_payload != expected_payload:
            raise RawObjectIntegrityError(f"existing object at {key} does not match its content address")
