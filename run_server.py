"""开发服务器入口：``python run_server.py``。

监听 0.0.0.0:8000，便于容器 / 预览环境访问；
端口与日志级别可用 ``DEEMBED_HOST`` / ``DEEMBED_PORT`` / ``DEEMBED_LOG_LEVEL`` 覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.environ.get("DEEMBED_HOST", "0.0.0.0"),
        port=int(os.environ.get("DEEMBED_PORT", "8000")),
        log_level=os.environ.get("DEEMBED_LOG_LEVEL", "info"),
    )
