# 洗衣店管理系统（v5・双端闭环 + 双 Agent + 加固版）

课设系统重构为 **FastAPI 分层架构**，业务逻辑全部收敛到 `app/services/`，REST 接口与 Agent 工具共用同一份代码。

原有的 `server.py`（标准库 http.server 版本）保留未动，两套可同时存在、互不影响。

四轮升级做过的事：



| 阶段     | 内容                                                                                     | 结果                      |
| ------ | -------------------------------------------------------------------------------------- | ----------------------- |
| v1     | 单文件 `http.server` → FastAPI 分层（config /db/models /schemas/security /services/routers）  | 28 项测试通过                |
| v2.1   | 业务闭环（五态订单、服务端计价、会员折扣、逾期提醒、趋势统计）+ 前端设计系统重做                                              | 65 项测试通过                |
| v3 一期  | 客户账号 + 三层权限（登录 → 角色 → 归属）+ 客户端只读视图 + 越权测试                                              | 65 + 52 项测试通过           |
| v3 二期  | 洗护知识库 `care_rules` + 客户端 Agent（5 个只读工具 + 对话循环 + 出处）                                    | +41 项 Agent 测试（接真模型 44） |
| v4 三期  | 上门取件预约（两层单：预约 + 洗衣单）+ 线上点单 + 到店复核调价 + 客户端自助下单                                          | 59 项三期测试通过              |
| v4 四期  | 管理端 Agent（9 个工具 + 3 个写操作两段式确认）+ `/chat` 页面 + 评估集 37 条                                  | 37 项四期测试通过；评估桩模式 37/37  |
| v4 可选  | LangGraph 引擎换装（`AGENT_ENGINE=langgraph` 切换）+ 会话持久化到 `chat_messages`                    | +20 项对照测试               |
| v5 加固  | 五条硬伤（未确认调价不许结算 / 员工注册要邀请码 / 客户不能认领老档案 / 密钥不硬编码 / 财务可审计）+ 站内消息 / 库存扣减 / 登录限流 / Agent 指标 | +43 项加固测试，全量 320 项      |
| v5 工程化 | Dockerfile + compose + GitHub Actions 门禁 + 压测脚本 + 评估集扩到 80 条 + 架构决策记录                  | 320 项 + 评估 80/80        |

## 目录结构



