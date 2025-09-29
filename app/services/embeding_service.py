import logging
import asyncio

from google import genai
from google.genai import types
from dotenv import load_dotenv
from enum import Enum


load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EmbeddingTaskType(str, Enum):
    RETRIEVAL_QUERY = "RETRIEVAL_QUERY"
    RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"


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

    client = genai.Client()

    if not json_contents:
        logger.warning("create_embedding called with empty json_contents")
        return None

    # Ensure the API receives a list (the SDK expects an iterable of contents)
    contents_list = list(json_contents)

    try:
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=contents_list,
            config=types.EmbedContentConfig(
                output_dimensionality=3072,
                task_type=task_type.value,
                title=title.value if isinstance(title, TitleType) else str(title),
            ),
        )

        embeddings = getattr(result, "embeddings", None)
        if embeddings and len(embeddings) > 0:
            embedding_obj = embeddings[0]
            embedding_values = getattr(embedding_obj, "values", None)
            if embedding_values:
                length = len(embedding_values)
                logger.info(
                    "Created embedding (length=%d) for task=%s", length, task_type
                )
                return embedding_values
            else:
                logger.warning("Embedding object returned without values")
                return None
        else:
            logger.warning("No embeddings returned from the API for task=%s", task_type)
            return None

    except Exception as exc:
        logger.exception("Failed to create embedding: %s", exc)
        return None


async def create_embedding_async(
    json_contents,
    task_type: EmbeddingTaskType,
    title: TitleType | str,
):
    """Async wrapper for create_embedding"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: create_embedding(json_contents, task_type, title)
    )
