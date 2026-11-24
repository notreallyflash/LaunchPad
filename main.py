import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pymupdf  # PyMuPDF
import pytesseract
from PIL import Image

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from supabase import Client, create_client

import uvicorn


# ============================================================
# 1. APPLICATION CONFIGURATION
# ============================================================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="LaunchPad AI Backend",
    description="Resume analysis and career preparation API"
)

MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PDF_PAGES = 15
MIN_TEXT_LENGTH_FOR_OCR = 80
OCR_PAGE_TIMEOUT_SECONDS = 20
OCR_RENDER_SCALE = 2.5


# ============================================================
# 2. TESSERACT OCR CONFIGURATION
# ============================================================

def configure_tesseract() -> None:
    """Locate the Tesseract executable on Windows or Linux."""

    configured_path = os.getenv("TESSERACT_CMD")

    if configured_path:
        pytesseract.pytesseract.tesseract_cmd = configured_path
        logger.info("Using Tesseract from TESSERACT_CMD.")
        return

    if os.name == "nt":
        windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        if os.path.isfile(windows_path):
            pytesseract.pytesseract.tesseract_cmd = windows_path
            logger.info("Windows Tesseract installation detected.")
            return

    detected_path = shutil.which("tesseract")

    if detected_path:
        pytesseract.pytesseract.tesseract_cmd = detected_path
        logger.info("Tesseract installation detected.")
    else:
        logger.warning(
            "Tesseract was not found. OCR will be unavailable "
            "until the executable is installed and configured."
        )


configure_tesseract()


# ============================================================
# 3. SUPABASE CONFIGURATION
# ============================================================

def initialize_supabase() -> Optional[Client]:
    """Initialize Supabase when environment credentials exist."""

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        logger.info("Supabase credentials not configured.")
        return None

    try:
        client = create_client(url, key)
        logger.info("Supabase client initialized.")
        return client

    except Exception:
        logger.exception("Supabase initialization failed.")
        return None


supabase = initialize_supabase()


# ============================================================
# 4. RESUME CLASSIFICATION CONFIGURATION
# ============================================================

SECTORS = {
    "Developer": [
        "python",
        "java",
        "kotlin",
        "android",
        "sql",
        "aws",
        "git",
        "fastapi",
        "react",
        "mongodb"
    ],

    "Marketing": [
        "seo",
        "google analytics",
        "social media",
        "sem",
        "content strategy",
        "copywriting",
        "email marketing",
        "ads"
    ],

    "Finance": [
        "accounting",
        "excel",
        "tally",
        "audit",
        "taxation",
        "investments",
        "banking",
        "fintech",
        "gst"
    ]
}


# ============================================================
# 5. REQUEST MODELS
# ============================================================

class PrepRequest(BaseModel):
    skills: str
    role: str


class CoverLetterRequest(BaseModel):
    skills: str = "Technology"
    role: str = "Professional"


