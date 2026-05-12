import asyncio
from common.config import load_config
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler

async def main():
    cfg = load_config()
    lb = LoadBalancer(
        cfg.worker_urls, 
        backend='ollama', 
        model_name=cfg.model_name, 
        worker_health_urls=cfg.worker_health_urls, 
        worker_metrics_urls=cfg.worker_metrics_urls, 
        strategy=cfg.load_balancer_strategy
    )
    scheduler = Scheduler(
        lb, 
        max_workers=cfg.max_workers, 
        queue_size=1, 
        retry_workers=cfg.retry_workers, 
        max_retries=cfg.max_retries, 
        request_timeout=cfg.request_timeout
    )
    
    loop = asyncio.get_running_loop()
    first_future = loop.create_future()
    # Manually fill the queue (size=1)
    scheduler.queue.put_nowait(({'user_id': 1, 'prompt': 'x', 'retry_count': 0}, first_future))
    
    # This should trigger the "System is overloaded" response because queue is full
    result = await scheduler.handle_request({'user_id': 2, 'prompt': 'y'})
    print(result)

if __name__ == '__main__':
    asyncio.run(main())
