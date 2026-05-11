import asyncio
import time

from load_balancer.lb import LoadBalancer
from rag.retriever import RAGRetriever


class Scheduler:
    def __init__(self, lb: LoadBalancer, max_workers: int = 4, queue_size: int = 200, timeout: int = 120):
        self.lb = lb
        self.rag = RAGRetriever()

        self.queue = asyncio.Queue(maxsize=queue_size)

        self.max_workers = max_workers
        self.workers_started = False

        # 🔥 request timeout (seconds)
        self.timeout = timeout

    # ----------------------------
    # PUBLIC ENTRY POINT (FastAPI calls this)
    # ----------------------------
    async def handle_request(self, payload):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        await self.queue.put((payload, future))

        # start dispatcher pool once
        if not self.workers_started:
            self.workers_started = True
            for _ in range(self.max_workers):
                asyncio.create_task(self._dispatcher())

        # 🔥 attach timeout watchdog
        asyncio.create_task(self._timeout_handler(future))

        return await future

    # ----------------------------
    # TIMEOUT HANDLER
    # ----------------------------
    async def _timeout_handler(self, future):
        await asyncio.sleep(self.timeout)

        if not future.done():
            future.set_result({
                "worker_id": "TIMEOUT",
                "answer": "Request expired due to high load. Please retry.",
                "latency": self.timeout,
                "success": False
            })

    # ----------------------------
    # DISPATCHER WORKERS
    # ----------------------------
    async def _dispatcher(self):
        while True:
            payload, future = await self.queue.get()

            try:
                start_wait = time.time()

                # ----------------------------
                # RAG (optional)
                # ----------------------------
                if payload.get("use_rag", False):
                    context = self.rag.get_context(payload["prompt"])
                    payload["prompt"] = (
                        f"Context:\n{context}\n\n"
                        f"Question: {payload['prompt']}\n\n"
                        f"Answer:"
                    )

                # ----------------------------
                # LOAD BALANCER CALL
                # ----------------------------
                result = await self.lb.route_request(payload)

                result["queue_wait_time"] = time.time() - start_wait

                # only set result if not timed out
                if not future.done():
                    future.set_result(result)

            except Exception as e:
                if not future.done():
                    future.set_result({
                        "worker_id": "System Error",
                        "answer": str(e),
                        "latency": 0,
                        "success": False
                    })

            finally:
                self.queue.task_done()