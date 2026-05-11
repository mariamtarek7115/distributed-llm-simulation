from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


@dataclass
class AppConfig:
    worker_urls: list[str]
    worker_health_urls: list[str]
    worker_metrics_urls: list[str]
    model_name: str
    load_balancer_strategy: str
    scenario: str
    num_users: int
    concurrency: int
    failure_rate: float
    recovery_time: int
    node_down_worker_index: int
    node_down_after_seconds: int
    node_recovery_after_seconds: int
    all_nodes_down_after_seconds: int
    all_nodes_recovery_after_seconds: int
    max_workers: int
    queue_size: int
    retry_workers: int
    max_retries: int
    request_timeout: int


def load_env_file(env_path: Path | None = None) -> None:
    path = env_path or ENV_PATH

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


def _load_indexed_env_values(prefix: str) -> list[str]:
    values: list[str] = []
    index = 0

    while True:
        value = os.getenv(f"{prefix}_{index}")

        if value is None:
            break

        cleaned_value = value.strip()
        if cleaned_value:
            values.append(cleaned_value)

        index += 1

    return values


def load_config() -> AppConfig:
    load_env_file()

    worker_urls = _load_indexed_env_values("OLLAMA_WORKER_URL")
    if not worker_urls:
        worker_urls = [
            url.strip()
            for url in os.getenv("OLLAMA_WORKERS", "http://localhost:11434").split(",")
            if url.strip()
        ]

    worker_health_urls = _load_indexed_env_values("OLLAMA_WORKER_HEALTH_URL")
    if not worker_health_urls:
        worker_health_urls = [
            url.strip()
            for url in os.getenv("OLLAMA_HEALTH_URLS", "").split(",")
            if url.strip()
        ]

    worker_metrics_urls = _load_indexed_env_values("WORKER_METRICS_URL")

    if not worker_urls:
        raise ValueError("No workers provided in OLLAMA_WORKERS")

    if worker_health_urls and len(worker_health_urls) != len(worker_urls):
        raise ValueError(
            "OLLAMA_HEALTH_URLS must have the same number of entries as OLLAMA_WORKERS"
        )

    if worker_metrics_urls and len(worker_metrics_urls) != len(worker_urls):
        raise ValueError(
            "WORKER_METRICS_URL_* must have the same number of entries as worker URLs"
        )

    return AppConfig(
        worker_urls=worker_urls,
        worker_health_urls=worker_health_urls,
        worker_metrics_urls=worker_metrics_urls,
        model_name=os.getenv("OLLAMA_MODEL", "tinyllama"),
        load_balancer_strategy=os.getenv("LOAD_BALANCER_STRATEGY", "least_connections").strip().lower(),
        scenario=os.getenv("SCENARIO", "normal").strip().lower(),
        num_users=int(os.getenv("NUM_USERS", "100")),
        concurrency=int(os.getenv("CONCURRENCY", "10")),
        failure_rate=float(os.getenv("FAILURE_RATE", "0.2")),
        recovery_time=int(os.getenv("RECOVERY_TIME", "10")),
        node_down_worker_index=int(os.getenv("NODE_DOWN_WORKER_INDEX", "0")),
        node_down_after_seconds=int(os.getenv("NODE_DOWN_AFTER_SECONDS", "2")),
        node_recovery_after_seconds=int(os.getenv("NODE_RECOVERY_AFTER_SECONDS", os.getenv("RECOVERY_TIME", "10"))),
        all_nodes_down_after_seconds=int(os.getenv("ALL_NODES_DOWN_AFTER_SECONDS", "2")),
        all_nodes_recovery_after_seconds=int(os.getenv("ALL_NODES_RECOVERY_AFTER_SECONDS", "0")),
        max_workers=int(os.getenv("MAX_WORKERS", "4")),
        queue_size=int(os.getenv("QUEUE_SIZE", "200")),
        retry_workers=int(os.getenv("RETRY_WORKERS", "2")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "120")),
    )