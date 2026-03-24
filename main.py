import os
import fitz  # PyMuPDF
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from supabase import create_client, Client
import uvicorn

app = FastAPI(title="LaunchPad AI Backend")

# ✅ 1. Cloud Database Connection
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Optional[Client] = None

if url and key:
    try:
        supabase = create_client(url, key)
        print("✅ Supabase Cloud Connection Initialized")
    except Exception as e:
        print(f"❌ Supabase Error: {e}")

# ✅ 2. Sector Keyword Mapping (The "Intelligence" Layer)
SECTORS = {
    "Developer": ["python", "java", "kotlin", "android", "sql", "aws", "git", "fastapi", "react", "mongodb"],
    "Marketing": ["seo", "google analytics", "social media", "sem", "content strategy", "copywriting", "email marketing", "ads"],
    "Finance": ["accounting", "excel", "tally", "audit", "taxation", "investments", "banking", "fintech", "gst"]
}

class PrepRequest(BaseModel):
    skills: str
    role: str

# ✅ 3. Helper: Extract Text
def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

@app.get("/")
def home():
    return {"status": "online", "message": "LaunchPad AI Engine is Live"}

# ✅ 4. The Brain: Sector ID + ATS + Roadmap
@app.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())

    try:
        resume_text = extract_text_from_pdf(temp_path).lower()
        
        # Identify User Sector
        user_sector = "General Tech"
        max_matches = 0
        for sector, keywords in SECTORS.items():
            matches = len([k for k in keywords if k in resume_text])
            if matches > max_matches:
                max_matches = matches
                user_sector = sector

        # Calculate Strengths & Roadmap
        sector_keywords = SECTORS.get(user_sector, [])
        found_skills = [k for k in sector_keywords if k in resume_text]
        missing_skills = [k for k in sector_keywords if k not in resume_text]
        
        # Professional ATS Scoring
        score = 40 + (len(found_skills) * 10)
        if score > 98: score = 98

        return {
            "ats_score": score,
            "market_insight": user_sector,
            "core_strengths": found_skills,
            "priority_roadmap": missing_skills[:4],  # Top 4 missing items
            "improvement_tip": f"To reach a perfect score in {user_sector}, focus on adding projects involving {', '.join(missing_skills[:2])}."
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ✅ 5. Detailed Interview Prep Guide
@app.post("/generate_prep_guide")
async def generate_prep_guide(request: PrepRequest):
    skills = request.skills
    role = request.role
    
    return {
        "useful_sentences": [
            f"I have a robust foundation in {skills}, which I've used to build scalable solutions.",
            f"My transition into {role} is driven by a passion for technical efficiency.",
            "I excel at translating complex requirements into clean, functional code."
        ],
        "interview_qa": [
            {
                "question": "Tell me about yourself.",
                "answer": f"I am a final year BCA student specializing in {role}. I have spent the last year mastering {skills} through projects like LaunchPad AI. I am a proactive learner who thrives in environments where I can build impactful technology."
            },
            {
                "question": f"How do you stay updated with {skills}?",
                "answer": "I follow industry-standard documentation and contribute to open-source projects. I implemented FastAPI and Supabase in my latest project to handle real-time data, ensuring I stay at the cutting edge."
            },
            {
                "question": "Describe a difficult technical challenge you solved.",
                "answer": "While building my career app, I faced issues with PDF parsing in a cloud environment. I resolved this by implementing PyMuPDF for efficient text extraction and optimized my CI/CD pipeline on Render."
            },
            {
                "question": "Why should we hire you over other candidates?",
                "answer": f"Beyond my proficiency in {skills}, I bring a product-oriented mindset. I don't just write code; I design systems that solve user problems, as seen in my Resume Analyzer project."
            },
            {
                "question": "Where do you see yourself in 5 years?",
                "answer": f"I aim to be a Senior {role}, leading a team of developers. I want to be known for creating architecturally sound systems using modern tech stacks like Python and Kotlin."
            }
        ]
    }

# ✅ 6. AI Cover Letter
@app.post("/generate_cover_letter")
async def generate_letter(data: dict):
    skills = data.get("skills", "Technology")
    role = data.get("role", "Professional")
    letter = f"Dear Hiring Manager,\n\nI am writing to express my interest in the {role} position. With my expertise in {skills}, I am confident in my ability to contribute to your team..."
    return {"cover_letter": letter}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
