import unittest
from datetime import date, timedelta

from lottery_intelligence_platform.predictions import record_prediction


class FakeConnection:
    def __init__(self):
        self.executed = []

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        raise AssertionError("validation must fail before any database call")


class TestRecordPredictionValidation(unittest.TestCase):
    def _record(self, **kwargs):
        defaults = dict(
            connection=FakeConnection(),
            model_version_id="00000000-0000-0000-0000-000000000001",
            draw_type_id="00000000-0000-0000-0000-000000000002",
            scheduled_date=date.today() + timedelta(days=30),
            predicted_numbers=[1, 2],
        )
        defaults.update(kwargs)
        return record_prediction(**defaults)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            self._record(predicted_numbers=[])

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            self._record(predicted_numbers=[5, 5])

    def test_out_of_range_rejected(self):
        for bad in ([0, 1], [91, 2], [-3, 4]):
            with self.assertRaises(ValueError, msg=str(bad)):
                self._record(predicted_numbers=bad)

    def test_past_date_rejected(self):
        with self.assertRaises(ValueError):
            self._record(scheduled_date=date(2020, 1, 1))

    def test_today_accepted_for_validation(self):
        connection = FakeConnection()
        with self.assertRaises(AssertionError):
            # validation passes; the fake connection proves the DB path was reached
            record_prediction(
                connection=connection,
                model_version_id="00000000-0000-0000-0000-000000000001",
                draw_type_id="00000000-0000-0000-0000-000000000002",
                scheduled_date=date.today(),
                predicted_numbers=[7, 8],
            )


if __name__ == "__main__":
    unittest.main()
