# Distributed LLM Simulation

This project simulates a distributed LLM inference system with:

- multiple worker endpoints
- a scheduler and retry queue
- load balancing strategies
- scenario-based testing for failures, rerouting, recovery, and total outage

The main test entrypoint is `main.py`. It reads settings from `.env`, builds the load balancer and scheduler, then runs the selected scenario.

## Prerequisites

- Python virtual environment created at `.venv`
- dependencies installed from `requirements.txt`
- valid worker generation endpoints in `.env`
- valid health endpoints in `.env`
- valid metrics endpoints in `.env` if `LOAD_BALANCER_STRATEGY=load_aware`

## Installation

From the project root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Main Files

- `main.py`: runs scenario-based testing directly from `.env`
- `api_server.py`: runs the FastAPI gateway with `/chat`
- `.env`: stores worker endpoints, strategy, scenario, and test settings
- `client/scenario_runner.py`: selects and applies the configured scenario
- `client/load_generator.py`: runs the simulated users and prints metrics

## How To Run A Test

For scenario testing, run:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

The program will read `.env` and print:

- average latency
- p95 latency
- throughput
- average CPU usage
- average GPU utilization
- worker distribution
- per-worker resource snapshot

## .env Settings Used During Tests

### Worker Endpoints

Each worker has three settings:

- `OLLAMA_WORKER_URL_n`: generation endpoint
- `OLLAMA_WORKER_HEALTH_URL_n`: health check endpoint
- `WORKER_METRICS_URL_n`: metrics endpoint used by `load_aware`

Example:

```dotenv
OLLAMA_WORKER_URL_0=https://worker-id-11434.thundercompute.net/api/generate
OLLAMA_WORKER_HEALTH_URL_0=https://worker-id-8080.thundercompute.net/health
WORKER_METRICS_URL_0=http://127.0.0.1:9090/metrics
```

### Load Balancer Strategy

Available values:

- `LOAD_BALANCER_STRATEGY=least_connections`
- `LOAD_BALANCER_STRATEGY=load_aware`

Behavior:

- `least_connections`: routes to the worker with the fewest assigned active requests
- `load_aware`: routes using cached metrics, preferring lower GPU usage, then lower CPU usage, then lower active connections

### Scenario Selection

Available values for `SCENARIO`:

- `normal`
- `random_failures`
- `node_down_recovery`
- `all_nodes_down`

## Running Each Scenario

### 1. Normal

Purpose: baseline run without artificial delay or failures.

Recommended `.env` values:

```dotenv
SCENARIO=normal
NUM_USERS=100
CONCURRENCY=10
```

Run:

```powershell
python main.py
```

### 2. Random Failures

Purpose: simulate worker failures while keeping at least one worker alive so failed tasks are redirected to other healthy workers.

Recommended `.env` values:

```dotenv
SCENARIO=random_failures
FAILURE_RATE=0.2
RECOVERY_TIME=10
NUM_USERS=100
CONCURRENCY=10
```

Run:

```powershell
python main.py
```

Note: this scenario is designed to test failover. It is most useful when multiple workers are configured.

### 3. One Node Down, Then Recovery

Purpose: take one chosen worker down, stop assigning new tasks to it, then allow it to receive tasks again after the configured recovery delay.

Recommended `.env` values:

```dotenv
SCENARIO=node_down_recovery
NODE_DOWN_WORKER_INDEX=0
NODE_DOWN_AFTER_SECONDS=2
NODE_RECOVERY_AFTER_SECONDS=10
NUM_USERS=100
CONCURRENCY=10
```

Run:

```powershell
python main.py
```

### 4. All Nodes Down

Purpose: simulate a total outage. Once all workers are marked unhealthy, the system returns a safe fallback response telling the caller to try again later.

Recommended `.env` values:

```dotenv
SCENARIO=all_nodes_down
ALL_NODES_DOWN_AFTER_SECONDS=2
ALL_NODES_RECOVERY_AFTER_SECONDS=0
NUM_USERS=100
CONCURRENCY=10
```

Run:

```powershell
python main.py
```

If `ALL_NODES_RECOVERY_AFTER_SECONDS=0`, the workers stay down for the rest of the run.

## Testing High Load

To simulate heavier load, keep the scenario you want and increase:

```dotenv
NUM_USERS=1000
CONCURRENCY=100
```

Then run:

```powershell
python main.py
```

Start with smaller values first to verify the endpoints are reachable before running large tests.

## Running The API Gateway Instead

If you want to test through the FastAPI gateway rather than directly through `main.py`, run:

```powershell
python api_server.py
```

Then send requests to:

```text
POST http://localhost:8000/chat
```

Example request body:

```json
{
	"user_id": 1,
	"prompt": "Explain what a REST API is in two sentences.",
	"use_rag": true
}
```

## Troubleshooting

- If `python main.py` exits immediately, verify the worker URLs in `.env` are reachable.
- If `load_aware` does not seem to use metrics, verify each `WORKER_METRICS_URL_n` is reachable from the machine running this code.
- If health checks fail, verify each `OLLAMA_WORKER_HEALTH_URL_n` returns `200 OK`.
- If generation fails, verify each `OLLAMA_WORKER_URL_n` accepts `POST` requests with model, prompt, and stream fields.
- Simulated scenario failures are intentionally independent from heartbeat success so reliability behavior can be tested even when health endpoints still return `200 OK`.

## Quick Example Configs

### Small Sanity Test

```dotenv
SCENARIO=normal
NUM_USERS=5
CONCURRENCY=2
LOAD_BALANCER_STRATEGY=least_connections
```

### Load-Aware Test

```dotenv
SCENARIO=normal
NUM_USERS=100
CONCURRENCY=20
LOAD_BALANCER_STRATEGY=load_aware
```

### Stress Test

```dotenv
SCENARIO=normal
NUM_USERS=1000
CONCURRENCY=100
LOAD_BALANCER_STRATEGY=load_aware
```
