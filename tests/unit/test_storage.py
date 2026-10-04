import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
from botocore.config import Config

from lottery_intelligence_platform.raw_bucket import ensure_bucket
from lottery_intelligence_platform.storage import s3_client_from_environment


class FakeS3Client:
    def __init__(self, head_error=None, create_error=None):
        self.head_error = head_error
        self.create_error = create_error
        self.created = []

    def head_bucket(self, **kwargs):
        if self.head_error:
            raise self.head_error
        return {}

    def create_bucket(self, **kwargs):
        if self.create_error:
            raise self.create_error
        self.created.append(kwargs["Bucket"])
        return {}


def client_error(code, status):
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "HeadBucket",
    )


class StorageConfigTests(unittest.TestCase):
    @patch("lottery_intelligence_platform.storage.boto3.client")
    def test_minio_endpoint_uses_path_style_and_explicit_credentials(self, client_factory):
        expected_client = object()
        client_factory.return_value = expected_client
        environment = {
            "LOTTERY_S3_ENDPOINT_URL": "http://127.0.0.1:19000",
            "LOTTERY_S3_REGION": "us-east-1",
            "LOTTERY_S3_ACCESS_KEY": "local-access-key",
            "LOTTERY_S3_SECRET_KEY": "local-secret-key",
        }

        result = s3_client_from_environment(environment)

        self.assertIs(result, expected_client)
        args, kwargs = client_factory.call_args
        self.assertEqual(args, ("s3",))
        self.assertEqual(kwargs["endpoint_url"], environment["LOTTERY_S3_ENDPOINT_URL"])
        self.assertEqual(kwargs["aws_access_key_id"], environment["LOTTERY_S3_ACCESS_KEY"])
        self.assertIsInstance(kwargs["config"], Config)

    @patch("lottery_intelligence_platform.storage.boto3.client")
    def test_aws_default_credentials_are_left_to_boto_provider_chain(self, client_factory):
        s3_client_from_environment({"LOTTERY_S3_REGION": "eu-west-1"})

        kwargs = client_factory.call_args.kwargs
        self.assertNotIn("aws_access_key_id", kwargs)
        self.assertNotIn("aws_secret_access_key", kwargs)
        self.assertEqual(kwargs["region_name"], "eu-west-1")

    def test_endpoint_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            s3_client_from_environment({
                "LOTTERY_S3_ENDPOINT_URL": "http://user:pass@localhost:19000",
                "LOTTERY_S3_ACCESS_KEY": "key",
                "LOTTERY_S3_SECRET_KEY": "secret",
            })

    def test_credentials_must_be_configured_as_a_pair(self):
        with self.assertRaises(ValueError):
            s3_client_from_environment({"LOTTERY_S3_ACCESS_KEY": "key"})


class BucketInitializationTests(unittest.TestCase):
    def test_existing_bucket_is_not_recreated(self):
        client = FakeS3Client()

        self.assertFalse(ensure_bucket(client, "lottery-raw"))
        self.assertEqual(client.created, [])

    def test_missing_bucket_is_created(self):
        client = FakeS3Client(head_error=client_error("NoSuchBucket", 404))

        self.assertTrue(ensure_bucket(client, "lottery-raw"))
        self.assertEqual(client.created, ["lottery-raw"])

    def test_non_missing_bucket_error_is_not_suppressed(self):
        client = FakeS3Client(head_error=client_error("AccessDenied", 403))

        with self.assertRaises(ClientError):
            ensure_bucket(client, "lottery-raw")

    def test_already_owned_bucket_race_is_idempotent(self):
        client = FakeS3Client(
            head_error=client_error("NoSuchBucket", 404),
            create_error=client_error("BucketAlreadyOwnedByYou", 409),
        )

        self.assertFalse(ensure_bucket(client, "lottery-raw"))


if __name__ == "__main__":
    unittest.main()
