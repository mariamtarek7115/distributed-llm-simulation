from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class RAGRetriever:
    def __init__(self):
        # Model khafeef gedan lel Embeddings (bey7awel el kalam le arkam)
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Knowledge Base: Momken tb2a list of strings aw t2ra mn text file
        self.documents = [
            "Ain Shams University Faculty of Engineering is located in Cairo.",
            "CSE354 is a Distributed Computing course where students build scalable systems.",
            "A Load Balancer distributes incoming network traffic across multiple servers.",
            "Context switching in ARM Cortex-M4 involves saving the Program Counter and Stack Pointer."
        ]
        
        # Build the Vector Database (FAISS)
        self.embeddings = self.model.encode(self.documents)
        self.index = faiss.IndexFlatL2(self.embeddings.shape[1])
        self.index.add(self.embeddings)

    def get_context(self, query, top_k=2): # 5alena top_k=2 hena
            # Search for the most relevant sentences
            query_vector = self.model.encode([query])
            distances, indices = self.index.search(query_vector, top_k)
            
            # Combine the retrieved documents into one context string
            retrieved_docs = [self.documents[idx] for idx in indices[0]]
            combined_context = " | ".join(retrieved_docs)
            
            return combined_context