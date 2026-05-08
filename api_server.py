from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler
import asyncio

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(lb.heartbeat_loop())

# N-setup el Load Balancer w el Scheduler m3 el 4 workers
worker_urls = [
    "http://127.0.0.1:8001", 
    "http://127.0.0.1:8002", 
    "http://127.0.0.1:8003", 
    "http://127.0.0.1:8004"
]
lb = LoadBalancer(worker_urls)
scheduler = Scheduler(lb)

# Format el Data elly gaya mn Locust
class ChatRequest(BaseModel):
    user_id: int
    prompt: str
    use_rag: bool = True

# El Endpoint elly Locust hay-Drob 3aleh
@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    payload = {
        "user_id": req.user_id, 
        "prompt": req.prompt, 
        "use_rag": req.use_rag
    }
    # N-b3at el request lel Scheduler (elly hyzbt el RAG w y-forward lel LB)
    response = await scheduler.handle_request(payload)
    return response

if __name__ == "__main__":
    print("🚀 API Gateway / Load Balancer started on Port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)