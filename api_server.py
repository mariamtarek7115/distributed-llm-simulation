from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import uvicorn

from common.config import load_config
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler

app = FastAPI()
config = load_config()

lb = LoadBalancer(
    config.worker_urls,
    backend="ollama",
    model_name=config.model_name,
    worker_health_urls=config.worker_health_urls,
    worker_metrics_urls=config.worker_metrics_urls,
    strategy=config.load_balancer_strategy,
)
scheduler = Scheduler(
    lb,
    max_workers=config.max_workers,
    queue_size=config.queue_size,
    retry_workers=config.retry_workers,
    max_retries=config.max_retries,
    request_timeout=config.request_timeout,
)

# -----------------------
# STARTUP (heartbeat)
# -----------------------
@app.on_event("startup")
async def startup():
    await lb.start_background_tasks()
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
    print("Workers:", config.worker_urls)
    print("Strategy:", config.load_balancer_strategy)
    print("Model:", config.model_name)
    uvicorn.run(app, host="0.0.0.0", port=8000)