FROM python:3.11-slim

# 系统依赖（psycopg2 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 复制源码
COPY . .

# 收集静态文件
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

# gunicorn 启动 — 3 worker 适合中小规模部署
CMD ["gunicorn", "ai_skill_project.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "180", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
