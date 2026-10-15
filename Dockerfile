FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends calibre mupdf-tools && rm -rf /var/lib/apt/lists/*  # ponytail: heavy but gold-standard fallback, drop if image too big
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
