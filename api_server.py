from fastapi import FastAPI
from pydantic import BaseModel
import os
import asyncio
import uvicorn
import time

from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler

app = FastAPI()
latencies = []

#b3ml printing ll latencies 3ashan a3raf a3raf el performance bta3 el system, w baadein akarar ba a keep it ezay

# -----------------------
# WORKERS (IMPORTANT FIX)
# -----------------------
worker_urls = [
    url.strip()
    for url in os.getenv("OLLAMA_WORKERS", "").split(",")
    if url.strip()
]

if not worker_urls:
    raise ValueError("No workers provided in OLLAMA_WORKERS")

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
@app.post("/reset_metrics")
def reset_metrics():
    global latencies
    latencies = []
    return {"status": "metrics reset"}


@app.post("/chat")
async def chat(req: ChatRequest):
    payload = {
        "user_id": req.user_id,
        "prompt": req.prompt,
        "use_rag": req.use_rag
    }

    result = await scheduler.handle_request(payload)

    # 🔥 CLEAN OUTPUT (NO FULL TEXT)
    return {
        "worker_id": result["worker_id"],
        "latency": result["latency"],
        "answer_preview": result["answer"][:80]  # 👈 IMPORTANT FIX
    }


@app.get("/final_report")
def final_report():
    if not latencies:
        return {"message": "No data collected yet"}

    return {
        "total_requests": len(latencies),
        "avg_latency": sum(latencies) / len(latencies),
        "min_latency": min(latencies),
        "max_latency": max(latencies)
    }
# -----------------------
# RUN SERVER
# -----------------------
if __name__ == "__main__":
    print("API Gateway running on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)