```
laundry_management/
├── app/
│   ├── main.py              # FastAPI 入口：Jinja2 页面渲染、静态资源、统一异常出口
│   ├── config.py            # 路径、JWT、五态状态机、状态流转表、会员折扣表、积分等级规则
│   ├── db.py                # SQLAlchemy 引擎与会话
│   ├── models.py            # ORM（映射原有表 + order_items；orders 增加折前金额/折扣率/等级快照）
│   ├── schemas.py           # Pydantic v2 契约（OrderItemIn / QuoteRequest / OrderStatusRequest …）
│   ├── security.py          # bcrypt 密码哈希 + JWT 签发/校验（token 内含 role 与 customer_id）
│   ├── deps.py              # ★ 三层权限依赖：get_current_user / require_staff / require_customer
│   ├── exceptions.py        # ServiceError / NotFoundError / ConflictError
│   ├── services/            # ★ 业务逻辑唯一入口，REST 与 Agent 共用
│   │   ├── items_parser.py      # 明细文本 ↔ 结构化行（独立模块，避免循环导入）
│   │   ├── pricing_service.py   # 服务端计价：查价目表、套会员折扣、试算、反向生成文本
│   │   ├── order_service.py     # 建单验价、五态流转、幂等结算、逾期查询、禁删已完成单
│   │   │                        # + 客户端视角：list_orders_of_customer / get_order_of_customer / customer_summary
│   │   ├── auth_service.py      # 员工登录注册 + 客户注册/登录（手机号即账号）
│   │   ├── customer_service.py  # 会员 CRUD + 结算累计积分/升级
│   │   ├── catalog_service.py
│   │   ├── inventory_service.py # 出入库、低库存预警
│   │   ├── stats_service.py     # 看板、日报、区间报表、服务排行、近 N 日趋势
│   │   ├── notification_service.py # v5：站内消息（调价/可取衣/预约/取消）
│   │   ├── metric_service.py       # v5：Agent 每轮调用落库 + P50/P95 汇总
│   │   ├── login_guard.py          # v5：登录失败限流（进程内存，10 次/5 分钟锁 5 分钟）
│   │   └── log_service.py
│   └── routers/             # HTTP 层，只做参数解析与调用 services
│       ├── auth.py / orders.py / customers.py
│       ├── catalog.py / stats.py / inventory.py
│       ├── appointments.py    # 上门取件预约（管理端，GET + PATCH）
│       ├── staff_chat.py      # 员工助手对话 + 动作卡 + /api/staff/metrics
│       └── me.py            # ★ 客户端接口 /api/my/*（身份只来自 token）+ /api/my/notifications
├── app/agent/               # ★ 双端 Agent
│   ├── tools.py             # 客户端 5 个只读工具（签名里没有手机号，身份由 ToolContext 注入）
│   ├── staff_tools.py       # 员工 7 个只读 + 3 个 propose 写工具（ACTION_STORE 两段式确认）
│   ├── llm.py               # Agnes（OpenAI 兼容）调用封装，超时重试
│   ├── graph.py             # 客户端对话循环：模型决策 → 执行工具 → 观察 → 再决策
│   ├── graph_lg.py          # 同一套逻辑的 LangGraph 版（plan / act / give_up 三节点）
│   └── staff_graph.py       # 员工对话循环 + 动作卡回传
├── templates/               # 20 个 Jinja2 模板（管理端 14；客户端 6：登录/首页/订单/下单/助手/消息）
├── static/
│   ├── css/app.css          # 设计系统（CSS 变量、卡片/表格/徽标/Toast/图表/小票/动作卡）
│   ├── css/me.css           # 客户端样式（登录双栏、会员卡、步骤条、对话气泡、下单页）
│   └── js/                  # api.js、app.js、10 个管理端页面脚本、me*.js 客户端脚本
├── tests/
│   ├── smoke_test.py        # 65 项端到端测试（在临时库副本上运行）
│   ├── permission_test.py   # 52 项权限/越权测试（同上，独立临时库）
│   ├── agent_test.py        # 41 项客户端 Agent 测试（打桩模型 41，接真模型 44）
│   ├── phase3_test.py       # 59 项三期测试（预约两层单 / 线上点单 / 调价复核）
│   ├── staff_agent_test.py  # 37 项四期测试（员工工具 / 两段式写操作 / 权限 / 页面）
│   └── langgraph_test.py    # 20 项引擎对照测试（手写循环 vs LangGraph 行为一致）
├── scripts/
│   ├── migrate_order_items.py   # v1：历史订单明细回填
│   ├── migrate_v2.py            # v2：加字段 + pending→ready + 折前金额回填（幂等）
│   ├── migrate_v3.py            # v3：users 加 customer_id 列与唯一索引（幂等）
│   ├── migrate_v4.py            # v4：订单加来源/复核字段 + appointments 等 3 张表（幂等）
│   ├── seed_care_rules.py       # 洗护知识库种子（幂等，10 条规则）
│   ├── migrate_v5.py            # v5：orders 加 is_deleted + notifications / agent_metrics / inventory_usages 三张表
│   ├── migrate_v6.py            # v6：agent_metrics 加 question 字段（指标看板要看坏例子）
│   ├── eval_cases.json          # Agent 评估语料 80 条（客户 50 / 员工 30，11 个 category）
│   ├── eval_agent.py            # 评估脚本：用例通过 / 工具命中 / 越权拒绝 / 禁忌调用
│   ├── load_test.py             # 压测：QPS / P50 / P95 / P99 / 错误率
│   └── verify_data.py           # 数据完整性验收
├── docs/
│   ├── agent-plan.md        # 三期实施方案（权限/拆单/Agent 工具白名单）
│   ├── phase1-progress.md   # 一期进度：客户账号 + 权限地基
│   ├── phase2-agent.md      # 二期进度：洗护知识库 + 客户端 Agent
│   ├── phase3-progress.md   # 三期四期 + 可选项进度：双端闭环 + 双 Agent + 评估集
│   └── architecture-decisions.md # 架构决策记录（ADR）：为什么这么拆
├── run.py                   # 新入口：python run.py [端口]
├── requirements.txt
├── .env / .env.example      # 模型密钥（.env 不进仓库）
└── server.py                # 旧入口（保留，未改动）
```

## 启动



```
pip install -r requirements.txt
python run.py 7777          # http://127.0.0.1:7777
```



