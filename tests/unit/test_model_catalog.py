import unittest

from lottery_intelligence_platform.model_catalog import (
    FAMILY_DOCS,
    render_model_catalog,
)


REQUIRED_KEYS = {
    "priority", "hypothesis", "formula", "inputs", "parameters",
    "limitations", "rejection_criteria",
}


class TestFamilyDocs(unittest.TestCase):
    def test_every_family_has_complete_documentation(self):
        for code, doc in FAMILY_DOCS.items():
            with self.subTest(code=code):
                self.assertEqual(set(doc), REQUIRED_KEYS)
                for key in REQUIRED_KEYS:
                    self.assertTrue(doc[key].strip(), f"{code}.{key} is empty")

    def test_priorities_are_valid(self):
        for code, doc in FAMILY_DOCS.items():
            self.assertIn(doc["priority"], {"P0", "P1", "P2"}, code)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class TestRenderModelCatalog(unittest.TestCase):
    def test_render_includes_models_and_findings(self):
        models = FakeResult([
            ("top_k_frequency", "PREDICTIVE", 1, "ab" * 32, None),
        ])
        findings = FakeResult([
            ("top_k_frequency", "REJECTED", "did not beat null"),
        ])
        calls = [models, findings]

        class Connection:
            def __init__(self):
                self._index = 0

            def execute(connection_self, *_args):
                result = calls[connection_self._index]
                connection_self._index += 1
                return result

        content = render_model_catalog(Connection())
        self.assertIn("## top_k_frequency (v1, PREDICTIVE)", content)
        self.assertIn("- **Hypothesis**", content)
        self.assertIn("`REJECTED` — did not beat null", content)
        self.assertIn("## bootstrap_uncertainty", content)

    def test_render_marks_undocumented_models(self):
        models = FakeResult([("mystery_model", "OTHER", 1, "cd" * 32, None)])
        findings = FakeResult([])

        class Connection:
            def __init__(self):
                self._index = 0

            def execute(connection_self, *_args):
                result = [models, findings][connection_self._index]
                connection_self._index += 1
                return result

        content = render_model_catalog(Connection())
        self.assertIn("No structured documentation registered", content)


if __name__ == "__main__":
    unittest.main()
