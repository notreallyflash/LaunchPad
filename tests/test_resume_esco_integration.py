from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import main


class FakeRecognition:
    def __init__(self):
        self.confirmed_skill_uris = ["python-uri", "seo-uri"]

    def to_dict(self):
        return {
            "confirmed_skills": [
                {"skill_uri": "python-uri", "preferred_label": "Python"},
                {"skill_uri": "seo-uri", "preferred_label": "SEO"},
            ],
            "ambiguous_matches": [],
            "review_matches": [],
            "confirmed_skill_uris": self.confirmed_skill_uris,
            "token_count": 10,
            "candidate_phrase_count": 15,
            "catalog_row_count": 2,
            "truncated": False,
        }


class FakeSkillCatalog:
    def recognise(self, text):
        return FakeRecognition()


class TestResumeESCOIntegration:

    def setup_method(self):
        self.client = TestClient(main.app)
        self.catalog_patch = patch.object(
            main, "skill_catalog", FakeSkillCatalog()
        )
        self.catalog_patch.start()

        self.pdf_patch = patch.object(
            main,
            "extract_text_from_pdf",
            return_value=(
                "Python developer with search engine optimisation "
                "and digital marketing experience."
            ),
        )
        self.pdf_patch.start()

    def teardown_method(self):
        self.pdf_patch.stop()
        self.catalog_patch.stop()

    @patch.object(main, "rank_esco_occupations")
    def test_successful_upload_returns_esco_skills_and_occupations(self, ranking):
        ranking.return_value = [
            {
                "occupation_label": "Search engine optimisation expert",
                "matched_essential": 2,
                "total_essential": 10,
                "essential_coverage": 20.0,
                "weighted_skill_coverage": 12.0,
            }
        ]

        response = self.client.post(
            "/upload_resume",
            files={"file": ("resume.pdf", b"dummy pdf", "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()

        assert "ats_score" in data
        assert data["esco_analysis"]["status"] == "success"
        assert data["esco_analysis"]["occupation_ranking_status"] == "success"
        assert len(data["esco_analysis"]["confirmed_skills"]) == 2
        assert len(data["esco_analysis"]["occupation_matches"]) == 1

        ranking.assert_called_once_with(["python-uri", "seo-uri"])

    @patch.object(main, "rank_esco_occupations")
    def test_ranking_failure_preserves_recognised_skills(self, ranking):
        ranking.side_effect = RuntimeError("Simulated ranking failure")

        response = self.client.post(
            "/upload_resume",
            files={"file": ("resume.pdf", b"dummy pdf", "application/pdf")},
        )

        assert response.status_code == 200
        esco = response.json()["esco_analysis"]

        assert esco["status"] == "success"
        assert esco["occupation_ranking_status"] == "error"
        assert len(esco["confirmed_skills"]) == 2
        assert esco["occupation_matches"] == []

    def test_recognition_failure_preserves_ats_response(self):
        with patch.object(
            main.skill_catalog,
            "recognise",
            side_effect=RuntimeError("Simulated recognition failure"),
        ):
            response = self.client.post(
                "/upload_resume",
                files={"file": ("resume.pdf", b"dummy pdf", "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()

        assert "ats_score" in data
        assert data["esco_analysis"]["status"] == "error"
        assert data["esco_analysis"]["occupation_matches"] == []

    def test_unavailable_catalog_preserves_ats_response(self):
        with patch.object(main, "skill_catalog", None):
            response = self.client.post(
                "/upload_resume",
                files={"file": ("resume.pdf", b"dummy pdf", "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()

        assert "ats_score" in data
        assert data["esco_analysis"]["status"] == "unavailable"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
