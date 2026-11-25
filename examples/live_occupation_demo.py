
import json
import os

from dotenv import load_dotenv
from supabase import create_client
from services.skill_recognition import SupabaseSkillCatalog

load_dotenv()


def print_section(title):
    print(f"\n========== {title} ==========")


def main():
    # 1. Load Supabase credentials
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        raise SystemExit(
            "Missing SUPABASE_URL or SUPABASE_ANON_KEY."
        )

    try:
        # 2. Connect to Supabase
        client = create_client(url, key)

        # 3. Initialise the ESCO skill recognition engine
        catalog = SupabaseSkillCatalog(
            client,
            chunk_size=500
        )

        # 4. Marketing-focused test resume
        resume_text = (
            "Digital marketing specialist with experience "
            "conducting search engine optimisation for client websites. "
            "Developed content marketing strategies. "
            "Used web analytics to measure campaign performance. "
            "Used email marketing execution to support campaign outreach. "
            "Conducted market research."
        )

        # 5. Recognise skills from the resume
        result = catalog.recognise(resume_text)

        # 6. Display confirmed skills
        print_section("CONFIRMED SKILLS")

        for skill in result.confirmed_skills:
            print(f"\nSkill: {skill.preferred_label}")
            print(f"URI: {skill.skill_uri}")
            print(f"Matched phrase: {skill.matched_phrases}")

        # 7. Display ambiguous matches
        print_section("AMBIGUOUS MATCHES")

        if result.ambiguous_matches:
            for match in result.ambiguous_matches:
                print(f"\nPhrase: {match.matched_phrase}")

                for candidate in match.candidates:
                    print(
                        f"  - {candidate.preferred_label}"
                        f" | {candidate.skill_uri}"
                    )
        else:
            print("No ambiguous matches.")

        # 8. Display hidden-label matches requiring review
        print_section("HIDDEN-LABEL REVIEW")

        if result.review_matches:
            for item in result.review_matches:
                print(f"\nPhrase: {item.matched_phrases}")
                print(f"Skill: {item.preferred_label}")
                print(f"Evidence: {item.evidence_snippets}")
        else:
            print("No hidden-label matches requiring review.")

        # 9. Extract only confirmed skill URIs
        confirmed_uris = result.confirmed_skill_uris

        print_section("SKILLS SENT TO OCCUPATION MATCHING")
        print("Confirmed skill URIs:", len(confirmed_uris))

        for uri in confirmed_uris:
            print(uri)

        if not confirmed_uris:
            print("\nNo confirmed skills available for occupation matching.")
            return

        # 10. Rank ESCO occupations
        print_section("OCCUPATION MATCHING")

        ranking_response = client.rpc(
            "rank_esco_occupations",
            {
                "p_matched_skill_uris": confirmed_uris,
                "p_isco_major_groups": ["1", "2", "3", "4", "5"],
                "p_min_matched_essential": 2,
                "p_include_all": False
            }
        ).execute()

        occupations = ranking_response.data or []

        print("Occupations returned:", len(occupations))

        # 11. Display the top 10 occupation results
        print_section("TOP 10 OCCUPATIONS")

        if occupations:
            for rank, occupation in enumerate(occupations[:10], start=1):
                print(f"\nRank #{rank}")

                print(
                    json.dumps(
                        occupation,
                        indent=2,
                        ensure_ascii=False
                    )
                )
        else:
            print("No occupations passed the current ranking filters.")

        # 12. Display pipeline summary
        print_section("PIPELINE SUMMARY")

        print("Confirmed skills:", len(result.confirmed_skills))
        print("Ambiguous matches:", len(result.ambiguous_matches))
        print("Hidden-label reviews:", len(result.review_matches))
        print("Candidate phrases:", result.candidate_phrase_count)
        print("Database rows returned:", result.catalog_row_count)
        print("Occupation results:", len(occupations))

        print("\nEnd-to-end test completed successfully.")

    except Exception as error:
        print("\nOccupation matching test failed.")
        print(f"Error: {type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    main()
