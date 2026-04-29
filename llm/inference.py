from transformers import pipeline


class LLMHandler:
    def __init__(self):
        # Lightweight GPT-2 model (CPU-friendly)
        self.generator = pipeline("text-generation", model="gpt2")

    def generate(self, prompt, context=""):
        full_prompt = f"Context: {context}\nQuestion: {prompt}\nAnswer:"
        
        result = self.generator(
            full_prompt,
            max_length=50,
            num_return_sequences=1
        )

        return result[0]["generated_text"]