"""启动入口

python run.py            # 本机 7777，只监听 127.0.0.1
python run.py 8000       # 换端口
python run.py 8000 0.0.0.0   # 监听所有网卡（容器里用这个）
环境变量 LAUNDRY_HOST / LAUNDRY_PORT 也认。
"""
import os
import sys

import uvicorn


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("LAUNDRY_PORT", "7777"))
    host = sys.argv[2] if len(sys.argv) > 2 else os.getenv("LAUNDRY_HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
