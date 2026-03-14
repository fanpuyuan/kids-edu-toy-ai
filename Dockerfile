FROM python:3.10-bookworm

WORKDIR /app

# 安装必要的系统依赖 (针对音频处理 ASR/TTS 和网络请求)
RUN apt-get update && \
    apt-get install -y ffmpeg libsndfile1 gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# 1. 先安装 Torch 核心库 (体积最大)
RUN pip install --no-cache-dir --default-timeout=1000 \
    torch torchaudio

# 2. 升级 pip resolver
RUN pip install --upgrade pip setuptools wheel

# 3. 复制依赖清单并安装其余包
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 \
    -r requirements.txt

# 复制整个项目源码
COPY . .

# 暴露 FastAPI 端口 (8000) 和 Streamlit 端口 (8501)
EXPOSE 8000
EXPOSE 8501

# 默认启动点留空，由 docker-compose 的 command 覆盖
CMD ["/bin/bash"]
