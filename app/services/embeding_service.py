import logging

import google.generativeai as genai
from dotenv import load_dotenv
from enum import Enum


load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EmbeddingTaskType(str, Enum):
    RETRIEVAL_QUERY = "retrieval_query"
    RETRIEVAL_DOCUMENT = "retrieval_document"  
    SEMANTIC_SIMILARITY = "semantic_similarity"


class TitleType(str, Enum):
    APPLICANT_RESUME = "This is an applicant's resume to be embedded"
    RECRUITER_JOB_DESCRIPTION = (
        "This is a job description of a recruiter to be embedded"
    )


def create_embedding(
    json_contents,
    task_type: EmbeddingTaskType,
    title: TitleType | str,
):
    from app.core.config import settings
    
    # Configure the API key
    genai.configure(api_key=settings.GEMINI_API_KEY)

    if not json_contents:
        logger.warning("create_embedding called with empty json_contents")
        return None

    # Ensure the API receives a list of strings
    if isinstance(json_contents, dict):
        # Convert dict to list of strings
        contents_list = [str(v) for v in json_contents.values()]
    elif isinstance(json_contents, list):
        contents_list = [str(item) for item in json_contents]
    else:
        contents_list = [str(json_contents)]

    try:
        # Use the correct method for the google-generativeai package
        result = genai.embed_content(
            model="models/embedding-001",
            content="\n".join(contents_list),  # Join content into single string
            task_type=task_type.value,
            title=title.value if isinstance(title, TitleType) else str(title),
        )

        if result and "embedding" in result:
            embedding_values = result["embedding"]
            logger.info(
                "Created embedding (length=%d) for task=%s", 
                len(embedding_values), task_type
            )
            return embedding_values
        else:
            logger.warning("No embedding returned from the API for task=%s", task_type)
            return None

    except Exception as exc:
        logger.exception("Failed to create embedding: %s", exc)
        return None
