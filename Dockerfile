# 洗衣店管理系统 —— 运行镜像
# 说明：AGENT 的动作卡（ACTION_STORE）是进程内存，所以这里固定单进程 1 worker；
#      要横向扩容必须先把 ACTION_STORE 落表/落 Redis（见 docs/architecture-decisions.md）

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LAUNDRY_ENV=production \
    LAUNDRY_PORT=8000 \
    LAUNDRY_HOST=0.0.0.0 \
    LAUNDRY_DATABASE_URL=sqlite:////data/laundry.db

WORKDIR /app

# 默认走清华源：国内云服务器构建快很多；海外构建可 --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
COPY tests ./tests
COPY run.py ./

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

# 生产环境必须由外部注入 LAUNDRY_SECRET_KEY，否则 config 会拒绝启动
CMD ["python", "run.py", "8000", "0.0.0.0"]
