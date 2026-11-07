"""全局配置"""
import os
import secrets
from pathlib import Path

# laundry_management 目录
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "laundry.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"


def _load_env_file(path: Path) -> None:
    """极简 .env 读取（避免为一个功能引入额外依赖）：KEY=VALUE，忽略注释与空行"""
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            # 已存在的真实环境变量优先
            os.environ.setdefault(key, value)
    except OSError:
        pass


_load_env_file(BASE_DIR / ".env")

# 数据库连接串（SQLite 文件，沿用原有 laundry.db，不迁移数据）
DATABASE_URL = os.getenv("LAUNDRY_DATABASE_URL", f"sqlite:///{DB_PATH}")

# 运行环境：dev / production
APP_ENV = os.getenv("LAUNDRY_ENV", "dev").strip().lower()

# JWT 配置
# 密钥的三条规则（对应 P0-4：不许带着默认密钥上线）
#   1. 配了 LAUNDRY_SECRET_KEY -> 用它（生产必须走这条）
#   2. 生产环境没配 -> 直接拒绝启动，不给"默认密钥就能伪造 admin token"的机会
#   3. 开发环境没配 -> 每次进程启动随机生成，重启后旧 token 失效，不再硬编码在代码里
_secret_from_env = os.getenv("LAUNDRY_SECRET_KEY", "").strip()
DEV_SECRET_GENERATED = False
if _secret_from_env:
    SECRET_KEY = _secret_from_env
elif APP_ENV in ("prod", "production"):
    raise RuntimeError(
        "production 环境必须设置 LAUNDRY_SECRET_KEY（至少 32 字符），拒绝以默认密钥启动"
    )
else:
    SECRET_KEY = secrets.token_hex(32)
    DEV_SECRET_GENERATED = True

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 12 * 60

# 员工注册：只认邀请码（对应 P0-2）
#   为空 = 关闭公开注册，只能由管理员在管理端建号
STAFF_INVITE_CODE = os.getenv("LAUNDRY_STAFF_INVITE_CODE", "").strip()

# 登录失败限流（进程内存实现，单进程有效；多进程部署请换 Redis）
LOGIN_MAX_FAILURES = int(os.getenv("LAUNDRY_LOGIN_MAX_FAILURES", "10"))   # 窗口内最多错几次
LOGIN_WINDOW_SECONDS = int(os.getenv("LAUNDRY_LOGIN_WINDOW_SECONDS", "300"))  # 统计窗口
LOGIN_LOCK_SECONDS = int(os.getenv("LAUNDRY_LOGIN_LOCK_SECONDS", "300"))      # 锁多久

# 库存与订单挂钩：每件衣服折算消耗多少"洗涤耗材"（结算时扣减并留用量流水）
INVENTORY_SUPPLY_NAME = os.getenv("LAUNDRY_INVENTORY_SUPPLY_NAME", "洗涤耗材")
INVENTORY_PER_PIECE = int(os.getenv("LAUNDRY_INVENTORY_PER_PIECE", "1"))

# 会员积分规则：消费 1 元 = 1 积分
POINTS_PER_YUAN = 1

# 会员等级门槛（累计积分）
LEVEL_THRESHOLDS = [
    (1500, 4),  # 钻石会员
    (800, 3),   # 金卡会员
    (300, 2),   # 银卡会员
    (100, 1),   # 普通会员
    (0, 0),     # 普通客户
]
LEVEL_NAMES = {
    0: "普通客户",
    1: "普通会员",
    2: "银卡会员",
    3: "金卡会员",
    4: "钻石会员",
}

ORDER_STATUS_RECEIVED = "received"    # 已收衣，待洗涤
ORDER_STATUS_WASHING = "washing"      # 洗涤中
ORDER_STATUS_READY = "ready"          # 可取衣
ORDER_STATUS_COMPLETED = "completed"  # 已完成
ORDER_STATUS_CANCELLED = "cancelled"  # 已取消

ORDER_STATUS_TEXT = {
    ORDER_STATUS_RECEIVED: "待洗涤",
    ORDER_STATUS_WASHING: "洗涤中",
    ORDER_STATUS_READY: "可取衣",
    ORDER_STATUS_COMPLETED: "已完成",
    ORDER_STATUS_CANCELLED: "已取消",
}

# 仍在店内、可继续流转的状态
ACTIVE_STATUSES = (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING, ORDER_STATUS_READY)

# 允许的流转关系：目标状态 -> 允许的来源状态
STATUS_TRANSITIONS = {
    ORDER_STATUS_WASHING: (ORDER_STATUS_RECEIVED,),
    ORDER_STATUS_READY: (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING),
    ORDER_STATUS_COMPLETED: (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING, ORDER_STATUS_READY),
    ORDER_STATUS_CANCELLED: (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING, ORDER_STATUS_READY),
}

# 会员等级折扣（结算时按等级打折）
MEMBER_DISCOUNT = {
    0: 1.00,  # 普通客户
    1: 0.95,  # 普通会员
    2: 0.90,  # 银卡会员
    3: 0.85,  # 金卡会员
    4: 0.80,  # 钻石会员
}

# ---------------- Agent 配置 ----------------
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
AGNES_MODEL = os.getenv("AGNES_MODEL", "agnes-3.0-flash")
AGENT_MAX_ROUNDS = int(os.getenv("AGENT_MAX_ROUNDS", "4"))      # 最多几轮"调工具→再问模型"
AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT", "90"))          # 单次模型调用超时（秒），失败会再重试一次
AGENT_HISTORY_TURNS = int(os.getenv("AGENT_HISTORY_TURNS", "6"))  # 携带多少条历史进上下文
# 图引擎：loop=手写循环（默认，零依赖）；langgraph=换 LangGraph 节点编排（需 pip install langgraph）
AGENT_ENGINE = os.getenv("AGENT_ENGINE", "loop").strip().lower()
# 知识库未命中时的固定话术：宁可说不知道，也不让模型编
CARE_FALLBACK_TEXT = "这条我没查到依据。洗护工艺请以衣物上的洗涤标志和门店师傅的判断为准，我不好替你猜。"

