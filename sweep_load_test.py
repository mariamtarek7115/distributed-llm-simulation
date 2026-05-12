"""
Load-test sweep: runs the system at increasing user counts and writes a CSV
summary so you can chart latency / throughput vs concurrency for the report.

Usage:
    python sweep_load_test.py
    python sweep_load_test.py --users 100,250,500,1000 --scenario normal --out sweep.csv

It uses the configuration from .env (workers, queue size, retries, etc.) but
overrides NUM_USERS and CONCURRENCY for each step.
"""

import argparse
import asyncio
import csv
import os
import sys
import time
from pathlib import Path

from client.load_generator import run_load_test
from common.config import load_config
from load_balancer.lb import LoadBalancer
from master.scheduler import Scheduler


DEFAULT_USER_STEPS = [100, 250, 500, 1000]
DEFAULT_OUTPUT_FILE = "sweep_results.csv"


def _build_components(config):
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
    return lb, scheduler


async def _run_single_step(config, num_users, concurrency):
    print(f"\n############################################################")
    print(f"#  SWEEP STEP  users={num_users}  concurrency={concurrency}")
    print(f"############################################################\n")

    lb, scheduler = _build_components(config)
    await lb.start_background_tasks()

    summary = await run_load_test(
        scheduler,
        lb,
        num_users=num_users,
        max_concurrent=concurrency,
    )
    return summary


def _write_csv(rows, output_path):
    fieldnames = [
        "users",
        "concurrency",
        "completed",
        "success",
        "overloaded",
        "failed",
        "total_time_s",
        "throughput_req_s",
        "avg_latency_s",
        "p95_latency_s",
        "avg_cpu_pct",
        "avg_gpu_pct",
        "strategy",
        "scenario",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _summarize_workers(worker_metrics):
    if not worker_metrics:
        return 0.0, 0.0
    avg_cpu = sum(w["cpu_usage"] for w in worker_metrics) / len(worker_metrics)
    avg_gpu = sum(w["gpu_usage"] for w in worker_metrics) / len(worker_metrics)
    return avg_cpu, avg_gpu


def _print_final_table(rows):
    print("\n############################################################")
    print("#  SWEEP RESULTS")
    print("############################################################")
    header = (
        f"{'users':>6} | {'thr(r/s)':>9} | {'avg_lat':>8} | "
        f"{'p95_lat':>8} | {'success':>7} | {'overld':>7} | {'failed':>6}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['users']:>6} | {r['throughput_req_s']:>9.2f} | "
            f"{r['avg_latency_s']:>8.2f} | {r['p95_latency_s']:>8.2f} | "
            f"{r['success']:>7} | {r['overloaded']:>7} | {r['failed']:>6}"
        )
    print()


async def _run_sweep(user_steps, concurrency_override, output_path):
    config = load_config()
    rows = []

    for num_users in user_steps:
        concurrency = concurrency_override if concurrency_override else num_users
        summary = await _run_single_step(config, num_users, concurrency)
        avg_cpu, avg_gpu = _summarize_workers(summary.get("worker_metrics", []))

        rows.append({
            "users": num_users,
            "concurrency": concurrency,
            "completed": summary["completed_count"],
            "success": summary["completed_count"] - summary["failure_count"] - summary["fallback_count"],
            "overloaded": summary["fallback_count"],
            "failed": summary["failure_count"],
            "total_time_s": round(summary["total_time"], 2),
            "throughput_req_s": round(summary["throughput"], 2),
            "avg_latency_s": round(summary["avg_latency"], 2),
            "p95_latency_s": round(summary["p95_latency"], 2),
            "avg_cpu_pct": round(avg_cpu, 2),
            "avg_gpu_pct": round(avg_gpu, 2),
            "strategy": config.load_balancer_strategy,
            "scenario": config.scenario,
        })

        _write_csv(rows, output_path)
        print(f"\n[SWEEP] wrote {len(rows)} row(s) to {output_path}")

    _print_final_table(rows)


def _parse_args():
    parser = argparse.ArgumentParser(description="Distributed LLM load-test sweep")
    parser.add_argument(
        "--users",
        type=str,
        default=",".join(str(u) for u in DEFAULT_USER_STEPS),
        help="Comma-separated user counts to test (default: 100,250,500,1000)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=0,
        help="Override CONCURRENCY for each step (default: equal to users)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help="Output CSV file path",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    user_steps = [int(u.strip()) for u in args.users.split(",") if u.strip()]
    output_path = Path(args.out).resolve()
    asyncio.run(_run_sweep(user_steps, args.concurrency, output_path))


if __name__ == "__main__":
    main()
