import hashlib
import io
import unittest

from botocore.exceptions import ClientError

from lottery_intelligence_platform.raw import (
    RawObjectIntegrityError,
    S3RawObjectStore,
    raw_object_key,
)


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.put_calls = 0
        self.conflicts_remaining = 0

    def put_object(self, **kwargs):
        self.put_calls += 1
        if self.conflicts_remaining:
            self.conflicts_remaining -= 1
            raise ClientError({"Error": {"Code": "ConditionalRequestConflict"}}, "PutObject")
        key = kwargs["Key"]
        if key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[key] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}


class RawObjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeS3Client()
        self.store = S3RawObjectStore(self.client, "raw-test")

    def test_payload_is_stored_at_content_addressed_key(self):
        payload = b'{"draw": [1, 2, 3]}'

        reference = self.store.put(payload, "application/json")

        digest = hashlib.sha256(payload).hexdigest()
        self.assertEqual(reference.sha256, digest)
        self.assertEqual(reference.object_key, raw_object_key(digest))
        self.assertEqual(self.client.objects[reference.object_key], payload)
        self.assertEqual(reference.byte_size, len(payload))

    def test_repeated_payload_is_idempotent_and_verifies_existing_bytes(self):
        payload = b"same response"

        first = self.store.put(payload)
        second = self.store.put(payload)

        self.assertEqual(first, second)
        self.assertEqual(self.client.put_calls, 2)
        self.assertEqual(len(self.client.objects), 1)

    def test_existing_corrupt_content_fails_closed(self):
        payload = b"expected"
        key = raw_object_key(hashlib.sha256(payload).hexdigest())
        self.client.objects[key] = b"corrupt"

        with self.assertRaises(RawObjectIntegrityError):
            self.store.put(payload)

    def test_conditional_conflict_is_retried(self):
        self.client.conflicts_remaining = 1

        reference = self.store.put(b"payload")

        self.assertIn(reference.object_key, self.client.objects)
        self.assertEqual(self.client.put_calls, 2)

    def test_empty_payload_is_preserved(self):
        reference = self.store.put(b"")

        self.assertEqual(reference.byte_size, 0)
        self.assertEqual(self.client.objects[reference.object_key], b"")

    def test_non_bytes_payload_is_rejected(self):
        with self.assertRaises(TypeError):
            self.store.put("not bytes")

    def test_invalid_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            raw_object_key("ABC")


if __name__ == "__main__":
    unittest.main()
