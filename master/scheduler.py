from load_balancer.lb import LoadBalancer
from rag.retriever import RAGRetriever

class Scheduler:
    def __init__(self, lb: LoadBalancer):
        self.lb = lb
        self.rag = RAGRetriever() # Initialize RAG

    async def handle_request(self, payload):
        # 1. Retrieve Context mn el Knowledge Base
        context = self.rag.get_context(payload['prompt'])
        
        # 2. Augment Prompt (Da5al el ma3loma f so2al el user)
        original_prompt = payload['prompt']
        payload['prompt'] = f"Context: {context}\nAnswer this based on context: {original_prompt}"
        
        # 3. Forward lel Load Balancer
        response = await self.lb.route_request(payload)
        return response