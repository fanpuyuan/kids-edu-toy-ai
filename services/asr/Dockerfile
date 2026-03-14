FROM python:3.10-bookworm

WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg libsndfile1 gcc g++ && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --default-timeout=1000 \
    torch torchaudio --index-url https://download.pytorch.org/whl/cpu

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]
