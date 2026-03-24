import os
from supabase import create_client, Client

# ✅ This pulls the keys from the Render Environment Variables you set
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# This creates the connection to your database
if url and key:
    supabase: Client = create_client(url, key)
    print("✅ Supabase Cloud Connection Initialized")
else:
    print("⚠️ Warning: Supabase keys not found. Check Render Environment Variables.")
    
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import uvicorn
from typing import List

app = FastAPI()

class SkillList(BaseModel):
    skills: List[str]

# --- MODULE 16: MULTI-DOMAIN LIBRARIES ---
DOMAIN_LIBRARIES = {
    "TECH": ["PYTHON", "JAVA", "KOTLIN", "ANDROID", "JAVASCRIPT", "AWS", "DOCKER", "FIREBASE", "SQL", "REACT"],
    "DESIGN": ["FIGMA", "ADOBE XD", "CANVA", "UI", "UX", "PROTOTYPING", "WIREFRAMING", "ILLUSTRATOR"],
    "MARKETING": ["SEO", "SEM", "CONTENT STRATEGY", "GOOGLE ANALYTICS", "COPYWRITING", "SOCIAL MEDIA", "EMAIL MARKETING"],
    "BUSINESS_HR": ["RECRUITMENT", "PAYROLL", "ONBOARDING", "PROJECT MANAGEMENT", "AGILE", "STAKEHOLDER MANAGEMENT", "BUDGETING"]
}

def detect_domain(clean_text):
    scores = {domain: 0 for domain in DOMAIN_LIBRARIES}
    for domain, skills in DOMAIN_LIBRARIES.items():
        for skill in skills:
            if skill.lower() in clean_text:
                scores[domain] += 1
    
    # Return the domain with the most "hits", default to TECH
    best_domain = max(scores, key=scores.get)
    return best_domain if scores[best_domain] > 0 else "TECH"

@app.post("/upload_resume")
async def receive_resume(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        doc = fitz.open(stream=contents, filetype="pdf")
        raw_text = " ".join([page.get_text().lower() for page in doc])
        clean_text = " ".join(raw_text.split())

        # 1. Detect Domain
        user_domain = detect_domain(clean_text)
        target_skills = DOMAIN_LIBRARIES[user_domain]

        # 2. Audit Skills within that Domain
        found_skills = [s for s in target_skills if s.lower() in clean_text]
        missing_skills = [s for s in target_skills if s not in found_skills]

        # 3. Dynamic Scoring
        final_score = int((len(found_skills) / len(target_skills)) * 100) if target_skills else 0

        print(f"✅ Domain: {user_domain} | Score: {final_score}%")

        return {
            "status": "Success",
            "ats_score": final_score,
            "found_skills": found_skills,
            "missing_skills": missing_skills,
            "market_insight": f"Industry: {user_domain.replace('_', ' ')}",
            "feedback": f"LaunchPad optimized your score for the {user_domain.title()} sector."
        }
    except Exception as e:
        return {"status": "Error", "found_skills": [], "ats_score": 0}

@app.post("/generate_cover_letter")
async def generate_letter(data: SkillList):
    # Determine the context of the letter based on the skills provided
    primary_skill = data.skills[0] if data.skills else "Professional Services"
    
    # Check if user is Tech or Non-Tech to change the "Tone"
    is_tech = any(s in data.skills for s in DOMAIN_LIBRARIES["TECH"])
    
    opening = "I am a technical specialist" if is_tech else "I am a results-driven professional"
    
    letter_text = (
        f"Subject: Professional Application\n\n"
        f"Dear Hiring Manager,\n\n"
        f"{opening} with a strong background in {primary_skill}. "
        f"I am writing to express my interest in joining your team. "
        f"Having successfully applied my skills in {', '.join(data.skills[:3])}, "
        f"I am confident in my ability to drive success in your organization.\n\n"
        f"I look forward to discussing how my unique perspective can benefit your "
        f"current goals. Thank you for your time.\n\n"
        f"Sincerely,\n[Your Name]"
    )
    
    return {"letter": letter_text}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)