from transformers import pipeline


class LLMHandler:
    def __init__(self):
        # Lightweight GPT-2 model (CPU-friendly)
        self.generator = pipeline("text-generation", model="gpt2")

    def generate(self, prompt): 
        # Esta5dm max_new_tokens badal max_length
        result = self.generator(prompt, max_new_tokens=50, num_return_sequences=1) 
        
        # 3ashan n-extract el egeba el gedida bas w nesheel el prompt mn el output
        generated_text = result[0]['generated_text']
        answer_only = generated_text.replace(prompt, "").strip()
        
        return answer_only