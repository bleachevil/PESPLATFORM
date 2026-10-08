FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY importer ./importer
COPY web ./web
COPY data/google_oauth.env.example ./data/google_oauth.env.example
COPY data/sample ./data/sample

EXPOSE 8080
CMD ["sh", "-c", "python -m uvicorn web.app:app --host 0.0.0.0 --port ${PORT}"]
