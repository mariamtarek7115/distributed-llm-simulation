from fastapi import FastAPI
from pydantic import BaseModel
import os
import asyncio
import uvicorn

from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler

app = FastAPI()

# -----------------------
# WORKERS (IMPORTANT FIX)
# -----------------------
worker_urls = [
    "https://j87rla8a-11434.thundercompute.net",
    "https://8bby694v-11434.thundercompute.net",
    "https://rrs3mb7w-11434.thundercompute.net",
    "https://ln3xcktv-11434.thundercompute.net"
]

model = "tinyllama"

lb = LoadBalancer(worker_urls, backend="ollama", model_name=model)
scheduler = Scheduler(lb)

# -----------------------
# STARTUP (heartbeat)
# -----------------------
@app.on_event("startup")
async def startup():
    asyncio.create_task(lb.heartbeat_loop())

# -----------------------
# REQUEST FORMAT
# -----------------------
class ChatRequest(BaseModel):
    user_id: int
    prompt: str
    use_rag: bool = False

# -----------------------
# MAIN ENDPOINT
# -----------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    payload = {
        "user_id": req.user_id,
        "prompt": req.prompt,
        "use_rag": req.use_rag
    }

    return await scheduler.handle_request(payload)

# -----------------------
# RUN SERVER
# -----------------------
if __name__ == "__main__":
    print("API Gateway running on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)