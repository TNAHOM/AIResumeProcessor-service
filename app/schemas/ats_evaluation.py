from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List


class ATSEvaluation(BaseModel):
    strengths: List[str] = Field(
        default_factory=list, description="Reasons the candidate is a good fit"
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Reasons the candidate may not be a good fit"
    )
    score: float = Field(
        ..., description="Overall fit score from 1 to 10 (higher is better)"
    )
