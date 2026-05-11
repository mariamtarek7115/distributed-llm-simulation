import asyncio
import logging
import random
import time
import httpx


logger = logging.getLogger("load_balancer")
logger.addHandler(logging.NullHandler())
logger.propagate = False


class LoadBalancer:
    def __init__(
        self,
        worker_urls,
        backend="ollama",
        model_name=None,
        worker_health_urls=None,
        worker_metrics_urls=None,
        strategy="least_connections",
    ):
        self.worker_urls = worker_urls.copy()
        self.worker_health_urls = worker_health_urls.copy() if worker_health_urls else []
        self.worker_metrics_urls = worker_metrics_urls.copy() if worker_metrics_urls else []
        self.dead_nodes = set()
        self.simulated_dead_nodes = set()
        self.active_connections = {url: 0 for url in self.worker_urls}

        self.backend = backend
        self.model_name = model_name
        self.strategy = strategy

        # Round-robin pointer used only when least-connections ties occur
        self.next_index = 0

        # Friendly labels for reporting
        self.worker_labels = {
            url: f"GPU-{i}"
            for i, url in enumerate(self.worker_urls)
        }
        self.health_urls = {
            url: self._build_health_url(url, index)
            for index, url in enumerate(self.worker_urls)
        }
        self.metrics_urls = {
            url: self._build_metrics_url(url, index)
            for index, url in enumerate(self.worker_urls)
        }
        self.request_counter = 0
        self.simulated_delay_ms = 0
        self.simulated_jitter_ms = 0
        self.metrics_refresh_interval = 1.0
        self.metrics_cache = {}
        self.background_tasks_started = False

    # ----------------------------
    # HEARTBEAT (FAILURE DETECTION)
    # ----------------------------
    async def heartbeat_loop(self):
        async with httpx.AsyncClient(timeout=2.0) as client:
            while True:
                await asyncio.sleep(5)

                for node in self.worker_urls:
                    if node in self.dead_nodes and node not in self.simulated_dead_nodes:
                        try:
                            response = await client.get(self.health_urls[node])

                            if response.status_code == 200:
                                logger.info(
                                    "event=recovery worker_id=%s active_connections=%s",
                                    self.worker_labels[node],
                                    self._active_connections_snapshot(),
                                )
                                self.dead_nodes.remove(node)
                                self.active_connections[node] = 0

                        except Exception:
                            pass

    async def start_background_tasks(self):
        if self.background_tasks_started:
            return

        self.background_tasks_started = True

        if self.strategy == "load_aware" and self.worker_metrics_urls:
            asyncio.create_task(self._metrics_refresh_loop())

    # ----------------------------
    # MAIN ROUTING LOGIC (LEAST CONNECTIONS + ROUND-ROBIN TIE BREAK)
    # ----------------------------
    async def _select_target(self):
        if self.strategy == "load_aware":
            return self._select_target_by_load()

        return self._select_target_by_least_connections()

    def _select_target_by_least_connections(self):
        available_nodes = {
            url: self.active_connections[url]
            for url in self.worker_urls
            if url not in self.dead_nodes
        }

        if not available_nodes:
            return None

        min_connections = min(available_nodes.values())
        candidate_nodes = [
            url for url in self.worker_urls
            if url in available_nodes and available_nodes[url] == min_connections
        ]

        for offset in range(len(self.worker_urls)):
            index = (self.next_index + offset) % len(self.worker_urls)
            candidate = self.worker_urls[index]
            if candidate in candidate_nodes:
                self.next_index = (index + 1) % len(self.worker_urls)
                return candidate

        return candidate_nodes[0]

    def _select_target_by_load(self):
        alive_workers = [url for url in self.worker_urls if url not in self.dead_nodes]
        if not alive_workers:
            return None

        worker_scores = self._get_cached_worker_scores(alive_workers)
        if not worker_scores:
            return self._select_target_by_least_connections()

        best_score = min(score for _, score in worker_scores)
        candidate_nodes = [url for url, score in worker_scores if score == best_score]

        for offset in range(len(self.worker_urls)):
            index = (self.next_index + offset) % len(self.worker_urls)
            candidate = self.worker_urls[index]
            if candidate in candidate_nodes:
                self.next_index = (index + 1) % len(self.worker_urls)
                return candidate

        return candidate_nodes[0]

    # ----------------------------
    # REQUEST HANDLING
    # ----------------------------
    async def route_request(self, payload):
        request_id = self._next_request_id()
        await self.start_background_tasks()
        target_url = await self._select_target()

        if not target_url:
            logger.error(
                "event=request_failed request_id=%s reason=no_available_workers active_connections=%s dead_nodes=%s",
                request_id,
                self._active_connections_snapshot(),
                self._dead_node_labels(),
            )
            return self._safe_fallback_response()

        self.active_connections[target_url] += 1
        logger.info(
            "event=request_selected request_id=%s user_id=%s worker_id=%s active_connections=%s prompt_preview=%r",
            request_id,
            payload.get("user_id", "unknown"),
            self.worker_labels[target_url],
            self._active_connections_snapshot(),
            self._prompt_preview(payload.get("prompt", "")),
        )

        try:
            start_time = time.time()
            await self._simulate_network_delay()

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    target_url,
                    json={
                        "model": self.model_name,
                        "prompt": payload["prompt"],
                        "stream": False,
                    },
                )

                response.raise_for_status()
                data = response.json()
                latency = time.time() - start_time

                logger.info(
                    "event=request_succeeded request_id=%s worker_id=%s latency_ms=%.2f active_connections=%s",
                    request_id,
                    self.worker_labels[target_url],
                    latency * 1000,
                    self._active_connections_snapshot(),
                )

                return {
                    "request_id": request_id,
                    "worker_id": self.worker_labels[target_url],
                    "answer": data.get("response", ""),
                    "latency": latency,
                    "success": True
                }

        except Exception as e:
            logger.error(
                "event=request_failed request_id=%s worker_id=%s reason=%s active_connections=%s",
                request_id,
                self.worker_labels[target_url],
                repr(e),
                self._active_connections_snapshot(),
            )

            self.dead_nodes.add(target_url)
            self.active_connections[target_url] = 0

            if self.get_alive_workers():
                return await self.route_request(payload)

            return self._safe_fallback_response()
        finally:
            if target_url in self.active_connections:
                self.active_connections[target_url] = max(
                    0,
                    self.active_connections[target_url] - 1
                )

    def _active_connections_snapshot(self):
        return {
            self.worker_labels[url]: self.active_connections[url]
            for url in self.worker_urls
        }

    def _dead_node_labels(self):
        return [self.worker_labels[url] for url in self.worker_urls if url in self.dead_nodes]

    def _next_request_id(self):
        self.request_counter += 1
        return self.request_counter

    def _prompt_preview(self, prompt, max_length=60):
        single_line_prompt = prompt.replace("\n", " ").strip()
        if len(single_line_prompt) <= max_length:
            return single_line_prompt
        return f"{single_line_prompt[:max_length]}..."

    def _build_health_url(self, worker_url, index):
        if self.worker_health_urls:
            return self.worker_health_urls[index]

        health_path = "/api/tags" if self.backend == "ollama" else "/health"
        return f"{worker_url}{health_path}"

    def _build_metrics_url(self, worker_url, index):
        if self.worker_metrics_urls:
            return self.worker_metrics_urls[index]

        return None

    def _get_cached_worker_scores(self, worker_urls):
        scores = []

        for worker_url in worker_urls:
            metrics = self.metrics_cache.get(worker_url)
            if not metrics:
                continue

            scores.append((
                worker_url,
                (
                    metrics["gpu_usage"],
                    metrics["cpu_usage"],
                    self.active_connections[worker_url],
                ),
            ))

        return scores

    async def get_worker_metrics_snapshot(self):
        await self.start_background_tasks()

        snapshots = []
        for worker_url in self.worker_urls:
            if worker_url in self.dead_nodes:
                continue

            metrics = self.metrics_cache.get(worker_url)
            if metrics:
                snapshots.append(metrics)

        return snapshots

    async def _metrics_refresh_loop(self):
        while True:
            await self._refresh_metrics_cache()
            await asyncio.sleep(self.metrics_refresh_interval)

    async def _refresh_metrics_cache(self):
        alive_workers = [url for url in self.worker_urls if url not in self.dead_nodes]
        if not alive_workers:
            return

        async with httpx.AsyncClient(timeout=2.0) as client:
            tasks = [self._fetch_worker_metrics(client, worker_url) for worker_url in alive_workers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for worker_url, result in zip(alive_workers, results):
            if isinstance(result, dict):
                self.metrics_cache[worker_url] = result
            else:
                logger.warning(
                    "event=metrics_unavailable worker_id=%s reason=%s",
                    self.worker_labels[worker_url],
                    repr(result),
                )

    async def _fetch_worker_metrics(self, client, worker_url):
        metrics_url = self.metrics_urls.get(worker_url)
        if not metrics_url:
            raise ValueError("No metrics URL configured")

        response = await client.get(metrics_url)
        response.raise_for_status()

        metrics = response.json()
        cpu_usage = float(metrics.get("cpu", {}).get("usage_percent", 100.0))
        gpu_samples = metrics.get("gpus", [])
        gpu_utilizations = []

        for gpu in gpu_samples:
            utilization = gpu.get("utilization_gpu_percent")
            if utilization is None:
                continue

            gpu_utilizations.append(float(utilization))

        gpu_usage = (
            sum(gpu_utilizations) / len(gpu_utilizations)
            if gpu_utilizations else 100.0
        )

        return {
            "worker_id": self.worker_labels[worker_url],
            "worker_url": worker_url,
            "cpu_usage": cpu_usage,
            "gpu_usage": gpu_usage,
            "gpu_utilizations": gpu_utilizations,
            "active_connections": self.active_connections[worker_url],
            "timestamp": metrics.get("timestamp_iso"),
        }

    def configure_simulation(self, delay_ms=0, jitter_ms=0):
        self.simulated_delay_ms = max(0, delay_ms)
        self.simulated_jitter_ms = max(0, jitter_ms)
        logger.info(
            "event=simulation_updated delay_ms=%s jitter_ms=%s",
            self.simulated_delay_ms,
            self.simulated_jitter_ms,
        )

    def mark_worker_unhealthy(self, worker_url, reason="manual", simulated=True):
        if worker_url not in self.worker_urls:
            raise ValueError(f"Unknown worker URL: {worker_url}")

        self.dead_nodes.add(worker_url)
        if simulated:
            self.simulated_dead_nodes.add(worker_url)
        self.active_connections[worker_url] = 0
        logger.warning(
            "event=worker_marked_unhealthy worker_id=%s reason=%s dead_nodes=%s",
            self.worker_labels[worker_url],
            reason,
            self._dead_node_labels(),
        )

    def recover_worker(self, worker_url):
        if worker_url in self.dead_nodes:
            self.dead_nodes.remove(worker_url)
            self.simulated_dead_nodes.discard(worker_url)
            self.active_connections[worker_url] = 0
            logger.info(
                "event=worker_recovered worker_id=%s active_connections=%s",
                self.worker_labels[worker_url],
                self._active_connections_snapshot(),
            )

    def recover_all_workers(self):
        for worker_url in list(self.dead_nodes):
            self.recover_worker(worker_url)

    def mark_all_workers_unhealthy(self, reason="manual", simulated=True):
        for worker_url in self.worker_urls:
            self.mark_worker_unhealthy(worker_url, reason=reason, simulated=simulated)

    def get_alive_workers(self):
        return [url for url in self.worker_urls if url not in self.dead_nodes]

    def _safe_fallback_response(self):
        return {
            "request_id": self.request_counter,
            "worker_id": "SYSTEM_SHUTDOWN",
            "answer": "System is temporarily shut down. Try again later.",
            "latency": 0,
            "success": False,
            "retryable": False,
        }

    async def _simulate_network_delay(self):
        if self.simulated_delay_ms <= 0 and self.simulated_jitter_ms <= 0:
            return

        jitter = random.randint(0, self.simulated_jitter_ms) if self.simulated_jitter_ms > 0 else 0
        total_delay_ms = self.simulated_delay_ms + jitter
        await asyncio.sleep(total_delay_ms / 1000)