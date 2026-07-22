# ── Stage 1: Backend ──
FROM python:3.10-slim AS backend

WORKDIR /app

# 系统依赖（摄像头/音频相关）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 项目代码
COPY backend/ backend/
COPY modules/ modules/
COPY data/ data/
COPY .env .env.example

# 知识库 & FAISS 索引目录（构建时自动生成）
RUN mkdir -p data/knowledge/faiss_index

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ── Stage 2: Frontend (nginx 静态托管) ──
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build


FROM nginx:alpine AS frontend

# 复制构建产物
COPY --from=frontend-build /build/dist /usr/share/nginx/html

# Vite 代理 → 容器内 backend
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80


# ── Stage 3: Netease Music API ──
FROM node:20-alpine AS music-api

WORKDIR /app
COPY tools/netease-cloud-music-api/package.json ./
RUN npm install
COPY tools/netease-cloud-music-api/ .
EXPOSE 3000

CMD ["node", "app.js"]
