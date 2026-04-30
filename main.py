import asyncio
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler
from client.load_generator import run_load_test

async def main():
    worker_urls = [
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003",
        "http://localhost:8004"
    ]
    
    lb = LoadBalancer(worker_urls)
    scheduler = Scheduler(lb)
    
    print("\n=== CSE354: Distributed LLM System ===")
    print("1. Test Fault Tolerance (20 users)")
    print("2. Stress Test (1000 users)")
    
    choice = input("Enter your choice (1 or 2): ")
    
    if choice == '1':
        # Hanghrab 20 user bas, w n-limit el concurrency le 5 3ashan el test ytewal shwaya w n-l7a2 n-wa2a3 server
        await run_load_test(scheduler, num_users=20, max_concurrent=5)
    elif choice == '2':
        # El stress test el kbeer 
        await run_load_test(scheduler, num_users=1000, max_concurrent=30)
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())