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

def _format_response_line(result, user_id):
    if result.get("fallback", False):
        status = "OVERLOADED"
    elif result.get("success", False):
        status = "SUCCESS"
    else:
        status = "FAIL"
    answer = str(result.get("answer", "")).replace("\n", " ").strip()
    return (
        f"[RESPONSE] user={user_id} | "
        f"request_id={result.get('request_id', 'unknown')} | "
        f"status={status} | "
        f"worker_id={result.get('worker_id', 'unknown')} | "
        f"latency={result.get('latency', 0.0):.2f}s | "
        f"response={answer}"
    )


def _print_metrics_summary(results, total_time, worker_metrics, interrupted=False):
    latencies = [r.get("latency", 0.0) for r in results]

    completed = len(results)
    success_count = sum(1 for r in results if r.get("success", False) and not r.get("fallback", False))
    overloaded_count = sum(1 for r in results if r.get("fallback", False))
    failure_count = sum(1 for r in results if not r.get("success", False))

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p95_latency = _percentile(latencies, 95)
    throughput = completed / total_time if total_time > 0 else 0.0
    metrics_summary = _build_metrics_summary(worker_metrics)

    title = "RUN METRICS" if not interrupted else "TERMINATED RUN METRICS"
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)
    print(f"  total_requests       : {completed}")
    print(f"  success              : {success_count}")
    print(f"  overloaded (fallback): {overloaded_count}")
    print(f"  failed               : {failure_count}")
    print(f"  total_time           : {total_time:.2f}s")
    print(f"  throughput           : {throughput:.2f} req/s")
    print(f"  average_latency      : {avg_latency:.2f}s")
    print(f"  p95_latency          : {p95_latency:.2f}s")

    if metrics_summary:
        print(f"  average_cpu_usage    : {metrics_summary['avg_cpu']:.2f}%")
        print(f"  average_gpu_usage    : {metrics_summary['avg_gpu']:.2f}%")
        print(f"  {'-' * 56}")
        print(f"  per-worker metrics:")
        for worker in metrics_summary["workers"]:
            print(
                f"    {worker['worker_id']:<8} | "
                f"cpu={worker['cpu_usage']:6.2f}% | "
                f"gpu={worker['gpu_usage']:6.2f}% | "
                f"active_conn={worker['active_connections']:<3} | "
                f"timestamp={worker['timestamp']}"
            )
    else:
        print(f"  average_cpu_usage    : unavailable")
        print(f"  average_gpu_usage    : unavailable")
    print(f"{bar}\n")

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

        is_fallback = response.get("fallback", False)
        # For overloaded/fallback responses, use the scheduler-measured latency
        # (time from scheduler entry to response return). Otherwise use the
        # client-side end-to-end latency.
        if is_fallback:
            latency = response.get("latency", time.time() - start)
        else:
            latency = time.time() - start

        result = {
            "request_id": response.get("request_id"),
            "worker_id": response.get("worker_id"),
            "success": response.get("success", True),
            "fallback": is_fallback,
            "latency": latency,
            "answer": response.get("answer", ""),
        }

        # Only print full response details for processed requests.
        # Overloaded/rejected requests already printed [OVERLOADED] in the scheduler.
        if not is_fallback:
            print(_format_response_line(result, user_id))
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


async def run_load_test(scheduler, load_balancer, num_users=1000, max_concurrent=30, arrival_interval=0.01):
    sem = asyncio.Semaphore(max_concurrent)
    results = []
    tasks = []
    start_time = time.time()
    interrupted = False

    async def _spawn_users():
        # Stagger task creation so [QUEUE], [OVERLOADED], and [RESPONSE]
        # interleave naturally instead of bursting all at once.
        for i in range(num_users):
            tasks.append(asyncio.create_task(simulate_user(i, scheduler, sem)))
            if arrival_interval > 0:
                await asyncio.sleep(arrival_interval)

    spawner = asyncio.create_task(_spawn_users())

    try:
        await spawner
        for task in asyncio.as_completed(tasks):
            results.append(await task)
    except (asyncio.CancelledError, KeyboardInterrupt):
        interrupted = True
        spawner.cancel()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(spawner, *tasks, return_exceptions=True)
    finally:
        total_time = time.time() - start_time
        # Flush any pending [QUEUE] batch so all admissions are visible
        # before the metrics block.
        flush = getattr(scheduler, "_flush_queue_log", None)
        if callable(flush):
            flush(force=True)
        worker_metrics = await load_balancer.get_worker_metrics_snapshot()
        summary = _print_metrics_summary(results, total_time, worker_metrics, interrupted=interrupted)

    summary["total_time"] = total_time
    summary["completed_count"] = len(results)
    summary["failure_count"] = sum(1 for result in results if not result.get("success", False))
    summary["fallback_count"] = sum(1 for result in results if result.get("fallback", False))
    return summary