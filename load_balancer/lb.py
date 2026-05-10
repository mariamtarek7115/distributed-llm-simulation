import asyncio
import logging
import time
import httpx


logger = logging.getLogger("load_balancer")


class LoadBalancer:
    def __init__(self, worker_urls, backend="ollama", model_name=None):
        self.worker_urls = worker_urls.copy()
        self.dead_nodes = set()
        self.active_connections = {url: 0 for url in self.worker_urls}

        self.backend = backend
        self.model_name = model_name

        # Round-robin pointer used only when least-connections ties occur
        self.next_index = 0

        # Friendly labels for reporting
        self.worker_labels = {
            url: f"GPU-{i}"
            for i, url in enumerate(self.worker_urls)
        }
        self.request_counter = 0

        if not logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )

    # ----------------------------
    # HEARTBEAT (FAILURE DETECTION)
    # ----------------------------
    async def heartbeat_loop(self):
        async with httpx.AsyncClient(timeout=2.0) as client:
            while True:
                await asyncio.sleep(5)

                for node in self.worker_urls:
                    if node in self.dead_nodes:
                        try:
                            health_path = "/api/tags" if self.backend == "ollama" else "/health"
                            response = await client.get(f"{node}{health_path}")

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

    # ----------------------------
    # MAIN ROUTING LOGIC (LEAST CONNECTIONS + ROUND-ROBIN TIE BREAK)
    # ----------------------------
    def _select_target(self):
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

    # ----------------------------
    # REQUEST HANDLING
    # ----------------------------
    async def route_request(self, payload):
        request_id = self._next_request_id()
        target_url = self._select_target()

        if not target_url:
            logger.error(
                "event=request_failed request_id=%s reason=no_available_workers active_connections=%s dead_nodes=%s",
                request_id,
                self._active_connections_snapshot(),
                self._dead_node_labels(),
            )
            return {
                "worker_id": "System Failure",
                "answer": "All workers are DOWN!",
                "latency": 0,
                "success": False
            }

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

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{target_url}/api/generate",
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

            # retry with remaining nodes
            return await self.route_request(payload)

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