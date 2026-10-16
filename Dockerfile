FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY static/ ./static/

ENV PYTHONUNBUFFERED=1
ENV PORT=8095

EXPOSE 8095

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8095"]
