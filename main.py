import asyncio
from client.scenario_runner import run_scenario
from common.config import load_config
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler

async def main():
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
    
    print(f"running_scenario={config.scenario}")
    await lb.start_background_tasks()
    await run_scenario(config, scheduler, lb)

if __name__ == "__main__":
    asyncio.run(main())