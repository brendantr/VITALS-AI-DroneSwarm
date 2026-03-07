FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY agent_b/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.lock.txt

COPY . /app
EXPOSE 8081

CMD ["uvicorn", "agent_b.agent_b_service:app", "--host", "0.0.0.0", "--port", "8081"]
