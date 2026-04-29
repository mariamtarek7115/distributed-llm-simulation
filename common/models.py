from pydantic import BaseModel, Field
from typing import Optional
import time


class AIRequest(BaseModel):
    request_id: int
    user_id: int
    prompt: str
    use_rag: bool = True
    priority: int = 1
    created_at: float = Field(default_factory=time.time)


class AIResponse(BaseModel):
    request_id: int
    worker_id: int
    answer: str
    latency: float
    success: bool = True
    error: Optional[str] = None