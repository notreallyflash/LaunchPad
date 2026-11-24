import unittest

from services.skill_recognition import (
    build_candidate_phrases,
    recognise_from_label_rows,
)


PYTHON_URI = "http://data.europa.eu/esco/skill/ccd0a1d9-afda-43d9-b901-96344886e14d"
SEO_URI = "http://data.europa.eu/esco/skill/a0bf9b9d-e53f-418c-a839-5d99eff718fe"
OPENCV_URI_1 = "http://data.europa.eu/esco/skill/21d2f96d-35f7-4e3f-9745-c533d2dd6e97"
OPENCV_URI_2 = "http://data.europa.eu/esco/skill/484df271-bb52-49f1-8f50-f19624bf4df2"
OPENCV_URI_3 = "http://data.europa.eu/esco/skill/7b0d5000-00da-4864-b776-6de49a87a669"


def row(label, uri, preferred, label_type="alternative", skill_type="knowledge", reuse="sector-specific"):
    return {
        "normalized_label": label.lower().strip(),
        "skill_uri": uri,
        "label": label,
        "label_type": label_type,
        "preferred_label": preferred,
        "skill_type": skill_type,
        "reuse_level": reuse,
    }


class SkillRecognitionTests(unittest.TestCase):
    def test_unique_alias_resolves_to_one_canonical_uri(self):
        catalog = [
            row("Python", PYTHON_URI, "Python (computer programming)", "alternative"),
            row("Python (computer programming)", PYTHON_URI, "Python (computer programming)", "preferred"),
        ]
        result = recognise_from_label_rows("Built APIs using Python.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [PYTHON_URI])
        self.assertEqual(len(result.confirmed_skills), 1)
        self.assertEqual(result.confirmed_skills[0].preferred_label, "Python (computer programming)")
        self.assertEqual(result.ambiguous_matches, [])

    def test_ambiguous_opencv_is_not_automatically_awarded(self):
        catalog = [
            row("OpenCV", OPENCV_URI_1, "computer programming", "alternative"),
            row("OpenCV", OPENCV_URI_1, "computer programming", "hidden"),
            row("OpenCV", OPENCV_URI_2, "computer vision", "hidden"),
            row("OpenCV", OPENCV_URI_3, "software components libraries", "alternative"),
        ]
        result = recognise_from_label_rows("Used OpenCV in a computer vision project.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [])
        self.assertEqual(len(result.ambiguous_matches), 1)
        self.assertEqual(len(result.ambiguous_matches[0].candidates), 3)

    def test_longest_phrase_wins(self):
        catalog = [
            row("search engine", "skill-short", "search engine", "alternative"),
            row("search engine optimisation", SEO_URI, "conduct search engine optimisation", "alternative"),
        ]
        result = recognise_from_label_rows("Improved search engine optimisation performance.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [SEO_URI])
        self.assertEqual(result.confirmed_skills[0].matched_phrases, ["search engine optimisation"])

    def test_duplicate_mentions_and_aliases_credit_uri_once(self):
        catalog = [
            row("Python", PYTHON_URI, "Python (computer programming)", "alternative"),
            row("Python 3", PYTHON_URI, "Python (computer programming)", "alternative"),
        ]
        result = recognise_from_label_rows("Python and Python 3 were used. Python was used again.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [PYTHON_URI])
        self.assertEqual(len(result.confirmed_skills), 1)
        self.assertEqual(result.confirmed_skills[0].occurrence_count, 3)

    def test_technical_punctuation_is_preserved(self):
        phrases, tokens, _ = build_candidate_phrases("Built apps with C++, C#, .NET, Node.js and CI/CD.")
        self.assertIn("c++", phrases)
        self.assertIn("c#", phrases)
        self.assertIn(".net", phrases)
        self.assertIn("node.js", phrases)
        self.assertIn("ci/cd", phrases)
        self.assertIn("c++", [token.value for token in tokens])

    def test_java_does_not_match_javascript(self):
        catalog = [
            row("Java", "java-uri", "Java", "preferred"),
        ]
        result = recognise_from_label_rows("Built frontend features with JavaScript.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [])

    def test_phrase_does_not_span_sentence_boundary(self):
        catalog = [
            row("python java", "combined-uri", "Python Java", "alternative"),
        ]
        result = recognise_from_label_rows("Python. Java developer.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [])

    def test_unique_hidden_label_requires_review_not_confirmation(self):
        report_facts_uri = "http://data.europa.eu/esco/skill/be6ab363-3de1-427f-a8ef-85d5b0250822"
        catalog = [
            row("reporting", report_facts_uri, "report facts", "hidden"),
        ]
        result = recognise_from_label_rows("Built reporting tools using Python.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [])
        self.assertEqual(len(result.review_matches), 1)
        self.assertEqual(result.review_matches[0].skill_uri, report_facts_uri)
        self.assertEqual(result.review_matches[0].match_status, "hidden_label_requires_review")
        self.assertEqual(result.review_matches[0].matched_phrases, ["reporting"])

    def test_stronger_match_for_same_uri_overrides_hidden_label_review(self):
        report_facts_uri = "http://data.europa.eu/esco/skill/be6ab363-3de1-427f-a8ef-85d5b0250822"
        catalog = [
            row("reporting", report_facts_uri, "report facts", "hidden"),
            row("report facts", report_facts_uri, "report facts", "preferred"),
        ]
        result = recognise_from_label_rows("I prepare report facts and reporting summaries.", catalog)
        self.assertEqual(result.confirmed_skill_uris, [report_facts_uri])
        self.assertEqual(result.review_matches, [])

    def test_empty_input_returns_empty_result(self):
        result = recognise_from_label_rows("", [])
        self.assertEqual(result.confirmed_skills, [])
        self.assertEqual(result.ambiguous_matches, [])
        self.assertEqual(result.review_matches, [])
        self.assertEqual(result.token_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
