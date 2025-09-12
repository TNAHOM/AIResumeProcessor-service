from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Dict

from google import genai
from google.genai import types
from dotenv import load_dotenv
from app.schemas.gemini_output import ResumeOutput
from app.core.config import settings


load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def structure_and_normalize_resume_with_gemini(
    raw_resume_json: Dict[str, Any],
) -> Dict[str, Any]:
    """Call Gemini to structure and normalize a resume.

    This keeps the original prompt and logic but adds: logging, optional api_key override,
    injectable client factory for easier testing, and consistent return types.

    Inputs:
    - raw_resume_json: mapping of page/segment -> list[str] (same as original code expects)
    - api_key: optional override for GEMINI_API_KEY environment var
    - client_factory: callable to instantiate a client object given an api_key

    Returns: JSON-like dict with parsed schema, or an error dict with keys: error, details, raw_response
    """
    GEMINI_API_KEY = settings.GEMINI_API_KEY
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in environment and no api_key provided")
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    # Instantiate client via factory (keeps core logic unchanged)
    client = genai.Client()

    # 2. Prepare the resume text (unchanged combining logic)
    try:
        combined_resume_text = "\n".join(
            line
            for key in sorted(raw_resume_json.keys(), key=int)
            for line in raw_resume_json[key]
        )
    except Exception:
        logger.exception("Failed to combine raw resume text")
        raise

    # 3. Build instructions / prompt (kept intact)
    context_instruction = """
You are an expert resume parsing AI. Your task is to analyze the provided resume text
and produce a fully normalized and structured JSON object that strictly adheres to
the provided schema. You must perform all calculations and text normalizations yourself.
"""

    hard_rules = f"""
HARD RULES (CRITICAL - DO NOT BREAK):

1. **Output Format**: Your entire output MUST be a single, valid JSON object that conforms
   to the schema. Do not output any text, code blocks, or explanations before or after the JSON.

2. **Date Calculation**: You MUST calculate the duration between start and end dates for all
   work experiences and projects.
      
   - The result MUST be an integer (and take the ceiling like if its a fraction) representing the total months.
   - Place this number in the `durationMonths` field. Do NOT include the original date strings
     in the output.
   - Handle terms like 'CURRENT', 'PRESENT', or 'NOW' by using today's date ({datetime.now().strftime('%Y-%m-%d')})
     as the end date for your calculation.
   - Example 1: A range of "09/12/2022 - 04/03/2023" should result in `"durationMonths": 5`.
   - Example 2: A range of "Jan 2022 - Dec 2023" should result in `"durationMonths": 24`.

3. **Acronym Expansion**: You MUST expand common technical and professional acronyms in ALL text fields
   of your final JSON output.
   - Example: If the resume says "experience with AWS and ERP systems", the corresponding output in fields
     like `description` or `skillsAndTechnologies` must contain "Amazon Web Services" and "Enterprise Resource Planning".
   - Common acronyms to expand include: AWS, GCP, ERP, CRM, SQL, CI/CD, API, DRF, HTML, CSS.

4. **Dynamic Domain Identification**: For the `monthsOfWorkExperienceByDomain` field, you MUST dynamically
   identify the key domains of expertise from the entire resume (consider only work experience not project experience for calculating this part monthsOfWorkExperienceByDomain).
   - Do NOT use a fixed list. Analyze the text to find the most relevant domains (e.g., "Full-Stack Development",
     "ERP Implementation", "Mobile Application Development", "Data Analysis", "Accountant", etc.).
   - For each domain you identify, create a JSON object with the domain name and the estimated total months
     of experience, aggregated from all relevant work and project entries.
   - The final output for this field should be an array of these objects, like:
     `[{{"domain": "ERP Implementation", "months": 18}}, {{"domain": "frontend Development", "months": 15}}, {{"domain": "product manager", "months": 6}}]`.

5. **Information Integrity**: Do NOT invent any information. If a piece of information required by the schema
   (e.g., a portfolio link) is not present, use an empty string "" or an empty array [].


6. **Education**: The output MUST include an `education` array. Each entry should contain at least
    `degree` and `institution` when available. Do not invent degrees or
    institutions; if missing, use an empty string.
"""

    prompt = f"{context_instruction}\n{hard_rules}\nRESUME_TEXT:\n---\n{combined_resume_text}\n---"

    response = None
    try:
        logger.info("Sending resume to Gemini model for parsing")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a meticulous and detail-oriented resume parsing AI(also you are a senior recruiter).",
                response_mime_type="application/json",
                response_schema=ResumeOutput,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        # The SDK may return structured result. Prefer parsed when available.
        if hasattr(response, "parsed") and response.parsed is not None:
            logger.info("Received parsed response from Gemini client")
            return response.parsed  # pyright: ignore[reportReturnType]
        else:
            # fallback: parse text if response.text is JSON
            logger.info(
                "Parsed attribute missing; falling back to response.text JSON parse"
            )
            return json.loads(response.text)  # pyright: ignore[reportArgumentType]

    except Exception as e:
        logger.exception("An error occurred during Gemini API call or processing")
        raw_response = (
            getattr(response, "text", "N/A") if response is not None else "N/A"
        )
        return {
            "error": "Failed to process resume with Gemini",
            "details": str(e),
            "raw_response": raw_response,
        }


async def structure_and_normalize_resume_with_gemini_async(
    raw_resume_json: Dict[str, Any],
) -> Dict[str, Any]:
    """Async wrapper for the synchronous Gemini call.

    This function runs the blocking operation in a thread to avoid blocking async event loops.
    It keeps the same return contract as the sync function.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: structure_and_normalize_resume_with_gemini(raw_resume_json),
    )
