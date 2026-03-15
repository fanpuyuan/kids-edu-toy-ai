FROM python:3.10-slim

# Install system dependencies required for unstructured and building C++ extensions
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libmagic-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip to avoid installation errors
RUN pip install --upgrade pip

# Copy and install requirements
COPY requirements.txt .
# Use tuna mirror for faster installation in China
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8003

# Run the FastAPI application
CMD ["python", "main.py"]
