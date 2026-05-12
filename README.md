# Distributed LLM Simulation

A distributed system that handles 1000+ concurrent LLM inference requests across multiple GPU worker nodes, with RAG enrichment, load balancing, fault tolerance, and graceful overload handling.

Implements the CSE354 Distributed Computing course project: **"Efficient Load Balancing and GPU Cluster Task Distribution for Handling 1000+ Concurrent LLM Requests"**.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration (`.env`)](#configuration-env)
- [How To Run](#how-to-run)
- [Load Balancing Strategies](#load-balancing-strategies)
- [Test Scenarios](#test-scenarios)
- [Terminal Log Legend](#terminal-log-legend)
- [Metrics Block](#metrics-block)
- [Load-Test Sweep](#load-test-sweep)
- [API Gateway Mode](#api-gateway-mode)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
+-----------------+
|  Client Layer   |   simulates N concurrent users
+--------+--------+
         |
         v
+-----------------+
|    Scheduler    |   main queue (capacity QUEUE_SIZE)
|     (Master)    |   retry queue (exponential backoff)
+--------+--------+
         |
         v
+-----------------+         +-----------------+
| Load Balancer   |-------->|   RAG Module    |
| round_robin /   |         | (FAISS + ST)    |
| least_conn /    |         +-----------------+
| load_aware      |
+--------+--------+
         |
         v
+--------+--------+--------+--------+
| GPU-0 | GPU-1 | GPU-2 | GPU-3 |    Worker nodes (Ollama on Thunder Compute)
+-------+-------+-------+-------+
```

**Layers:**
- **Client** — `client/load_generator.py` simulates users with staggered arrivals.
- **Scheduler / Master** — `master/scheduler.py` owns the request queue, retry queue, dispatcher pool, and overload handling.
- **Load Balancer** — `load_balancer/lb.py` selects a worker via round_robin / least_connections / load_aware; tracks dead nodes; runs heartbeat and metrics-polling background loops.
- **RAG Module** — `rag/retriever.py` uses `sentence-transformers` + FAISS for context retrieval.
- **Workers** — Ollama instances exposing `/api/generate` (4 Thunder Compute endpoints by default).

---

## Project Layout

```
api_server.py             FastAPI gateway (alternative entrypoint)
main.py                   Scenario test entrypoint
sweep_load_test.py        Automated user-count sweep (writes CSV)
.env                      All runtime configuration
client/
  load_generator.py       Simulated users + metrics block
  scenario_runner.py      Scenario orchestration loops
common/
  config.py               .env parser
load_balancer/
  lb.py                   Worker selection, heartbeat, metrics polling
master/
  scheduler.py            Queue, dispatcher, retry, overload fallback
rag/
  retriever.py            FAISS-backed context retrieval
workers/
  gpu_worker.py           Reference worker (FastAPI; Ollama is used in practice)
llm/
  inference.py            LLM wrapper
```

---

## Prerequisites

- Python 3.11+
- Virtual environment at `.venv`
- Worker generation endpoints reachable
- Health endpoints reachable
- Metrics endpoints reachable if you use `load_aware`

---

## Installation

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Configuration (`.env`)

### Worker endpoints (one block per worker)

```dotenv
OLLAMA_WORKER_URL_0=https://<id>-11434.thundercompute.net/api/generate
OLLAMA_WORKER_HEALTH_URL_0=https://<id>-8080.thundercompute.net/health
WORKER_METRICS_URL_0=http://127.0.0.1:9090/metrics
```

### Model and load balancing

| Variable | Values | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | e.g. `tinyllama` | Model name sent to `/api/generate` |
| `LOAD_BALANCER_STRATEGY` | `round_robin` / `least_connections` / `load_aware` | Worker selection strategy |

### Scenario

| Variable | Values | Purpose |
|---|---|---|
| `SCENARIO` | `normal` / `random_failures` / `node_down_recovery` / `all_nodes_down` | Which test scenario to run |

### Load generation

| Variable | Default | Purpose |
|---|---|---|
| `NUM_USERS` | 100 | Total simulated requests |
| `CONCURRENCY` | 10 | Maximum concurrent in-flight users (client-side throttle) |

### Failure / recovery

| Variable | Default | Purpose |
|---|---|---|
| `FAILURE_RATE` | 0.2 | Probability of killing a worker every 2s in `random_failures` |
| `RECOVERY_TIME` | 10 | Seconds before a randomly killed worker is restored |
| `NODE_DOWN_WORKER_INDEX` | 0 | Which worker to kill in `node_down_recovery` |
| `NODE_DOWN_AFTER_SECONDS` | 2 | When to kill it |
| `NODE_RECOVERY_AFTER_SECONDS` | 10 | When to recover it (use 0 to keep down) |
| `ALL_NODES_DOWN_AFTER_SECONDS` | 2 | When to trigger total outage |
| `ALL_NODES_RECOVERY_AFTER_SECONDS` | 0 | When to recover (0 = stay down) |

### Scheduler / retry

| Variable | Default | Purpose |
|---|---|---|
| `MAX_WORKERS` | 4 | Main dispatcher tasks |
| `QUEUE_SIZE` | 200 | Main queue capacity (overflow → instant overload fallback) |
| `RETRY_WORKERS` | 2 | Retry-dispatcher tasks |
| `MAX_RETRIES` | 3 | Retry attempts per failed request |
| `REQUEST_TIMEOUT` | 120 | Per-call timeout (seconds) |

---

## How To Run

### Single scenario (uses `.env`)

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

### Sweep (multiple user counts in one go)

```powershell
python sweep_load_test.py
python sweep_load_test.py --users 100,250,500,1000 --out sweep.csv
```

See [Load-Test Sweep](#load-test-sweep) below.

---

## Load Balancing Strategies

Set `LOAD_BALANCER_STRATEGY` in `.env`:

| Strategy | Behavior | When to use |
|---|---|---|
| `round_robin` | Rotates through alive workers in order. Skips dead nodes. | Even distribution baseline. Good when workers are homogeneous. |
| `least_connections` | Picks the alive worker with the fewest active in-flight requests. Ties broken by round-robin. | Workers vary in speed; smooths uneven request durations. |
| `load_aware` | Uses cached metrics: lowest GPU% → lowest CPU% → fewest active connections. | Most realistic; reflects actual GPU pressure. Requires reachable metrics endpoints. |

If `load_aware` cannot fetch metrics, it falls back to `least_connections` automatically.

---

## Test Scenarios

### 1. `normal` — baseline

Recommended:
```dotenv
SCENARIO=normal
NUM_USERS=100
CONCURRENCY=20
```
Demonstrates: end-to-end throughput, per-worker distribution, RAG enrichment.

### 2. `random_failures` — chaos engineering

Recommended:
```dotenv
SCENARIO=random_failures
FAILURE_RATE=0.3
RECOVERY_TIME=10
NUM_USERS=200
CONCURRENCY=30
```
Demonstrates: random worker kills + auto-recovery + retry-queue requeue + load balancer continuing to operate.

### 3. `node_down_recovery` — controlled fault injection

Recommended:
```dotenv
SCENARIO=node_down_recovery
NODE_DOWN_WORKER_INDEX=0
NODE_DOWN_AFTER_SECONDS=10
NODE_RECOVERY_AFTER_SECONDS=20
NUM_USERS=200
CONCURRENCY=30
```
Demonstrates: deterministic single-node outage, traffic re-routing, recovery.

> Note: in-flight requests already at the killed worker may still complete (network can't be recalled); subsequent requests are routed elsewhere. This is correct fault-tolerance behavior.

### 4. `all_nodes_down` — total outage

Recommended:
```dotenv
SCENARIO=all_nodes_down
ALL_NODES_DOWN_AFTER_SECONDS=10
ALL_NODES_RECOVERY_AFTER_SECONDS=20
NUM_USERS=100
CONCURRENCY=20
```
Demonstrates: graceful degradation — every request during outage gets `worker_id=SYSTEM_SHUTDOWN` and the system recovers when workers are back.

---

## Terminal Log Legend

| Tag | Meaning |
|---|---|
| `[QUEUE] user=X` / `[QUEUE] users=A-B (N admitted)` | Request(s) accepted into the main queue. Batched to reduce log flooding. |
| `[OVERLOADED] user=X rejected` | Main queue is full. Request returned an instant safe-fallback response. Counted as `overloaded`. |
| `[RESPONSE] user=X \| status=SUCCESS \| worker_id=GPU-N \| latency=...` | LLM responded successfully. |
| `[RESPONSE] user=X \| status=FAIL \| worker_id=TIMEOUT` | All retries exhausted or system-shutdown response. Counted as `failed`. |
| `[RETRY] user=X \| attempt=k/MAX \| reason=... \| backoff=Ns` | Request hit an error and was pushed to the retry queue. Backoff is `2 * attempt` seconds. |
| `[FAILED] user=X \| retries_exhausted (MAX)` | Final failure after exhausting retries. |
| `!!! WORKER DOWN ... GPU-N IS DEAD !!!` (banner) | A worker was marked unhealthy. New requests will not be routed to it. |
| `+++ WORKER RECOVERED ... GPU-N IS ALIVE AGAIN +++` (banner) | A worker was restored and is selectable again. |

Logs are interleaved in real-time — `[QUEUE]` admissions are batched (10 at a time or every 0.5s) so the terminal isn't flooded at startup.

---

## Metrics Block

Printed at end of run (or on Ctrl+C, labelled `TERMINATED RUN METRICS`):

```
============================================================
  RUN METRICS
============================================================
  total_requests       : 1000
  success              : 712
  overloaded (fallback): 261
  failed               : 27
  total_time           : 84.10s
  throughput           : 11.89 req/s
  average_latency      : 6.41s
  p95_latency          : 18.22s
  average_cpu_usage    : 24.50%
  average_gpu_usage    : 71.32%
  --------------------------------------------------------
  per-worker metrics:
    GPU-0    | cpu= 22.10% | gpu= 68.40% | active_conn=0   | timestamp=...
    ...
============================================================
```

| Metric | Meaning |
|---|---|
| `success` | Successful LLM responses (incl. retries that eventually succeeded). |
| `overloaded (fallback)` | Requests rejected because the main queue was full. |
| `failed` | Requests that exhausted all retries or hit a SYSTEM_SHUTDOWN response. |
| `throughput` | Completed requests per second. |
| `average_latency` / `p95_latency` | Client-measured (queue wait + processing). For overloaded requests, latency is measured from scheduler entry to fallback return. |
| `average_cpu_usage` / `average_gpu_usage` | Mean across alive workers, from cached metrics snapshots. |

---

## Load-Test Sweep

`sweep_load_test.py` runs the system at several user counts back-to-back and writes a CSV summary you can paste into a spreadsheet for the report.

```powershell
# defaults: 100, 250, 500, 1000 users, concurrency = users
python sweep_load_test.py

# custom user steps
python sweep_load_test.py --users 50,100,500,1000 --out my_sweep.csv

# fix concurrency across all steps
python sweep_load_test.py --users 100,500,1000 --concurrency 100
```

Output CSV columns:
`users, concurrency, completed, success, overloaded, failed, total_time_s, throughput_req_s, avg_latency_s, p95_latency_s, avg_cpu_pct, avg_gpu_pct, strategy, scenario`

The script reuses `.env` for everything except `NUM_USERS` and `CONCURRENCY`, so set `SCENARIO`, `LOAD_BALANCER_STRATEGY`, etc. in `.env` first.

---

## API Gateway Mode

Instead of the scenario runner, you can expose a FastAPI endpoint:

```powershell
python api_server.py
```

POST a single request:

```http
POST http://localhost:8000/chat
{
  "user_id": 1,
  "prompt": "Explain what a REST API is.",
  "use_rag": true
}
```

---

## Troubleshooting

- **Run exits immediately** — verify worker URLs in `.env` are reachable.
- **`load_aware` not using metrics** — verify each `WORKER_METRICS_URL_n` returns the expected JSON.
- **All requests hit `[OVERLOADED]`** — `CONCURRENCY > MAX_WORKERS + QUEUE_SIZE`. Either increase `QUEUE_SIZE` or accept the overload as the intended demonstration.
- **No `[RETRY]` lines visible** — set `REQUEST_TIMEOUT=2` and run `random_failures` to force visible retries.
- **`status=FAIL` during `all_nodes_down`** — expected; the system returns a `SYSTEM_SHUTDOWN` response while no workers are alive.
- **Simulated worker outages don't auto-revive on heartbeat** — by design. `simulated=True` outages stay down until the scenario explicitly recovers them, even if the underlying health endpoint says `200 OK`.

---

## Capacity formula

```
acceptance_window = MAX_WORKERS + QUEUE_SIZE
```

A simultaneous burst larger than this produces `[OVERLOADED]` rejections. Smaller bursts are absorbed by the queue and dispatched as workers free up.
