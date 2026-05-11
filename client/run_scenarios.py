import asyncio
import os
from dotenv import load_dotenv
from client.scenarios import ScenarioManager

load_dotenv()

async def run_test(scheduler):

    num_users = int(os.getenv("NUM_USERS", 100))
    concurrency = int(os.getenv("CONCURRENCY", 10))

    sem = asyncio.Semaphore(concurrency)

    async def worker(i):
        async with sem:
            payload = {
                "user_id": i,
                "prompt": "Explain load balancing in simple terms",
                "use_rag": False
            }

            result = await scheduler.handle_request(payload)
            print(i, result["worker_id"], result["latency"])

    tasks = [worker(i) for i in range(num_users)]
    await asyncio.gather(*tasks)