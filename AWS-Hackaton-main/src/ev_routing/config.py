import os
from typing import Optional

from pydantic import BaseModel, Field

from .contracts import SolverConfig


class AppConfig(BaseModel):
    aws_region: str = Field(default_factory=lambda: os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    bedrock_model_id: Optional[str] = Field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID"))
    aws_profile: Optional[str] = Field(default_factory=lambda: os.getenv("AWS_PROFILE"))
    default_solver_config: SolverConfig = Field(default_factory=SolverConfig)
