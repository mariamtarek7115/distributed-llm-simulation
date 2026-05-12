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

    # =========================================================
    # PUBLIC ENTRY POINT
    # =========================================================
    async def handle_request(self, payload):
        start = time.time()
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # retry count starts at 0
        payload["retry_count"] = 0

        # enqueue request
        try:
            self.queue.put_nowait((payload, future))
        except asyncio.QueueFull:
            overload_response = {
                "request_id": payload.get("request_id"),
                "worker_id": "SYSTEM_OVERLOAD",
                "latency": time.time() - start,
                "success": True,
                "fallback": True,
                "answer": "System is overloaded. Try again later.",
            }
            print(
                f"[SCHEDULER] OVERLOADED | request_id={overload_response['request_id']} | "
                f"latency={overload_response['latency']:.4f}s | response={overload_response['answer']}"
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

        # -------------------------------------------------
        # SEND TO RETRY QUEUE
        # -------------------------------------------------
        if retry_count <= self.max_retries:

            await self.retry_queue.put((payload, future))

        # -------------------------------------------------
        # FINAL FAILURE
        # -------------------------------------------------
        else:

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