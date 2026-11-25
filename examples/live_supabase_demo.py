import json
import os

from dotenv import load_dotenv
from supabase import create_client
from services.skill_recognition import SupabaseSkillCatalog

load_dotenv()

def main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        raise SystemExit(
            "Missing SUPABASE_URL or SUPABASE_ANON_KEY."
        )

    try:
        client = create_client(url, key)

        catalog = SupabaseSkillCatalog(
            client,
            chunk_size=500
        )

        resume_text = (
            "Digital marketing analyst with experience in "
            "search engine optimisation. "
            "Built reporting tools using Python. "
            "Used OpenCV for image recognition."
        )

        result = catalog.recognise(resume_text)

        print("\n========== CONFIRMED SKILLS ==========")

        for skill in result.confirmed_skills:
            print(f"\nSkill: {skill.preferred_label}")
            print(f"URI: {skill.skill_uri}")
            print(f"Matched phrase: {skill.matched_phrases}")

        print("\n========== AMBIGUOUS MATCHES ==========")

        for match in result.ambiguous_matches:
            print(f"\nPhrase: {match.matched_phrase}")

            for candidate in match.candidates:
                print(
                    f"  - {candidate.preferred_label}"
                    f" | {candidate.skill_uri}"
                )

        print("\n========== HIDDEN-LABEL REVIEW ==========")

        for item in result.review_matches:
            print(f"\nPhrase: {item.matched_phrases}")
            print(f"Skill: {item.preferred_label}")
            print(f"Evidence: {item.evidence_snippets}")

        print("\n========== SUMMARY ==========")
        print("Confirmed skills:", len(result.confirmed_skills))
        print("Ambiguous phrases:", len(result.ambiguous_matches))
        print("Hidden-label reviews:", len(result.review_matches))
        print("Candidate phrases:", result.candidate_phrase_count)
        print("Database rows returned:", result.catalog_row_count)

        print("\nSupabase integration test completed.")

    except Exception as error:
        print("\nSupabase integration failed.")
        print(f"Error: {type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    main()