# ============================================================
# 6. PDF TEXT EXTRACTION AND OCR
# ============================================================

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract selectable text from a PDF.

    If a page contains very little selectable text,
    render that page and use Tesseract OCR.
    """

    extracted_pages = []

    with pymupdf.open(file_path) as document:

        if document.needs_pass:
            raise ValueError("Password-protected PDFs are not supported.")

        if len(document) == 0:
            raise ValueError("The uploaded PDF contains no pages.")

        if len(document) > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF exceeds the maximum of {MAX_PDF_PAGES} pages."
            )

        for page_number, page in enumerate(document, start=1):

            # First attempt normal PDF text extraction.
            text = page.get_text("text").strip()

            # Fall back to OCR when little text is available.
            if len(text) < MIN_TEXT_LENGTH_FOR_OCR:

                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(
                        OCR_RENDER_SCALE,
                        OCR_RENDER_SCALE
                    ),
                    colorspace=pymupdf.csRGB,
                    alpha=False
                )

                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples
                )

                try:
                    ocr_text = pytesseract.image_to_string(
                        image,
                        lang="eng",
                        config="--psm 3",
                        timeout=OCR_PAGE_TIMEOUT_SECONDS
                    ).strip()

                    if len(ocr_text) > len(text):
                        text = ocr_text

                    logger.info(
                        "OCR completed for PDF page %s.",
                        page_number
                    )

                except pytesseract.TesseractNotFoundError:
                    logger.exception(
                        "Tesseract executable unavailable on page %s.",
                        page_number
                    )

                except (
                    pytesseract.TesseractError,
                    RuntimeError
                ):
                    logger.exception(
                        "OCR failed on PDF page %s.",
                        page_number
                    )

                finally:
                    image.close()

            extracted_pages.append(text)

    return "\n".join(extracted_pages)


# ============================================================
# 7. RESUME ANALYSIS HELPERS
# ============================================================

def normalize_text(text: str) -> str:
    """Normalize extracted resume text for keyword matching."""

    return re.sub(r"\s+", " ", text.lower()).strip()


def contains_keyword(text: str, keyword: str) -> bool:
    """Match a keyword without accidental partial-word matches."""

    pattern = (
        rf"(?<![a-z0-9])"
        rf"{re.escape(keyword)}"
        rf"(?![a-z0-9])"
    )

    return re.search(pattern, text) is not None


def classify_resume(resume_text: str) -> tuple[str, list[str], list[str]]:
    """Determine the strongest matching sector and its skills."""

    sector_scores = {
        sector: sum(
            contains_keyword(resume_text, keyword)
            for keyword in keywords
        )
        for sector, keywords in SECTORS.items()
    }

    user_sector = max(
        sector_scores,
        key=sector_scores.get
    )

    if sector_scores[user_sector] == 0:
        user_sector = "General Tech"

    sector_keywords = SECTORS.get(user_sector, [])

    found_skills = [
        keyword
        for keyword in sector_keywords
        if contains_keyword(resume_text, keyword)
    ]

    missing_skills = [
        keyword
        for keyword in sector_keywords
        if not contains_keyword(resume_text, keyword)
    ]

    return user_sector, found_skills, missing_skills


def calculate_resume_score(found_skills: list[str]) -> int:
    """
    Legacy heuristic score retained for Android compatibility.

    This is not a validated ATS score or a prediction of
    whether a recruiter will shortlist the applicant.
    """

    return min(40 + (len(found_skills) * 10), 98)


# ============================================================
# 8. API: HEALTH CHECK
# ============================================================

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "LaunchPad AI Engine is Live"
    }


# ============================================================
# 9. API: RESUME UPLOAD AND ANALYSIS
# ============================================================

@app.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...)):

    filename = file.filename or ""

    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    contents = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty."
        )

    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The PDF exceeds the 15 MB upload limit."
        )

    temp_path = None

    try:
        # Create a safe temporary file.
        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False
        ) as temporary_file:

            temporary_file.write(contents)
            temp_path = temporary_file.name

        # Run CPU-intensive PDF and OCR processing outside
        # the asynchronous event loop.
        extracted_text = await run_in_threadpool(
            extract_text_from_pdf,
            temp_path
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        ) from error

    except Exception as error:
        logger.exception("Resume processing failed.")

        raise HTTPException(
            status_code=400,
            detail="Unable to process this PDF. Please upload a valid, unencrypted PDF."
        ) from error

    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    resume_text = normalize_text(extracted_text)

    if not resume_text:
        raise HTTPException(
            status_code=422,
            detail="No readable text was found. Please upload a clearer PDF."
        )

    # Identify sector and skills.
    user_sector, found_skills, missing_skills = classify_resume(
        resume_text
    )

    # Calculate the existing compatibility score.
    score = calculate_resume_score(found_skills)

    focus_skills = ", ".join(missing_skills[:2])

    if not focus_skills:
        focus_skills = (
            "strengthening your experience and measurable achievements"
        )

    return {
        "ats_score": score,
        "market_insight": user_sector,
        "core_strengths": found_skills,
        "priority_roadmap": missing_skills[:4],
        "improvement_tip": (
            f"To improve your profile for {user_sector}, "
            f"focus on {focus_skills}."
        )
    }


# ============================================================
# 10. API: INTERVIEW PREPARATION
# ============================================================

@app.post("/generate_prep_guide")
async def generate_prep_guide(request: PrepRequest):

    skills = request.skills
    role = request.role

    return {
        "useful_sentences": [
            (
                f"I have a robust foundation in {skills}, "
                "which I've used to build scalable solutions."
            ),
            (
                f"My transition into {role} is driven "
                "by a passion for technical efficiency."
            ),
            (
                "I excel at translating complex requirements "
                "into clean, functional solutions."
            )
        ],

        "interview_qa": [
            {
                "question": "Tell me about yourself.",
                "answer": (
                    f"I am a candidate specializing in {role}. "
                    f"I have developed my skills in {skills} "
                    "through practical projects and continuous learning."
                )
            },
            {
                "question": f"How do you stay updated with {skills}?",
                "answer": (
                    "I follow industry documentation, learn through "
                    "practical projects and keep up with developments "
                    "in my field."
                )
            },
            {
                "question": "Describe a difficult challenge you solved.",
                "answer": (
                    "While developing my career application, "
                    "I faced challenges with PDF parsing. "
                    "I worked through the problem using PyMuPDF "
                    "and OCR technologies."
                )
            },
            {
                "question": "Why should we hire you?",
                "answer": (
                    f"My knowledge of {skills}, combined with "
                    "a problem-solving and product-oriented mindset, "
                    "allows me to contribute to practical solutions."
                )
            },
            {
                "question": "Where do you see yourself in five years?",
                "answer": (
                    f"I aim to grow into an experienced {role}, "
                    "take on greater responsibilities and contribute "
                    "to meaningful projects."
                )
            }
        ]
    }


# ============================================================
# 11. API: COVER LETTER GENERATION
# ============================================================

@app.post("/generate_cover_letter")
async def generate_letter(request: CoverLetterRequest):

    letter = (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my interest in the "
        f"{request.role} position. With my expertise in "
        f"{request.skills}, I am confident in my ability "
        "to contribute to your team..."
    )

    return {
        "cover_letter": letter
    }


# ============================================================
# 12. APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
