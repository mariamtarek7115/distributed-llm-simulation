import asyncio
import time

async def simulate_user(user_id, scheduler, sem):
    # El Semaphore by-limit 3adad el users elly be-ydkholo f nafs el lahza
    async with sem:
        payload = {"user_id": user_id, "prompt": f"User {user_id} asking about CSE354", "use_rag": True}
        start = time.time()
        
        response = await scheduler.handle_request(payload)
        
        latency = time.time() - start
        print(f"[User {user_id}] -> Worker {response.get('worker_id')} | Latency: {latency:.2f}s")

async def run_load_test(scheduler, num_users=1000, max_concurrent=30):
    print(f"--- Starting Stress Test: {num_users} Users ({max_concurrent} at a time) ---")
    
    # Allow only 'max_concurrent' active connections at once 3ashan el PC maywalla3sh
    sem = asyncio.Semaphore(max_concurrent)
    
    tasks = []
    for i in range(num_users):
        tasks.append(simulate_user(i, scheduler, sem))
    
    start_time = time.time()
    
    # Run all tasks
    await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    print(f"--- Test Finished! Total Time: {total_time:.2f}s ---")
    print(f"--- System Throughput: {num_users / total_time:.2f} requests/sec ---")