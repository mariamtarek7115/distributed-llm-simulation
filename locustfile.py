from locust import HttpUser, task, between
import random

QUESTIONS = [
    "Where is Ain Shams University?",
    "What do we learn in CSE354?",
    "How does a Load Balancer work?",
    "What is context switching in ARM Cortex-M4?"
]

class LLMClient(HttpUser):
    # El User bystna mn 1 le 3 sawany ben kol so2al w el tany (3ashan yb2a realistic)
    wait_time = between(1, 3)

    @task
    def ask_llm(self):
        payload = {
            "user_id": random.randint(1, 10000),
            "prompt": random.choice(QUESTIONS),
            "use_rag": True
        }
        # By-drob el API Gateway bta3na 3ala port 8000
        with self.client.post("/chat", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed! Status: {response.status_code}")