* 接口文档：[http://127.0.0.1:7777/docs](http://127.0.0.1:7777/docs)

* 管理端账号：`admin / admin123`、`staff / staff123` → 登录入口 `/login`

* 客户端入口：[http://127.0.0.1:7777/me/login](http://127.0.0.1:7777/me/login)；主库已为老客户 `lk` 开通账号：手机号 `123456` / 密码 `pass1234`（v5 起老档案不能在客户端自助注册，只能门店开通）

* 旧版本启动方式仍然可用：`python server.py 7777`（两者不要同时占用同一端口）

> 从 v2 升级到 v3 需要先跑一次 
>
> `python scripts/migrate_v3.py`
>
> （给 
>
> `users`
>
>  加 
>
> `customer_id`
>
>  列）。
> 从 v3 升级到 v4 需要再跑一次 
>
> `python scripts/migrate_v4.py`
>
> （订单加来源 / 复核字段，新建预约与消息表）。
> 从 v4 升级到 v5 需要再跑一次 
>
> `python scripts/migrate_v5.py`
>
> （订单加软删标记 + 站内消息 / 指标 / 耗材用量三张表）。
> v5 的 Agent 指标看板要 
>
> `python scripts/migrate_v6.py`
>
> （给 
>
> `agent_metrics`
>
>  补 
>
> `question`
>
>  字段）。
> v5 起员工注册要邀请码：
>
> `.env`
>
>  里设 
>
> `LAUNDRY_STAFF_INVITE_CODE`
>
> （本地是 
>
> `laundry-2026`
>
> ），不设就直接关掉公开注册。
> v5 起密钥不硬编码：
>
> `LAUNDRY_ENV=production`
>
>  必须给 
>
> `LAUNDRY_SECRET_KEY`
>
> ，否则拒绝启动；dev 每次启动随机生成。
> 新库不用跑，
>
> `create_all`
>
>  会直接建全表；但 
>
> `create_all`
>
>  只建缺失表、不改已有表，改既有表必须走迁移脚本。
> 洗护知识库是全新表，跑一次 
>
> `python scripts/seed_care_rules.py`
>
>  灌 10 条规则即可（幂等）。
> Agent 需要项目根目录有 
>
> `.env`
>
> （填 
>
> `AGNES_API_KEY`
>
> ），没填时接口会提示 "还没配置模型密钥" 而不是崩掉。
> 想让 Agent 走 LangGraph：
>
> `pip install langgraph`
>
> ，然后在 
>
> `.env`
>
>  里加 
>
> `AGENT_ENGINE=langgraph`
>
> （默认 
>
> `loop`
>
> ，零依赖）。

## 页面

### 管理端（员工 / 管理员）



| 路径              | 页面       | 说明                                                     |
| --------------- | -------- | ------------------------------------------------------ |
| `/`             | 门店概览     | 四张统计卡、近 7 日趋势柱图、财务速览、逾期未取、最近订单                         |
| `/login`        | 登录       | 双栏布局，登录 / 注册员工同一页切换                                    |
| `/receive`      | 收衣建单     | 明细行编辑 + 右侧实时试算 + 收衣单打印                                 |
| `/orders`       | 订单管理     | 状态分段筛选 + 单步流转 / 结算 / 取消 / 打印                           |
| `/review`       | 到店复核     | 客户线上单的件数 / 面料核对：调价（留痕，等客户确认）或 "金额无误"                   |
| `/appointments` | 上门取件     | 客户预约列表 + 状态筛选（确认 / 已取件 / 取消）                           |
| `/chat`         | 员工助手     | 查经营 / 订单 / 复核 / 客户 / 洗护 / 价目；写操作先出「待确认动作卡」             |
| `/pickup`       | 取衣结算     | 可取衣列表、逾期高亮、结算详情弹窗                                      |
| `/members`      | 会员管理     | 等级与折扣展示、新增 / 编辑 / 删除、**为老客户开通网店账号**（客户不能自助认领）          |
| `/inventory`    | 耗材库存     | 库存总值、低库存预警、入库 / 出库                                     |
| `/finance`      | 经营报表     | 日报、区间统计、服务排行、收支流水登记                                    |
| `/metrics`      | Agent 指标 | 两端调用量 / 错误率 / P50・P95・最大耗时 / 平均轮次 / 工具调用数 + 最近 20 条坏例子 |

### 客户端（客户本人）



| 路径             | 页面        | 说明                                                   |
| -------------- | --------- | ---------------------------------------------------- |
| `/me/login`    | 客户登录 / 注册 | 手机号 + 密码；老客户手机号自动关联历史订单                              |
| `/me`          | 我的首页      | 在店件数、可取衣、待付款、累计消费、会员卡（等级 / 积分 / 折扣 / 升级还差多少）、最近一单进度条 |
| `/me/orders`   | 我的订单      | 状态筛选 + 行内展开明细（件数、单价、折扣、已付 / 待付、来源徽标、门店调价待确认）         |
| `/me/book`     | 线上点单      | 左侧预约上门取件，右侧直接下单（实时试算，可勾选 "顺便预约" 合成一张预约）              |
| `/me/chat`     | 洗衣助手      | 查自己订单进度 / 金额 / 等级，问洗护问题（带依据），查价目表                    |
| `/me/messages` | 消息中心      | 门店调价待确认、可取衣、预约变化；导航有未读红点，一键全部已读                      |

## 权限模型（v3）

三层，每层都比上一层更严：



| 层 | 依赖                 | 作用                                                   |
| - | ------------------ | ---------------------------------------------------- |
| 1 | `get_current_user` | 解析 Bearer Token，只判断 "有没有登录"；无 token / 签名错 / 过期统统 401 |
| 2 | `require_staff`    | 挂在 6 个管理路由上，`admin` / `staff` 可进；客户账号一律 403          |
| 3 | `require_customer` | 客户端接口专用，返回绑定的 `Customer` 档案；员工账号 403                 |

两条硬规则：



1. **客户端接口的签名里没有手机号 / 客户 ID 参数**。身份只来自 token 里的 `customer_id`，所以 "传别人手机号查别人订单" 这件事在能力上就不存在，不依赖提示词或前端自觉。

2. **跨客户访问返回 404 而不是 403**。403 会告诉攻击者 "这单存在，只是不给你看"，404 什么都不泄露。

v5 又补了两条：



1. **老客户不能自助认领账号**。手机号在 `customers` 表里已有档案时，自助注册直接 409（"请让门店在后台帮你开通"），只有全新手机号能自助注册；门店用 `POST /api/customers/{id}/bind-account` 开通（校验手机号与档案一致）。否则任何人拿别人手机号注册就能看到对方订单。

2. **员工注册要邀请码**。`POST /api/register` 必须带 `invite_code` 并与 `LAUNDRY_STAFF_INVITE_CODE` 比对；不配置就直接 403 关掉公开注册。正规做法是管理员用 `POST /api/staff/users`（`require_admin`）在后台建号。

配套的验证：`tests/permission_test.py` 55 项，覆盖未登录、伪造 / 篡改 / 过期 token、两个登录口互不通用、客户打管理端接口 403 且响应里不含他人姓名手机号、员工打客户端接口 403、跨客户查询 404、传 `phone` / `customer_id` 参数无效、注册冲突 409。

## 上门取件为什么拆两层单（v4）

预约和洗衣单是两种东西，硬塞进一张表会出现 "取件时间" 和 "取衣时间" 打架、金额算不清：



|      | 预约单 `appointments`                                 | 洗衣单 `orders`                                           |
| ---- | -------------------------------------------------- | ------------------------------------------------------ |
| 谁建   | 客户预约 / 客户下单时顺带勾选                                   | 到店收衣（或客户线上下单预生成）                                       |
| 关键字段 | `appt_no` / `expected_time` / `address` / `status` | `order_no` / `items_detail` / `total_price` / `status` |
| 状态   | 待确认 → 已确认 → 已取件 / 已取消                              | 待洗涤 → 洗涤中 → 可取衣 → 已完成 / 已取消                            |
| 关系   | 一张预约可关联多张洗衣单（`orders.appointment_id`）              |                                                        |

规则：预约时间不能早于现在、不能超过 14 天、地址必填、同一客户同时进行中（待确认 / 已确认）的预约最多 3 个（超了 409）。

## 线上点单与到店复核（v4）

客户能自己下单，但**金额以到店复核为准**—— 这是防止 "客户少报件数" 的关键：



1. 客户端下单时金额仍由 `pricing_service.quote` 服务端算（不信任前端），`review_status = pending`

2. 师傅到店点件，实际件数 / 面料不一致就在 `/review` 页调价，写 `order_amount_logs` 留痕（旧金额、新金额、原因、经手人），状态置 `adjusted`

3. 客户在 `/me/orders` 行内看到「门店调价，待你确认」，点「确认新金额」才算同意（`confirm_amount` 只认本人）

4. 金额没变就走 "金额无误"（`approve_amount`），直接置 `confirmed`

调价接口三条硬约束：必须是 `pending`/`adjusted` 状态、新金额必须真的变了、原因必填且 ≤300 字。

## 双端 Agent（v4）

同一个模型客户端，两套工具白名单，靠 "工具里根本没有那个能力" 防越权：



|      | 客户端 Agent                   | 员工 Agent                                                                                                                                                              |
| ---- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 入口   | `POST /api/my/chat`         | `POST /api/staff/chat`                                                                                                                                                |
| 工具数  | 5 个只读                       | 7 个只读 + 3 个 propose 写                                                                                                                                                 |
| 身份注入 | `ToolContext(db, customer)` | `_Ctx(db, user)`                                                                                                                                                      |
| 查别人  | **签名里没有手机号 / 客户 ID**，能力上不存在 | 员工本来就能查全店，但写操作必须二次确认                                                                                                                                                  |
| 写操作  | 不支持                         | `propose_create_order` / `propose_change_status` / `propose_complete_order` 只暂存动作卡（`ACTION_STORE`，TTL 600 秒，按 `staff_id` 隔离），员工点「确认执行」带 `confirm_action_id` 再来一次才真正落库 |

洗护问答一律走 `care_rules` 结构化知识库（10 条，都有 `GB/T`、`FZ/T` 规范出处）；查不到就返回固定拒答话术，不让模型自由发挥。

**评估集**（`scripts/eval_cases.json` 37 条：客户 25 / 员工 12）：



```
python scripts/eval_agent.py                 # 桩模式：只验证评估器与链路，37/37
python scripts/eval_agent.py --live         # 真模型（慢，一条 15 秒起）
python scripts/eval_agent.py --live --ids c11,c19 --show   # 只跑指定用例并打印回答
```

指标：用例通过、工具命中率、越权拒绝率、**禁忌工具调用次数**、禁忌表述命中次数。

`must_contain` 判定为 "任一命中"—— 模型措辞不固定（"不可水洗 / 别水洗 / 不能水洗" 都得分）。

**两个引擎**（默认手写循环，`AGENT_ENGINE=langgraph` 换 LangGraph）：两条路共用同一份 `SYSTEM_PROMPT` / `TOOL_SPECS` / `run_tool`，`tests/langgraph_test.py` 20 项按住 "行为一致" 这条线（轮次、工具列表、收口话术必须相同）。

写 LangGraph 版本时踩到的真坑：`route` 里必须先判轮次上限、再判有没有待执行工具调用，否则 "模型只调工具不给答案" 会绕成 `GraphRecursionError`。

## v5 安全加固：五条会被人当场问穿的硬伤

这五条都不是 "风格问题"，是拿演示账号走一遍就能发现的洞，现在每条都有测试按住。



| # | 原来的漏洞                                                         | 现在怎么做                                                                                                                       | 测试                        |
| - | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| 1 | 师傅把金额从 ¥70 调到 ¥105，客户没点确认，订单照样能 "结算拿走 ¥105"——"客户确认才作数" 只是师傅自觉 | `complete_order` 前置校验：`review_status` 是 `pending` 或 `adjusted` 一律 409，报文分别提示 "请先到店复核" 和 "或等客户点确认新金额"                        | `hardening_test.py` 前 6 条 |
| 2 | `POST /api/register` 谁都能注册，顺手就能进管理端                           | 必须带 `invite_code` 且与 `LAUNDRY_STAFF_INVITE_CODE` 一致；没配邀请码直接 403 关闭公开注册。另给管理员 `POST /api/staff/users`（`require_admin`）后台建号   | 员工注册三态 + 管理员建号 + 客户不能建号   |
| 3 | 客户拿别人手机号自助注册，自动关联到对方历史档案，直接看到别人订单                             | 老档案手机号自助注册一律 409；门店调 `POST /api/customers/{id}/bind-account` 开通（手机号与档案必须一致）                                                 | 老档案不能认领 + 新号可注册           |
| 4 | `SECRET_KEY` 写死在代码里，仓库一公开所有 token 可伪造                         | `LAUNDRY_ENV=production` 没给 `LAUNDRY_SECRET_KEY` 直接 `RuntimeError` 拒绝启动；dev 每次启动 `secrets.token_hex(32)` 随机生成（旧 token 重启失效） | 密钥非默认值 + 长度 ≥ 32          |
| 5 | 取消订单只改状态不记账，删除订单把流水一起删了，财务对不上                                 | 取消按 `paid_amount` 写一条负数 `refund` 红冲；删除改成软删（`is_deleted=1` + `status=cancelled`），`order_items` / `transactions` 一行不动         | 红冲金额 -10 + 软删后行仍在         |

软删之后所有查询（`_require_order`、订单列表、客户订单列表、客户摘要、待复核、逾期）都加了 `is_deleted == 0` 过滤，所以 "删了" 对用户是消失，对财务是留痕。

## v5 站内消息：让 "待确认" 有人看见

调价不确认就结算不了，但如果客户从没看到那条调价，单子就卡在那 —— 所以三处状态变化都推一条站内消息：



| 触发点         | 类型               | 内容                   |
| ----------- | ---------------- | -------------------- |
| 师傅调价        | `price_adjusted` | 原价 → 新价 + 原因，请到订单页确认 |
| 状态变 `ready` | `ready`          | 件数 + 待付金额，可来取衣       |
| 取消订单        | `cancelled`      | 已取消 + 若已付款会退多少       |
| 预约状态变化      | `appointment`    | 已确认 / 已取件            |

客户端 `/me/messages` 列表 + 导航红点（`meRefreshBadge()` 在每次 `meGuard` 后拉未读数），`POST /api/my/notifications/read` 不传 ids 就是全部已读。

## v5 库存与订单挂钩：洗完扣耗材，但绝不卡住客户

`complete_order` 里按 `sum(items.quantity) × INVENTORY_PER_PIECE` 从「洗涤耗材」扣减，写一条 `inventory_usages` 流水（订单号、件数、扣了多少）。

**库存不足不报错**—— 衣服已经洗完了，不能因为记账没库存就让客户拿不走衣服。返回体里给 `inventory: {item_name, pieces, need, deducted, short, left}`，前端和老板能看到 "这次欠了多少"。

## v5 登录限流

`login_guard` 是进程内存实现（10 次失败 / 5 分钟窗口 → 锁 5 分钟，返回 **429**），两个登录口都接，登录成功即复位。

选择内存而不是 Redis 的原因见 ADR-5：单进程部署下这才是对的复杂度；多进程要换存储，代码位置只有一处。

## v5 Agent 指标：回答 "你的 Agent 多快、多贵、错多少"

每轮对话落一条 `agent_metrics`（端、引擎、问题、轮次、工具、耗时、是否报错），`GET /api/staff/metrics?days=` 汇总两端：



```
calls / errors / error_rate / avg_ms / p50_ms / p95_ms / max_ms / avg_rounds / tool_calls + 最近 20 条
```

数据侧由 `/metrics` 页面消费（管理端导航「指标」）。客户账号打这个接口是 403。

## v5 压测：自己的数字，不引用别人的

`scripts/load_test.py` 用线程 + httpx 直接压五个接口（不引 locust，少一个依赖）：



```
python scripts/load_test.py --base-url http://127.0.0.1:7778 --users 20 --iters 25
```

本机（Windows / Python 3.13 / SQLite /uvicorn 单进程）实测：**20 并发、2500 请求、0 错误，整体 76.2 QPS，平均 260 ms**



| 接口                   | P50 | P95 | P99 | 最大  |
| -------------------- | --- | --- | --- | --- |
| `POST /api/login`    | 449 | 568 | 646 | 727 |
| `GET /api/orders`    | 344 | 541 | 653 | 700 |
| `GET /api/stats`     | 155 | 244 | 298 | 419 |
| `GET /api/my/orders` | 197 | 318 | 391 | 434 |
| `POST /api/my/quote` | 123 | 213 | 274 | 332 |

登录最慢是 bcrypt 的固有成本（故意调高，不是 bug）；瓶颈在 SQLite 单写者，换 PostgreSQL 后这条曲线才有意义。

## v5 工程化：Docker + CI 门禁



```
# 本机（Docker）
$env:LAUNDRY_SECRET_KEY="一个至少32字符的随机串"; docker compose up --build
# 直接跑镜像
docker build -t laundry-management . && docker run -p 8000:8000 -e LAUNDRY_SECRET_KEY=xxx laundry-management
```



* `Dockerfile`：`python:3.13-slim`，`LAUNDRY_ENV=production`，**单 worker**（原因见 ADR-5：`ACTION_STORE` 是进程内存）

* `docker-compose.yml`：数据卷 `/data`、健康检查打 `/api/health`、`LAUNDRY_SECRET_KEY` 不填直接起不来

* `.github/workflows/ci.yml`：先 `python tests/run_all.py`（7 套 320 项）→ 再跑评估集 → 再 `docker build` 起容器打健康检查

本地没装 Docker，所以镜像构建这一步只在 CI 里验证过配置、没有本机实测记录 —— 这条写在 `docs/architecture-decisions.md` 的 "已知未验证" 里，不假装跑过。

## 业务规则（v2.1 新增）

**订单五态**（`app/config.py` 的 `STATUS_TRANSITIONS` 约束，非法流转返回 409）



```
received（待洗涤）─► washing（洗涤中）─► ready（可取衣）─► completed（已完成）
        └────────────────┴───────────────┴──► cancelled（已取消）
```

**计价在服务端**，单价一律查 `service_items` 价目表，不信任前端传来的金额：



```
明细行 → 单价 × 数量 = 小计 → 汇总折前金额 → × 会员折扣率 = 应收
```



* `POST /api/orders` 若前端传了 `total_price`，与后端计算差 ≥ 0.01 直接拒绝（400）

* `POST /api/orders/quote` 只试算不落库，前端边填边算，提交时后端再算一次

* 定金不得大于应收，否则 400

**会员折扣**（`MEMBER_DISCOUNT`）



| 等级   | 0 普通客户 | 1 普通会员 | 2 银卡会员 | 3 金卡会员 | 4 钻石会员 |
| ---- | ------ | ------ | ------ | ------ | ------ |
| 折扣   | 100%   | 95%    | 90%    | 85%    | 80%    |
| 门槛积分 | 0      | 100    | 300    | 800    | 1500   |

结算时按 1 元 = 1 积分累计，等级只升不降；订单落库时快照等级与折扣率，事后改等级不影响历史单。

**逾期**：`GET /api/orders/overdue` 返回「未完成且预约取衣时间已过」的订单，首页与取衣页同步展示。

## 主要接口



| 方法                  | 路径                                           | 说明                                         |
| ------------------- | -------------------------------------------- | ------------------------------------------ |
| POST                | `/api/login`                                 | 登录，返回 `{success, token, user}`             |
| POST                | `/api/register`                              | 注册员工账号                                     |
| POST                | `/api/orders/quote`                          | **试算**：传明细，返回折前 / 折扣率 / 应收（不落库）            |
| POST                | `/api/orders`                                | 收衣建单（`items_detail` 结构化明细，或兼容旧 `items` 文本） |
| GET                 | `/api/orders?status=&keyword=&limit=`        | 订单列表（状态 / 订单号 / 姓名 / 手机号）                  |
| GET                 | `/api/orders/{id}`                           | 订单详情，含结构化明细 `items_detail`                 |
| POST                | `/api/orders/{id}/status`                    | **状态流转**（按允许表校验）                           |
| POST                | `/api/orders/{id}/complete`                  | 取衣结算（幂等，重复调用 409）                          |
| POST                | `/api/orders/{id}/cancel`                    | 取消订单                                       |
| GET                 | `/api/orders/overdue`                        | **逾期未取**                                   |
| DELETE              | `/api/orders/{id}`                           | 删除订单（已完成订单禁止删除）                            |
| GET/POST/PUT/DELETE | `/api/customers`、`/api/members`              | 会员增删改查                                     |
| GET/POST            | `/api/categories`、`/api/services`            | 衣物分类、服务项目                                  |
| GET                 | `/api/stats`                                 | 看板（今日订单 / 在店 / 可取衣 / 逾期 / 今日与累计收支）         |
| GET                 | `/api/stats/trend?days=N`                    | **近 N 日趋势**（订单量 + 收入）                      |
| GET                 | `/api/stats/daily?date=`                     | 日报                                         |
| GET                 | `/api/stats/range?start_date=&end_date=`     | 区间报表（含客单价）                                 |
| GET                 | `/api/stats/services`                        | 服务项目排行（件数 / 金额）                            |
| GET/POST            | `/api/transactions`                          | 财务流水（收入 / 支出）                              |
| GET/POST            | `/api/inventory`、`/inventory/{id}/in`、`/out` | 库存出入库、低库存预警                                |
| GET                 | `/api/logs`                                  | 操作日志                                       |
| GET                 | `/api/health`                                | 健康检查（免鉴权）                                  |

**客户端接口（**`require_customer`**，只返回本人数据）**



| 方法         | 路径                                          | 说明                                                     |
| ---------- | ------------------------------------------- | ------------------------------------------------------ |
| POST       | `/api/customer/register`                    | 客户注册（**v5：只有全新手机号能注册**；老档案 409，需门店开通）                  |
| POST       | `/api/customer/login`                       | 客户登录                                                   |
| GET        | `/api/my/profile`                           | 我的等级 / 积分 / 折扣 / 距下一等级还差多少                             |
| GET        | `/api/my/summary`                           | 在店件数、可取衣、待付款、累计消费、最近一单                                 |
| GET        | `/api/my/orders?status=&limit=`             | 我的订单列表（按状态筛选）                                          |
| GET        | `/api/my/orders/{id}`                       | 我的某一单明细（他人的单返回 404）                                    |
| POST       | `/api/my/chat`                              | 和我的洗衣助手对话（只读工具 + 出处，返回 answer /tools\_used/trace）      |
| GET/DELETE | `/api/my/chat/history`                      | 我的对话历史（会话持久化到 `chat_messages`，可按会话清空）                  |
| GET        | `/api/my/options`                           | 下单页选项：分类 / 服务价目 / 可查面料 / 本人折扣                          |
| POST       | `/api/my/quote`                             | 下单前试算（仍走服务端计价）                                         |
| POST       | `/api/my/orders`                            | 线上点单（`review_status=pending`，可带 `appointment_id` 关联预约） |
| POST       | `/api/my/orders/{id}/confirm-amount`        | 确认门店调价后的新金额（只认本人，非 `adjusted` 状态 409）                  |
| GET/POST   | `/api/my/appointments`                      | 我的预约列表 / 新建预约                                          |
| GET        | `/api/my/notifications?limit=&unread_only=` | **v5** 我的站内消息（返回 `{success, data, unread}`）            |
| POST       | `/api/my/notifications/read`                | **v5** 标记已读（body `{}` 全部已读，或 `{"ids":[..]}`）           |

**员工（**`require_staff`**，v4 新增）**



| 方法         | 路径                                 | 说明                                                    |
| ---------- | ---------------------------------- | ----------------------------------------------------- |
| GET        | `/api/orders/review-pending`       | 待复核（`pending` / `adjusted`）订单列表                       |
| POST       | `/api/orders/{id}/adjust`          | 调价（写 `order_amount_logs` 留痕，等客户确认）                    |
| POST       | `/api/orders/{id}/approve`         | 金额无误，直接确认                                             |
| GET        | `/api/appointments?status=&limit=` | 全部预约（可筛状态）                                            |
| PATCH      | `/api/appointments/{id}`           | 预约状态流转（确认 / 已取件 / 取消）                                 |
| POST       | `/api/staff/chat`                  | 员工助手对话（可带 `confirm_action_id` 执行动作卡，返回含 `elapsed_ms`） |
| GET/DELETE | `/api/staff/chat/history`          | 员工对话历史                                                |
| POST       | `/api/staff/users`                 | **v5** 管理员后台建员工号（`require_admin`，客户 / 普通员工 403）       |
| GET        | `/api/staff/metrics?days=`         | **v5** Agent 指标汇总（调用量 / 错误率 / P50・P95 / 轮次 / 工具数）     |
| GET        | `/api/customers/{id}/account`      | **v5** 查该档案是否已开通网店账号                                  |
| POST       | `/api/customers/{id}/bind-account` | **v5** 门店为老客户开通账号（手机号与档案不一致 400；已绑定 409）              |

除 `/api/health`、`/api/login`、`/api/register`、`/api/customer/login`、`/api/customer/register` 外，

所有接口都需要 `Authorization: Bearer <token>`，缺失或失效返回 401；角色不符返回 403。

错误码约定：校验类问题（金额不合法、定金超应收、明细为空、服务不存在）→ **400**；

真冲突（重复结算、已完成单被改、手机号重复、非法状态流转）→ **409**；不存在 → **404**。

所有错误响应都同时带 `error` 与 `message` 两个字段，前端与 Agent 都能统一解析。

## v1 修复的关键问题



1. **重复结算重复记账** —— 原实现只要 `status == 'completed'` 就无条件写流水。现在校验状态并返回 409，收入按 "已收金额" 补差。

2. **订单号秒级冲突** —— 原 `O{年月日时分秒}` 同秒必撞 UNIQUE，改为毫秒 + 4 位随机并带唯一性轮询。

3. **登录前后端契约不一致** —— 前端读 `data.success/data.user`，后端返回扁平对象，登录永远失败。现已返回 `{success, token, user}`。

4. **密码明文 + 接口零鉴权** —— bcrypt 哈希（历史明文首次登录自动升级），全接口 JWT 鉴权。

5. **魔法下标取字段** —— `order[11] if len(order) > 11` 全部换成 ORM 属性访问。

6. **积分体系从未生效** —— 结算时按 1 元 = 1 积分累计并自动升级（只升不降）。

7. **衣物明细是自由文本** —— 新增 `order_items`，解析成结构化行，历史 8 单已回填。

8. **库存与支出是死表** —— 补齐 CRUD、出入库与支出记账。

9. `expected_pickup`**&#x20;从未写入** —— 建单接口支持预约取衣时间。

## 关于接入 Agent（已铺好的前提）

`app/services/` 里每个函数都 **接收&#x20;**`db`**&#x20;+ 简单参数、返回可 JSON 序列化的 dict**，

所以同一份逻辑两种用法：



```
# 1) HTTP 层：routers/orders.py -> order_service.create_order(...)

# 2) Agent 工具直接调用（不走网络）
from app.db import SessionLocal
from app.services import order_service, pricing_service

db = SessionLocal()

# 试算（模型先问"要收多少钱"）
pricing_service.quote(db, [{"category": "外套", "service_name": "干洗", "quantity": 2}], "111")

# 建单（结构化明细，金额由后端算）
order_service.create_order(db, "张三", "13900001111",
                          items_detail=[{"category": "外套", "service_name": "干洗", "quantity": 2}],
                          deposit=0, pay_now=True)
```

客户端 Agent 已经落地（`app/agent/`），工具白名单是 "只有只读、且查不到别人"：



| 工具                      | 参数             | 说明                          |
| ----------------------- | -------------- | --------------------------- |
| `query_my_orders`       | status / limit | 本人订单列表                      |
| `query_my_order_detail` | order\_no      | 本人某一单明细（他人的单返回 found=false） |
| `query_my_account`      | —              | 等级、折扣、积分、待付、累计消费            |
| `query_care_rule`       | fabric         | 洗护规则（含禁忌与出处），未命中走拒答话术       |
| `query_price_list`      | —              | 门店价目表                       |

**所有工具签名里都没有手机号 /customer\_id**，身份由服务端从 token 取出后注入，

所以 "查别人的单" 不是被拦住，而是没有这个能力。写操作类工具留给管理端 Agent（四期）。

## 测试



```
python tests/run_all.py           # 一次跑完 7 套，共 320 项（CI 用这条）
python tests/run_all.py --eval    # 顺带跑评估集桩模式 80/80

python tests/smoke_test.py        # 65 项业务闭环，自动拷到 %TEMP%\laundry_smoke.db 运行，不动 laundry.db
python tests/permission_test.py   # 55 项权限/越权，独立临时库
python tests/hardening_test.py    # 43 项加固（P0 五条 + 消息 / 库存 / 限流 / 指标 / 密钥）
python tests/agent_test.py        # 41 项 Agent（模型打桩，秒出结果）
$env:AGENT_LIVE="1"; python tests/agent_test.py   # 44 项，会真实调用模型（约 1~2 分钟）
python scripts/verify_data.py     # 数据完整性 + 明细统计验收
```

当前基线：**smoke 65 /permission 55 /agent 41 /phase3 59 /staff\_agent 37 /langgraph 20 /hardening 43 = 320 项全绿**，评估集桩模式 80/80。

加固测试覆盖：未确认调价不能结算（pending /adjusted 两种报文）、确认后按 105 结算、库存按件扣减并留 `inventory_usages` 流水、取消写 -10 红冲、软删后列表消失但库里行还在、删除后详情 404、员工注册三态（无码 / 错码 / 对码）、管理员建号、客户不能建号、老档案不能认领、纯数字密码被拒、登录限流 429 与复位、三类站内消息 + 未读清零、Agent 指标落库与 P95 字段、客户看指标 403、密钥非默认且 ≥32、`/me/messages` 可打开。

冒烟测试覆盖：鉴权与错误码、会员折扣试算、金额篡改拦截、旧文本入参兼容、

五态流转与非法流转拦截、幂等结算、积分累计、逾期判定、状态筛选、库存出入库与超量拦截、

财务流水、报表、8 个页面渲染与全部静态资源。

权限测试覆盖：未登录 / 伪造签名 / 过期 token、客户注册与老档案绑定、重复注册 409、

两个登录口互不通用、客户访问 7 个管理接口 403 且响应不含他人信息、客户不能建单与结算、

员工访问客户端接口 403、跨客户查订单 404、`phone` / `customer_id` 参数注入无效、

摘要金额口径与列表一致、客户端页面与静态资源可访问。

Agent 测试覆盖：知识库命中 / 别名命中 / 未收录拒答、工具返回不含手机号、跨客户查询不回显他人信息、

塞 `phone` 参数只得到参数错误、未知工具拦截、一次多工具并行、只调工具不给答案时按轮次上限收口、

诱导查他人时仍只返回本人数据、员工打对话接口 403、空消息 422、页面与脚本可访问。

## 数据迁移



```
python scripts/migrate_v2.py       # 幂等：加 3 个字段、pending→ready、折前金额回填
python scripts/migrate_v3.py       # 幂等：users 加 customer_id 列 + 唯一索引
python scripts/migrate_v4.py       # 幂等：订单来源/复核字段 + appointments 等 3 张表
python scripts/migrate_v5.py       # 幂等：orders.is_deleted + notifications / agent_metrics / inventory_usages
python scripts/migrate_v6.py       # 幂等：agent_metrics.question（指标看板要回看坏例子）
python scripts/seed_care_rules.py  # 幂等：洗护知识库 10 条规则（新表，create_all 会自动建）
```

升级前快照：`C:\keshe3\laundry_backup_20261107_184935.db`（v2 前）、

`laundry_backup_v3_20261107_2050.db`（v3 前）、`laundry_backup_v4_20261107_2320.db`（v4 前）、

`laundry_backup_v5_*.db` / `laundry_backup_v6_*.db`（v5/v6 前，脚本自己生成）。

两条踩过的坑：



* SQLite 不支持 `ALTER TABLE ADD COLUMN ... UNIQUE`，唯一约束只能走 `CREATE UNIQUE INDEX`。

* `create_all` 只建缺失表、不改已有表，所以改既有表必须写迁移脚本（v5 的 `is_deleted` 就是这么来的）。