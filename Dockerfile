# Alternative container deploy (Fly.io, Koyeb, Render docker runtime, any host).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
