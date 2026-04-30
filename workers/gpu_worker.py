from fastapi import FastAPI, Request
from llm.inference import LLMHandler
import time
import sys
import asyncio

app = FastAPI()
model = LLMHandler()

def get_worker_id():
    for arg in sys.argv:
        if arg.startswith("--port="):
            return arg.split("=")[1]
        elif arg == "--port":
            index = sys.argv.index(arg)
            return sys.argv[index + 1]
    return "Unknown"

WORKER_ID = f"Port-{get_worker_id()}"

# ZERAR EL MOCKING: Khaly da True w enta bt-test el 1000 users, w False law 3ayez el AI be-gad
MOCK_MODE = True 

@app.post("/process")
async def process_request(request: dict):
    start_time = time.time()
    
    prompt_received = request['prompt']
    
    if MOCK_MODE:
        # 1. Simulate Heavy Processing (0.2 seconds delay without burning CPU)
        await asyncio.sleep(0.2) 
        
        # 2. Return a mock answer that PROVES we received the RAG context
        # Han-extract awel 30 harf mn el prompt 3ashan nwarry el Dr. enna estalamna el context
        response_text = f"[MOCK FAST-RESPONSE] Model processed context: {prompt_received[:40]}..." 
    else:
        # Real AI Inference
        response_text = model.generate(prompt_received)
    
    latency = time.time() - start_time
    return {
        "worker_id": WORKER_ID,
        "answer": response_text,
        "latency": latency
    }