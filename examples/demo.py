"""Offline demonstration using a tiny sample catalogue.

Run from the project root:
    python -m examples.demo
"""
from services.skill_recognition import recognise_from_label_rows

catalog = [
    {
        "normalized_label": "python",
        "skill_uri": "http://data.europa.eu/esco/skill/ccd0a1d9-afda-43d9-b901-96344886e14d",
        "label": "Python",
        "label_type": "alternative",
        "preferred_label": "Python (computer programming)",
        "skill_type": "knowledge",
        "reuse_level": "sector-specific",
    },
    {
        "normalized_label": "conduct search engine optimisation",
        "skill_uri": "http://data.europa.eu/esco/skill/a0bf9b9d-e53f-418c-a839-5d99eff718fe",
        "label": "conduct search engine optimisation",
        "label_type": "preferred",
        "preferred_label": "conduct search engine optimisation",
        "skill_type": "skill/competence",
        "reuse_level": "cross-sector",
    },
        {
        "normalized_label": "search engine optimisation",
        "skill_uri": "http://data.europa.eu/esco/skill/eda4d727-4374-49af-ace4-118c7c906835",
        "label": "search engine optimisation",
        "label_type": "preferred",
        "preferred_label": "search engine optimisation",
        "skill_type": "knowledge",
        "reuse_level": "sector-specific",
    },
]

resume_text = (
    "Digital marketing analyst with experience in search engine optimisation. "
    "Built reporting tools using Python."
)

result = recognise_from_label_rows(resume_text, catalog)
print(result.to_dict())
