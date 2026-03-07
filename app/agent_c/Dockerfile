FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/agent_c/src

COPY . /app
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e /app/agent_c

EXPOSE 8080

CMD ["uvicorn", "agent_c.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
