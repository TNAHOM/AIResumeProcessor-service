from typing import Optional, Sequence

# Optional imports with fallbacks
try:
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    np = None
    cosine_similarity = None
    SKLEARN_AVAILABLE = False


def similarity_search(
    resumeData: Optional[Sequence[float]], jobPostData: Optional[Sequence[float]]
) -> float:
    """Calculate cosine similarity between resume and job post embeddings."""
    
    if resumeData is None or jobPostData is None:
        raise ValueError("Both embeddings must be provided (not None).")
    
    if not SKLEARN_AVAILABLE:
        # Simple fallback using dot product approximation
        return calculate_score(list(resumeData), list(jobPostData))
    
    # Reshape into (1, n_features)
    embeddings_resume_matrix = np.array(resumeData).reshape(1, -1)
    embeddings_jobPost_matrix = np.array(jobPostData).reshape(1, -1)

    similarity = cosine_similarity(embeddings_resume_matrix, embeddings_jobPost_matrix)[0][0]
    return float(similarity)


def calculate_embedding_similarity(embedding1: list, embedding2: list) -> float:
    """Calculate similarity score between two embeddings with fallback implementation."""
    
    if not embedding1 or not embedding2:
        return 0.0
    
    if SKLEARN_AVAILABLE:
        return similarity_search(embedding1, embedding2)
    
    # Simple fallback: normalized dot product (approximates cosine similarity)
    try:
        # Ensure equal length
        min_len = min(len(embedding1), len(embedding2))
        vec1 = embedding1[:min_len]
        vec2 = embedding2[:min_len]
        
        # Calculate dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Calculate magnitudes
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        # Cosine similarity
        similarity = dot_product / (magnitude1 * magnitude2)
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
        
    except Exception:
        # Ultimate fallback
        return 0.5


# Alias for backward compatibility
calculate_score = calculate_embedding_similarity


def calculate_overall_score(description, requirement, responsibility, ai_score, penality):
    """Calculate overall ATS score from multiple factors."""
    return (
        (requirement * 40)
        + (responsibility * 30)
        + (description * 20)
        + (ai_score * 10)
    ) - penality
