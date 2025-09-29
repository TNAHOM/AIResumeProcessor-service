from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Type

import google.generativeai as genai
from dotenv import load_dotenv
from app.schemas.gemini_output import ResumeOutput
from app.core.config import settings


load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _combine_grouped_resume_text(raw_resume_json: Dict[str, List[str]]) -> str:
    """Combine grouped resume JSON (page->lines) into a single text blob in numeric key order.

    Raises if keys are not numeric; mirrors prior behavior.
    """
    try:
        return "\n".join(
            line
            for key in sorted(raw_resume_json.keys(), key=int)
            for line in raw_resume_json[key]
        )
    except Exception:
        logger.exception("Failed to combine raw resume text")
        raise


def generate_json_with_gemini(
    *,
    prompt: str,
    response_schema: Type[Any],
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    model: str = "gemini-1.5-flash",
) -> Dict[str, Any]:
    """Generic helper to call Gemini and return a JSON-like dict conforming to response_schema.

    - prompt: full text prompt to send as contents
    - response_schema: Pydantic model (or schema supported by SDK)
    - system_instruction: optional system role instruction
    - temperature: sampling temperature
    - model: model name

    Returns a Python dict matching the schema. If SDK returns a parsed Pydantic object,
    it's converted to a dict.
    """
    GEMINI_API_KEY = settings.GEMINI_API_KEY
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in environment")
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    # Configure the API key
    genai.configure(api_key=GEMINI_API_KEY)

    response = None
    try:
        logger.info("Calling Gemini model=%s with typed response", model)
        
        # Create the model
        model_instance = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_instruction,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        
        response = model_instance.generate_content(prompt)
        
        if response and response.text:
            # Parse the JSON response
            json_result = json.loads(response.text)
            logger.info("Successfully parsed JSON response from Gemini")
            return json_result
        else:
            logger.warning("Empty response from Gemini")
            return {"error": "Empty response from Gemini"}

    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON from Gemini response: %s", e)
        raw_response = response.text if response else "N/A"
        return {
            "error": "Invalid JSON response from Gemini",
            "details": str(e),
            "raw_response": raw_response,
        }
    except Exception as e:
        logger.exception("Gemini call failed")
        raw_response = response.text if response else "N/A"
        return {
            "error": "Gemini call failed",
            "details": str(e),
            "raw_response": raw_response,
        }


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
    # 2. Prepare the resume text (unchanged combining logic, now via helper)
    combined_resume_text = _combine_grouped_resume_text(raw_resume_json)

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

7. **Skills and Technologies (include soft skills)**: Populate `skillsAndTechnologies` with BOTH hard skills
     (e.g., programming languages, frameworks, cloud platforms) and soft skills explicitly mentioned or strongly
     implied by the resume text.
     - Examples of soft skills to capture when present: leadership, communication, teamwork, collaboration,
         stakeholder management, presentation, mentoring, coaching, conflict resolution, adaptability, problem solving,
         time management, prioritization, negotiation, strategic thinking, product sense, cross-functional collaboration.
     - Derive soft skills from action phrases when clearly implied (e.g., "led a team" -> leadership; "presented to executives" -> presentation; "managed stakeholders" -> stakeholder management).
     - Normalize names to a canonical singular form where reasonable (e.g., "communications" -> "communication").
     - Deduplicate entries and keep concise, human-readable names.
     - DO NOT invent skills: include only those that are explicitly stated or strongly implied by responsibilities/achievements in the text.
"""

    prompt = f"{context_instruction}\n{hard_rules}\nRESUME_TEXT:\n---\n{combined_resume_text}\n---"

    system_instruction = "You are a meticulous and detail-oriented resume parsing AI(also you are a senior recruiter)."

    # Delegate to the generic helper
    result = generate_json_with_gemini(
        prompt=prompt,
        response_schema=ResumeOutput,
        system_instruction=system_instruction,
        temperature=0.2,
    )

    # Consistent return contract
    return result


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


def evaluate_resume_against_job_post(
    *,
    resume_text: dict,
    job_post: dict,
    temperature: float = 0.2,
    model: str = "gemini-1.5-flash",
) -> Dict[str, Any]:
    """Use Gemini to generate ATS-style strengths and weaknesses, given resume and JD text.

    Contract:
    - Inputs: resume_text (string), job_post (string)
    - Output: dict matching ATSEvaluation schema: {"strengths": [...], "weaknesses": [...], "score": float}
    - No numeric scoring is performed here.
    """

    system_prompt = (
        "You are an ATS (Applicant Tracking System) evaluation assistant.\n"
        "Your task is to analyze how well an applicant’s resume matches a job posting.\n"
        "The system has already calculated numeric similarity scores.\n"
        "You DO NOT calculate scores. Instead, you must generate:\n"
        '- "strengths": reasons why the applicant is a good fit \n'
        '- "weaknesses": reasons why the applicant may not be a good fit\n\n'
        '- "score": a numeric score from 1 to 10(float number) indicating overall fit using the job post information and the applicant resume (higher is better)\n\n'
        "Respond strictly in this JSON format:\n\n"
        '{\n  "strengths": [list of short bullet strings],\n  "weaknesses": [list of short bullet strings],\n  "score": numeric score float number\n}\n'
    )

    user_prompt = (
        f"JOB_POST:\n---\n{job_post}\n---\n\n"
        f"RESUME:\n---\n{resume_text}\n---\n"
        "Return only valid JSON per the required format."
    )

    # Local import to avoid module-level coupling issues
    from app.schemas.ats_evaluation import ATSEvaluation

    result = generate_json_with_gemini(
        prompt=user_prompt,
        response_schema=ATSEvaluation,
        system_instruction=system_prompt,
        temperature=temperature,
        model=model,
    )

    return result


async def evaluate_resume_against_job_post_async(
    *,
    resume_text: dict,
    job_post: dict,
    temperature: float = 0.2,
    model: str = "gemini-1.5-flash",
) -> Dict[str, Any]:
    """Async wrapper for ATS evaluation."""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: evaluate_resume_against_job_post(
            resume_text=resume_text,
            job_post=job_post,
            temperature=temperature,
            model=model,
        ),
    )
