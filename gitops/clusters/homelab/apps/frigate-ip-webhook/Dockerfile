FROM python:3.12-slim

RUN pip install --no-cache-dir flask kubernetes

WORKDIR /app
COPY webhook.py .

EXPOSE 8080
CMD ["python", "-u", "webhook.py"]
