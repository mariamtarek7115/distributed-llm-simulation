from transformers import pipeline

class LLMHandler:
    def __init__(self):
        self.generator = pipeline('text-generation', model='Qwen/Qwen1.5-0.5B-Chat')

    def generate(self, prompt): 
        # 1. El Format el sa7 lel Chat Models (List of messages)
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Answer briefly based on the context."},
            {"role": "user", "content": prompt}
        ]
        
        # 2. El Pipeline delwa2ty btfham el messages automatically
        result = self.generator(
            messages, 
            max_new_tokens=50, 
            num_return_sequences=1
        ) 
        
        # 3. El Nateeja btrga3 3ala hy2et list of messages, h-na5od a5er wa7da (Assistant reply)
        generated_data = result[0]['generated_text']
        ai_generated_answer = generated_data[-1]['content'].strip()
        
        return ai_generated_answer