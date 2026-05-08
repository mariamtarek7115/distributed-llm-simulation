import asyncio
import time
import random

# As2ela mo5talefa 3ashan n-test el RAG bytl3 contexts mo5talefa
QUESTIONS = [
    "Where is Ain Shams University?",
    "What do we learn in CSE354?",
    "How does a Load Balancer work?",
    "What is context switching in ARM Cortex-M4?",
    # El So2al el Gadeed el Mozdawag:
    "Where is Ain Shams University located, and what do we learn in CSE354?" 
]

async def simulate_user(user_id, scheduler, sem):
    async with sem:
        # Ekhtar so2al 3ashwa2y mn el list
        user_prompt = random.choice(QUESTIONS)
        
        payload = {"user_id": user_id, "prompt": user_prompt, "use_rag": True}
        start = time.time()
        
        response = await scheduler.handle_request(payload)
        
        latency = time.time() - start
        
        # N-extract awel 60 7arf mn el egeba 3ashan nshoof el context elly raga3
        answer_snippet = str(response.get('answer', ''))[:60].replace('\n', ' ')
        
        print(f"[User {user_id} | Port: {response.get('worker_id')}] Asked: '{user_prompt[:15]}...' -> Ans: {answer_snippet} | {latency:.2f}s")

async def run_load_test(scheduler, num_users=1000, max_concurrent=30):
    print(f"--- Starting Realistic Stress Test: {num_users} Users ---")
    
    sem = asyncio.Semaphore(max_concurrent)
    tasks = []
    
    for i in range(num_users):
        tasks.append(simulate_user(i, scheduler, sem))
    
    start_time = time.time()
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    print(f"--- Test Finished! Total Time: {total_time:.2f}s ---")
    print(f"--- System Throughput: {num_users / total_time:.2f} requests/sec ---")