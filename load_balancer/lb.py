import httpx
import asyncio

class LoadBalancer:
    def __init__(self, worker_urls):
        self.worker_urls = worker_urls.copy()
        self.active_connections = {url: 0 for url in worker_urls}
        self.dead_nodes = set() # N-keep track b el nodes elly wa23et

    async def route_request(self, payload):
        # 1. Filter out dead nodes
        available_nodes = {url: req for url, req in self.active_connections.items() if url not in self.dead_nodes}
        
        if not available_nodes:
            return {"worker_id": "System Failure", "answer": "All workers are DOWN!", "latency": 0}

        # 2. Least Connections Algorithm
        target_url = min(available_nodes, key=available_nodes.get)
        self.active_connections[target_url] += 1
        
        try:
            # Send request
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{target_url}/process", json=payload)
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