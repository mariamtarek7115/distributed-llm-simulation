import asyncio
import time

import httpx

class LoadBalancer:
    def __init__(self, worker_urls, backend="custom", model_name=None):
        self.worker_urls = worker_urls.copy()
        self.active_connections = {url: 0 for url in worker_urls}
        self.dead_nodes = set()
        self.backend = backend
        self.model_name = model_name
        
        # Start the background heartbeat task automatically
        #asyncio.create_task(self.heartbeat_loop())

    # --- THE NEW HEARTBEAT FUNCTION ---
    async def heartbeat_loop(self):
        async with httpx.AsyncClient(timeout=2.0) as client:
            while True:
                await asyncio.sleep(5) # Check every 5 seconds
                
                # N-loop 3ala نسخة mn el dead_nodes 3shan hnghyar fiha
                for dead_url in list(self.dead_nodes):
                    try:
                        # Try to ping the dead node
                        health_path = "/api/tags" if self.backend == "ollama" else "/health"
                        response = await client.get(f"{dead_url}{health_path}")
                        if response.status_code == 200:
                            print(f"✅ [RECOVERY] Node {dead_url} is back online!")
                            self.dead_nodes.remove(dead_url)
                            self.active_connections[dead_url] = 0 # Reset connections
                    except:
                        # Lsa mayet, mt3mlsh 7aga
                        pass
                    
    async def route_request(self, payload):
        # 1. Filter out dead nodes
        available_nodes = {url: req for url, req in self.active_connections.items() if url not in self.dead_nodes}
        
        if not available_nodes:
            return {"worker_id": "System Failure", "answer": "All workers are DOWN!", "latency": 0}

        # 2. Least Connections Algorithm
        target_url = min(available_nodes, key=available_nodes.get)
        self.active_connections[target_url] += 1
        
        try:
            request_started_at = time.time()
            # Send request
            async with httpx.AsyncClient(timeout=120.0) as client:
                if self.backend == "ollama":
                    response = await client.post(
                        f"{target_url}/api/generate",
                        json={
                            "model": self.model_name,
                            "prompt": payload["prompt"],
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    response_payload = response.json()
                    return {
                        "worker_id": target_url,
                        "answer": response_payload.get("response", "").strip(),
                        "latency": time.time() - request_started_at,
                    }

                response = await client.post(f"{target_url}/process", json=payload)
                response.raise_for_status()
                return response.json()
                
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            # FAULT TOLERANCE LOGIC: Worker is down!
            print(f"⚠️ [ALERT] Node {target_url} is DOWN! Redirecting request...")
            self.dead_nodes.add(target_url) # Mark as dead
            
            # Try again with the remaining alive nodes
            return await self.route_request(payload)
            
        except Exception as e:
            return {"worker_id": "Error", "answer": str(e), "latency": 0}
            
        finally:
            if target_url in self.active_connections:
                self.active_connections[target_url] -= 1