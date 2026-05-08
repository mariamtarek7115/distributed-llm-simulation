FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .

# 1. Download PyTorch CPU Version (200MB instead of 3GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 2. Download the rest of the libraries
RUN pip install --no-cache-dir -r requirements.txt

COPY . .