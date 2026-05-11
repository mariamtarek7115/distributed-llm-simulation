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

def _format_response_line(result):
    status = "SUCCESS" if result.get("success", False) else "FAIL"
    answer = str(result.get("answer", "")).replace("\n", " ").strip()
    return (
        f"request_id={result.get('request_id', 'unknown')} | "
        f"status={status} | "
        f"worker_id={result.get('worker_id', 'unknown')} | "
        f"latency={result.get('latency', 0.0):.2f}s | "
        f"response={answer}"
    )


def _print_metrics_summary(results, total_time, worker_metrics, interrupted=False):
    latencies = []

    for result in results:
        latencies.append(result.get("latency", 0.0))

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p95_latency = _percentile(latencies, 95)
    throughput = len(results) / total_time if total_time > 0 else 0.0
    metrics_summary = _build_metrics_summary(worker_metrics)

    title = "RUN METRICS" if not interrupted else "TERMINATED RUN METRICS"
    print(f"\n=== {title} ===")
    print(f"average_latency={avg_latency:.2f}s")
    print(f"p95_latency={p95_latency:.2f}s")
    print(f"throughput={throughput:.2f} req/s")

    if metrics_summary:
        print(f"average_cpu_usage={metrics_summary['avg_cpu']:.2f}%")
        print(f"average_gpu_utilization={metrics_summary['avg_gpu']:.2f}%")
        print("worker_metrics:")
        for worker in metrics_summary["workers"]:
            print(
                f"  {worker['worker_id']} | "
                f"cpu={worker['cpu_usage']:.2f}% | "
                f"gpu={worker['gpu_usage']:.2f}% | "
                f"active_connections={worker['active_connections']} | "
                f"timestamp={worker['timestamp']}"
            )
    else:
        print("average_cpu_usage=unavailable")
        print("average_gpu_utilization=unavailable")

    return {
        "avg_latency": avg_latency,
        "p95_latency": p95_latency,
        "throughput": throughput,
        "worker_metrics": worker_metrics,
    }


async def simulate_user(user_id, scheduler, sem):
    async with sem:
        # Ekhtar so2al 3ashwa2y mn el list
        user_prompt = random.choice(QUESTIONS)
        
        payload = {"user_id": user_id, "prompt": user_prompt, "use_rag": True}
        start = time.time()
        
        response = await scheduler.handle_request(payload)
        
        latency = time.time() - start
        
        result = {
            "request_id": response.get("request_id"),
            "worker_id": response.get("worker_id"),
            "success": response.get("success", True),
            "latency": latency,
            "answer": response.get("answer", ""),
        }

        print(_format_response_line(result))
        return result

def _percentile(values, percentile):
    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, int(round((percentile / 100) * (len(sorted_values) - 1)))))
    return sorted_values[index]


def _build_metrics_summary(worker_metrics):
    if not worker_metrics:
        return None

    avg_cpu = sum(item["cpu_usage"] for item in worker_metrics) / len(worker_metrics)
    avg_gpu = sum(item["gpu_usage"] for item in worker_metrics) / len(worker_metrics)

    return {
        "avg_cpu": avg_cpu,
        "avg_gpu": avg_gpu,
        "workers": worker_metrics,
    }


async def run_load_test(scheduler, load_balancer, num_users=1000, max_concurrent=30):
    sem = asyncio.Semaphore(max_concurrent)
    tasks = [asyncio.create_task(simulate_user(i, scheduler, sem)) for i in range(num_users)]
    results = []
    start_time = time.time()
    interrupted = False

    try:
        for task in asyncio.as_completed(tasks):
            results.append(await task)
    except (asyncio.CancelledError, KeyboardInterrupt):
        interrupted = True
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        total_time = time.time() - start_time
        worker_metrics = await load_balancer.get_worker_metrics_snapshot()
        summary = _print_metrics_summary(results, total_time, worker_metrics, interrupted=interrupted)

    summary["total_time"] = total_time
    return summary