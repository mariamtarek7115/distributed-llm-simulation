from load_balancer.lb import LoadBalancer
from rag.retriever import RAGRetriever

class Scheduler:
    def __init__(self, lb: LoadBalancer):
        self.lb = lb
        self.rag = RAGRetriever()

    async def handle_request(self, payload):
        if payload.get('use_rag', False):
            context = self.rag.get_context(payload['prompt'])
            
            # Format kbeer w wade7 lel AI 3ashan yfham el task
            payload['prompt'] = (
                f"Read this context: {context}\n\n"
                f"Question: {payload['prompt']}\n\n"
                f"Answer:"
            )
            
        response = await self.lb.route_request(payload)
        return response