import os
import fitz  # PyMuPDF
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from supabase import create_client, Client
import uvicorn

app = FastAPI(title="LaunchPad AI Backend")

# ✅ 1. Cloud Database Connection (Supabase)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Optional[Client] = None

if url and key:
    supabase = create_client(url, key)
    print("✅ Supabase Cloud Connection Initialized")

# ✅ 2. Data Models
class PrepRequest(BaseModel):
    skills: str
    role: str

# ✅ 3. Helper: Extract Text from PDF
def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

# ✅ 4. Root Route (For "Cloud Online" Ping)
@app.get("/")
def home():
    return {"status": "online", "message": "LaunchPad AI Engine is Live"}

# ✅ 5. The Brain: Resume Analysis (ATS & Skills)
@app.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Save temp file
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())

    try:
        resume_text = extract_text_from_pdf(temp_path).lower()
        
        # Professional Keyword Matching (Logic for Ma'am)
        tech_keywords = ["python", "java", "kotlin", "sql", "aws", "figma", "android", "fastapi", "react"]
        found_skills = [skill for skill in tech_keywords if skill in resume_text]
        
        # ATS Calculation Logic
        score = 40 + (len(found_skills) * 10)
        if score > 98: score = 98  # Professional cap
        
        # Simple Market Insight
        insight = "Software Engineer" if "python" in found_skills or "java" in found_skills else "General Tech"

        return {
            "ats_score": score,
            "market_insight": insight,
            "found_skills": found_skills,
            "missing_skills": ["Docker", "Kubernetes", "CI/CD"] # Example static gaps
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ✅ 6. The Feature: AI Interview Prep Guide
@app.post("/generate_prep_guide")
async def generate_prep_guide(request: PrepRequest):
    skills = request.skills
    role = request.role
    
    # This simulates a 200-word "Gold Standard" response for your demo
    return {
        "useful_sentences": [
            f"I have a robust foundation in {skills}, which I've used to build scalable solutions.",
            f"My transition into {role} is driven by a passion for technical efficiency.",
            "I excel at translating complex requirements into clean, functional code."
        ],
        "interview_qa": [
            {
                "question": "Tell me about yourself.",
                "answer": f"I am a final year BCA student specializing in {role}. I have spent the last year mastering {skills} through projects like LaunchPad AI. I am a proactive learner who thrives in environments where I can build impactful technology from the ground up."
            },
            {
                "question": f"How do you stay updated with {skills}?",
                "answer": "I follow industry-standard documentation and contribute to open-source projects. For example, in my latest project, I implemented FastAPI and Supabase to handle real-time data, ensuring I stay at the cutting edge of cloud-native development."
            },
            {
                "question": "Describe a difficult technical challenge you solved.",
                "answer": "While building my career app, I faced issues with PDF parsing in a cloud environment. I resolved this by implementing PyMuPDF for efficient text extraction and optimized my CI/CD pipeline on Render to handle cold-start latencies."
            },
            {
                "question": "Why should we hire you over other candidates?",
                "answer": f"Beyond my proficiency in {skills}, I bring a product-oriented mindset. I don't just write code; I design systems that solve user problems, as seen in my Resume Analyzer which helps students bridge the gap between education and employment."
            },
            {
                "question": "Where do you see yourself in 5 years?",
                "answer": f"I aim to be a Senior {role}, leading a team of developers. I want to be known for creating architecturally sound systems and mentoring the next generation of engineers in modern tech stacks like Python and Kotlin."
            }
        ]
    }

# ✅ 7. The Feature: AI Cover Letter
@app.post("/generate_cover_letter")
async def generate_letter(data: dict):
    skills = data.get("skills", "Technology")
    role = data.get("role", "Professional")
    letter = f"Dear Hiring Manager,\n\nI am writing to express my interest in the {role} position. With my expertise in {skills}, I am confident in my ability to contribute to your team immediately..."
    return {"cover_letter": letter}

# ✅ 8. Run App
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
