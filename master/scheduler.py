# master/scheduler.py

import asyncio
import time

from load_balancer.lb import LoadBalancer
from rag.retriever import RAGRetriever


class Scheduler:
    def __init__(
        self,
        lb: LoadBalancer,
        max_workers: int = 4,
        queue_size: int = 200,
        retry_workers: int = 2,
        max_retries: int = 3,
        request_timeout: int = 120,
    ):
        self.lb = lb
        self.rag = RAGRetriever()

        # ----------------------------
        # MAIN REQUEST QUEUE
        # ----------------------------
        self.queue = asyncio.Queue(maxsize=queue_size)

        # ----------------------------
        # RETRY QUEUE
        # ----------------------------
        self.retry_queue = asyncio.Queue(maxsize=queue_size)

        # ----------------------------
        # CONFIG
        # ----------------------------
        self.max_workers = max_workers
        self.retry_workers = retry_workers
        self.max_retries = max_retries
        self.request_timeout = request_timeout

        self.workers_started = False

        # ----------------------------
        # QUEUE-LOG BATCHING
        # ----------------------------
        # Avoid flooding the terminal with one [QUEUE] line per admission.
        # Buffer admitted user_ids and flush them as a single summary line
        # either when the batch fills up or when enough time passes.
        self._queue_log_batch = []
        self._queue_log_batch_size = 10
        self._queue_log_flush_interval = 0.5  # seconds
        self._queue_log_last_flush = time.monotonic()

    def _flush_queue_log(self, force=False):
        if not self._queue_log_batch:
            self._queue_log_last_flush = time.monotonic()
            return
        now = time.monotonic()
        if (
            force
            or len(self._queue_log_batch) >= self._queue_log_batch_size
            or (now - self._queue_log_last_flush) >= self._queue_log_flush_interval
        ):
            ids = self._queue_log_batch
            if len(ids) == 1:
                label = f"user={ids[0]}"
            else:
                label = f"users={ids[0]}-{ids[-1]} ({len(ids)} admitted)"
            print(
                f"[QUEUE] {label} | "
                f"queue_size={self.queue.qsize()}/{self.queue.maxsize}"
            )
            self._queue_log_batch = []
            self._queue_log_last_flush = now

    # =========================================================
    # PUBLIC ENTRY POINT
    # =========================================================
    async def handle_request(self, payload):
        start = time.time()
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # retry count starts at 0
        payload["retry_count"] = 0

        user_id = payload.get("user_id", "unknown")

        # enqueue request
        try:
            self.queue.put_nowait((payload, future))
            self._queue_log_batch.append(user_id)
            self._flush_queue_log()
        except asyncio.QueueFull:
            # Flush any pending queue admissions so the OVERLOADED line
            # appears in the correct chronological position.
            self._flush_queue_log(force=True)
            overload_response = {
                "request_id": payload.get("request_id"),
                "worker_id": "SYSTEM_OVERLOAD",
                "latency": time.time() - start,
                "success": True,
                "fallback": True,
                "answer": "System is overloaded. Try again later.",
            }
            print(
                f"[OVERLOADED] user={user_id} rejected | "
                f"queue_size={self.queue.qsize()}/{self.queue.maxsize} | "
                f"latency={overload_response['latency']:.4f}s | "
                f"response={overload_response['answer']}"
            )
            return overload_response

        # start workers once
        if not self.workers_started:
            self.workers_started = True

            # main dispatchers
            for _ in range(self.max_workers):
                asyncio.create_task(self._dispatcher())

            # retry dispatchers
            for _ in range(self.retry_workers):
                asyncio.create_task(self._retry_dispatcher())

        return await future

    # =========================================================
    # MAIN DISPATCHER
    # =========================================================
    async def _dispatcher(self):
        while True:
            payload, future = await self.queue.get()

            try:
                result = await self._process_request(payload)

                future.set_result(result)

            except Exception as e:
                await self._handle_failure(payload, future, str(e))

            finally:
                self.queue.task_done()

    # =========================================================
    # RETRY DISPATCHER
    # =========================================================
    async def _retry_dispatcher(self):
        while True:
            payload, future = await self.retry_queue.get()

            try:
                retry_count = payload["retry_count"]

                # exponential backoff
                retry_delay = 2 * retry_count

                await asyncio.sleep(retry_delay)

                result = await self._process_request(payload)

                future.set_result(result)

            except Exception as e:
                await self._handle_failure(payload, future, str(e))

            finally:
                self.retry_queue.task_done()

    # =========================================================
    # ACTUAL PROCESSING
    # =========================================================
    async def _process_request(self, payload):

        start_time = time.time()

        # ----------------------------
        # OPTIONAL RAG ENRICHMENT
        # ----------------------------
        if payload.get("use_rag", False):

            context = self.rag.get_context(payload["prompt"])

            payload["prompt"] = (
                f"Context:\n{context}\n\n"
                f"Question: {payload['prompt']}\n\n"
                f"Answer:"
            )

        # ----------------------------
        # TIMEOUT WRAPPER
        # ----------------------------
        try:
            result = await asyncio.wait_for(
                self.lb.route_request(payload),
                timeout=self.request_timeout
            )
        except asyncio.TimeoutError:
            raise Exception("Request timed out")
        finally:
            total_latency = time.time() - start_time

        if not result.get("success", True) and result.get("retryable", True):
            raise Exception(result.get("answer", "Unknown worker failure"))

        return {
            "request_id": result.get("request_id"),
            "worker_id": result["worker_id"],
            "latency": total_latency,
            "success": result.get("success", True),
            "fallback": result.get("fallback", False),
            "answer": result["answer"][:120]
        }

    # =========================================================
    # FAILURE HANDLER
    # =========================================================
    async def _handle_failure(self, payload, future, error_message):

        payload["retry_count"] += 1

        retry_count = payload["retry_count"]
        user_id = payload.get("user_id", "unknown")

        # -------------------------------------------------
        # SEND TO RETRY QUEUE
        # -------------------------------------------------
        if retry_count <= self.max_retries:

            backoff = 2 * retry_count
            print(
                f"[RETRY] user={user_id} | attempt={retry_count}/{self.max_retries} | "
                f"reason={error_message} | backoff={backoff}s | "
                f"retry_queue_size={self.retry_queue.qsize()}/{self.retry_queue.maxsize}"
            )
            await self.retry_queue.put((payload, future))

        # -------------------------------------------------
        # FINAL FAILURE
        # -------------------------------------------------
        else:

            print(
                f"[FAILED] user={user_id} | retries_exhausted ({self.max_retries}) | "
                f"last_reason={error_message}"
            )
            future.set_result({
                "request_id": payload.get("request_id"),
                "worker_id": "TIMEOUT",
                "latency": 0,
                "success": False,
                "fallback": False,
                "answer": (
                    f"Request failed after "
                    f"{self.max_retries} retries."
                )
            })