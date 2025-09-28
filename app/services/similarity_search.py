import numpy as np
from typing import Optional, Sequence
from sklearn.metrics.pairwise import cosine_similarity


def similarity_search(
    resumeData: Optional[Sequence[float]], jobPostData: Optional[Sequence[float]]
) -> float:
    if resumeData is None or jobPostData is None:
        raise ValueError("Both embeddings must be provided (not None).")

    # Reshape into (1, n_features)
    embeddings_resume_matrix = np.array(resumeData).reshape(1, -1)
    embeddings_jobPost_matrix = np.array(jobPostData).reshape(1, -1)

    similarity = cosine_similarity(embeddings_resume_matrix, embeddings_jobPost_matrix)[
        0
    ][0]

    return float(similarity)


def calculate_score(description, requirement, responsibility, ai_score, penality):
    return (
        (requirement * 40)
        + (responsibility * 30)
        + (description * 20)
        + (ai_score * 10)
    ) - penality
