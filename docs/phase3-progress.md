# 三期 / 四期 + 可选项进度（v4）

> 一句话：这一轮把"两边都能登录、各自看到不同东西"升级成**两边都能办事**——
> 客户能预约上门、能自己下单、能看到师傅复核后的金额并确认；
> 员工有复核工作台、预约管理、以及一个"写操作必须我点确认才执行"的助手。

## 一、这一轮补的是什么

一期只解决了"客户能只读地看自己的单"，二期解决了"客户能问洗护问题"。缺的是**闭环**：

| 缺口 | 原来的状态 | 现在 |
|---|---|---|
| 客户想下单 | 只能到店 | `/me/book` 线上点单，实时试算，可顺手约上门取件 |
| 上门取件 | 没有 | 预约单 + 洗衣单两层，订单 `appointment_id` 关联 |
| 客户少报件数怎么办 | —— | 到店复核：调价留痕 + 客户手机上确认，不确认不算数 |
| 员工查东西要翻好几页 | 手工点页面 | `/chat` 员工助手，一句话查经营/订单/复核 |
| 员工让助手"改一笔" | —— | 助手只出「动作卡」，员工点确认才写库 |
| 换 Agent 图框架 | 手写 while 循环 | `AGENT_ENGINE=langgraph` 一键切换，行为对齐有测试按住 |
| 对话记录 | 刷新就没了 | 落库到 `chat_messages`，按 `customer:{id}` / `staff:{id}` 分会话 |

## 二、数据库改动（`scripts/migrate_v4.py`，已执行）

订单表加 3 列：

- `source`：`staff`（到店收衣）/ `online`（客户线上下单）
- `appointment_id`：关联预约单
- `review_status`：`confirmed`（金额已确认）/ `pending`（待到店复核）/ `adjusted`（门店调价，待客户确认）

新增 3 张表：

- `appointments`：预约单（`appt_no` 唯一、`expected_time`、`address`、`note`、`status`、`staff_id`）
- `order_amount_logs`：调价留痕（`old_total`、`new_total`、`reason`、`staff_id`、`customer_confirmed`）
- `chat_messages`：对话持久化（`session_key`、`role`、`content`、`tools_used`）

迁移前的备份：`C:\keshe3\laundry_backup_v4_20261107_2320.db`。
迁移脚本幂等（先查列/表是否存在），重复执行不会报错也不会重复加。
主库迁移后实况：订单 11、线上单 0、待复核 0、三张新表 0 行、`care_rules` 10 条 —— **测试全程在 `%TEMP%` 副本上跑，主库没被污染**。

## 三、状态机与校验（容易漏的地方）

**预约**：`pending`（待确认）→ `confirmed`（已确认）→ `completed`（已取件）；`pending` / `confirmed` 都能 → `cancelled`。
建预约校验四条：时间不能早于现在、不能超 14 天、地址必填 ≤200 字、同一客户进行中最多 3 个（超了 409）。

**金额复核**：

- 线上下单 → `review_status = pending`，前端显示「待到店复核」
- 师傅调价 `adjust_amount`：必须 `pending`/`adjusted`、新金额必须真的变了、原因必填 ≤300 字 → `adjusted`
- 师傅"金额无误" `approve_amount`：金额不变，直接 `confirmed`
- 客户确认 `confirm_amount`：只认本人（别人的单 404），必须 `adjusted` 才能确认 → `confirmed`

## 四、Agent 的两条红线

1. **工具签名里不出现手机号**（客户端）：`query_my_orders(ctx, limit)` 这种形状，第一参是 `ToolContext(db, customer)`，身份从 token 走 `require_customer` 注入。模型被诱导去查别人，最多只能拿到本人数据；塞 `phone="147258"` 会被 `run_tool` 的 `TypeError` 捕获成"参数不正确"。
2. **写操作两段式**（员工）：`propose_*` 只往 `ACTION_STORE` 里放动作卡（TTL 600 秒、按 `staff_id` 隔离、执行即弹出，不能重复执行），真正的 `create_order` / `change_status` / `complete_order` 只在员工带 `confirm_action_id` 再来一次时执行。

## 五、测试

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/phase3_test.py` | 59 | 预约两层单、线上点单与计价、调价复核与确认、HTTP 权限、页面资源 |
| `tests/staff_agent_test.py` | 37 | 员工工具层、两段式写操作、图循环打桩、HTTP 权限、页面资源 |
| `tests/langgraph_test.py` | 20 | 手写循环 vs LangGraph 行为一致、轮次上限、越权诱导、模型报错 |
| 回归 | 65 + 52 + 41 | `smoke_test` / `permission_test` / `agent_test` 全绿 |

全部都在 `%TEMP%` 的数据库副本上跑（`shutil.copy` + `LAUNDRY_DATABASE_URL`），不碰 `laundry.db`。

**评估集**（`scripts/eval_cases.json` 37 条）：桩模式 37/37；真模型抽查 c06 / c11 / c19 / s01 / s09 全 PASS；LangGraph 引擎下 c11 / c19 也 PASS。
真模型实测耗时很不稳定（plain 42 秒、带工具 15 秒、有一次 >75 秒），所以配了 `AGENT_TIMEOUT=90` + 超时重试一次。

## 六、这一轮修掉的真 bug（都出在"界面看起来没问题"的地方）

1. **工具结果被截断成非法 JSON**：`json.dumps(...)[:1500]` 在中文 + ASCII 转义下只装得下约 8 条订单，模型拿到的是半截 JSON → 找不到订单。改成 `[:4000]`。
2. **`STATUS_META` 重复声明**：`chat.html` / `review.html` / `appointments.html` 的 `scripts` 块又加载了一次 `api.js` / `app.js`（`base.html` 已经加载过），控制台报 `Identifier 'STATUS_META' has already been declared`，页面脚本直接不执行。改成只加载自己的页面脚本。
3. **下单页一进来就有两行空明细**：`addRow()` 在 `loadOptions()` 之前被调了一次，第一行是空下拉框，试算请求把空服务名发给后端 → 400。改成 options 加载完再渲染首行，`collectRows` 还加了 `service_name` 兜底过滤。
4. **员工助手回车不发送**：`textarea` 里按 Enter 不会提交表单，也没有 keydown 处理。补了 Enter → `requestSubmit()`（Shift+Enter 换行）。
5. **执行结果把 JSON 糊到聊天框**：「已执行：{"executed": ...}」这种。改成 `_describe_executed()` 说人话：「已执行：订单 O… 状态改为「可取衣」。」
6. **LangGraph 死循环**：`route` 里先判"有没有待执行工具调用"、后判轮次上限，模型只调工具不给答案时会绕成 `GraphRecursionError`。改成先判上限。

## 七、UI 验收（截图在 `docs/screenshots/`）

| 截图 | 覆盖的路径 |
|---|---|
| `me_book.png` | 客户端线上点单：左侧预约卡片（待到店确认）、右侧下单表单 + 实时试算 ¥35.00 |
| `me_confirm_amount.png` | `/me/orders` 行内展开：步骤条、来源"线上下单"、金额状态"门店调价，待你确认"、调价原因、确认按钮 |
| `admin_review.png` | 管理端到店复核：待复核 1 条，行内调价输入 + 原因 + 「调价 / 金额无误」 |
| `admin_appointments.png` | 管理端上门取件：预约号 / 客户 / 上门时间 / 地址 / 备注 / 状态 / 确认预约 + 取消 |
| `admin_chat.png` | 员工助手：问"今天收了几件"→ 工具答 4 件、在店 7 件、可取 3 件、收入 118 元 |
| `admin_chat_action.png` | 员工助手写操作：动作卡（待确认动作）→ 点「确认执行」→ 人话结果 |

实测走过的完整链路：客户端登录 → `/me/book` 填单提交 → `/me/orders` 看到「待到店复核」→ 展开看到调价框 → 点确认 → 徽标消失；管理端 `admin/admin123` → `/review` 看到待复核 → `/appointments` 看到预约 → `/chat` 问经营、出动作卡、点确认真的改了订单状态。
「勾选顺便预约」这条路径按前端同样的两次请求（`POST /api/my/appointments` → `POST /api/my/orders` 带 `appointment_id`）验证通过：预约 `A2026110722020374000`、订单 `O202611072202037555657`、`review_status=待到店复核`、`source=客户端下单`。

## 八、怎么跑

```bash
# 迁移（已经跑过，新库不用）
python scripts/migrate_v4.py

# 洗护知识库（已经灌过，幂等）
python scripts/seed_care_rules.py

# 起服务
python run.py 7777

# 测试（全部在临时库副本上跑）
python tests/smoke_test.py
python tests/permission_test.py
python tests/agent_test.py
python tests/phase3_test.py
python tests/staff_agent_test.py
python tests/langgraph_test.py

# 评估
python scripts/eval_agent.py
python scripts/eval_agent.py --live --ids c11,c19 --show
```

UI 实测建议用临时库副本，别拿主库造数：

```powershell
Copy-Item laundry.db "$env:TEMP\laundry_ui4.db"
$env:LAUNDRY_DATABASE_URL = "sqlite:///$($env:TEMP\laundry_ui4.db -replace '\\','/')"
python run.py 7777
```

## 九、明确没做（别误会）

- 没有支付/退款，只有"已付 / 待付"记账
- 没有短信/推送，预约状态变化不会通知客户（客户自己刷新页面）
- 预约"已取件"不会自动建洗衣单，师傅回 `/receive` 手工收衣（业务上确实要现场点件）
- 员工 Agent 没有"删单"工具（故意不给，删除是不可逆操作）
- 评估集只到 37 条，真模型全量跑一遍很慢（一条 15 秒起），目前是抽查 + 桩模式全量

## 十、下一步能做什么

1. 预约 → 收衣一键带出（点"已取件"时把预约地址/件数预填到收衣页）
2. 评估集扩到 80 条，加"多轮追问"和"含糊提问"类型
3. 把 `ACTION_STORE` 从内存换成表（重启不丢动作卡）
4. 员工助手加"批量改状态"（仍走两段式，一次确认执行一批）

---

# v5 加固（P0 五条 + P1 四项 + P2 三项）

上一轮结束时这个系统"能演示"，但按反驳视角看有五个洞是**拿演示账号走一遍就能发现的**。这一轮就是补这五个洞 + 工程化。

## 十一、五条硬伤，逐条对上

| # | 漏洞（改造前真的能复现） | 改法 | 按住的测试 |
|---|---|---|---|
| 1 | 调价 ¥70→¥105，客户没确认，`washing→ready→complete` 仍结算 ¥105 | `complete_order` 前置校验 `review_status`，`pending`/`adjusted` 抛 409，报文按状态区分 | `hardening_test.py` 6 条 |
| 2 | `POST /api/register` 任何人可注册员工，直接进管理端 | 必须 `invite_code` 且与 `LAUNDRY_STAFF_INVITE_CODE` 一致；未配置 → 403 关闭；另开 `POST /api/staff/users`（`require_admin`） | 三态 + 建号 + 客户不能建号 |
| 3 | 客户拿别人手机号注册即认领对方历史档案 | 老档案自助注册 409；门店 `bind-account` 开通（手机号必须与档案一致） | 老档案不能认领 + 新号可注册 |
| 4 | `SECRET_KEY` 硬编码在仓库里 | `production` 缺 `LAUNDRY_SECRET_KEY` 拒绝启动；dev 每次启动随机 32 字节 | 非默认值 + 长度 ≥32 |
| 5 | 取消不记账、删除连流水一起删 | 取消写负数 `refund` 红冲；删除改软删（`is_deleted=1`），明细与流水不动 | 红冲 -10 + 软删后行仍在 |

第 5 条带出的连锁改动：`_require_order` / `list_orders` / `list_orders_of_customer` / `customer_summary` /
`get_order_of_customer` / `list_review_pending` / `overdue_orders` 全部补 `is_deleted == 0`，否则"删了还在列表里"。

## 十二、P1 四项

- **站内消息** `notification_service`：调价 `price_adjusted`、可取衣 `ready`、取消 `cancelled`、预约 `appointment`；
  客户端 `/me/messages` + 导航红点（`meRefreshBadge()` 在 `meGuard` 末尾拉未读数）。
- **库存按件扣减** `inventory_service.consume_for_order`：`件数 × INVENTORY_PER_PIECE` 扣「洗涤耗材」并写
  `inventory_usages`；**不足不阻塞结算**（衣服已经洗完，不能因为记账让客户拿不走），返回体给
  `{need, deducted, short, left}`。
- **登录限流** `login_guard`：10 次失败 / 5 分钟 → 锁 5 分钟，两个登录口都接，成功即复位，锁定时 429。
- **Agent 指标** `metric_service`：每轮落 `agent_metrics`（端、引擎、问题、轮次、工具、耗时、是否报错），
  `GET /api/staff/metrics` 出 `calls/errors/error_rate/avg_ms/p50/p95/max/avg_rounds/tool_calls` + 最近 20 条；
  管理端 `/metrics` 页面消费；客户打这个接口 403。

## 十三、P2 三项

- **压测**：`scripts/load_test.py`（线程 + httpx，不引 locust）。本机 20 并发 × 25 轮 = 2500 请求，
  0 错误、整体 **76.2 QPS**、平均 260 ms；登录 P95 568 ms（bcrypt 固有成本），`/api/stats` P95 244 ms。
- **指标看板**：数据侧 `metric_service`，展示侧 `/metrics` 页面（两端汇总 + 最近 20 条坏例子）。
- **架构决策记录**：`docs/architecture-decisions.md`，8 条 ADR（单体分层 / 两层单 / 复核确认 / 不让自助认领 /
  内存动作卡 / 软删红冲 / 轮询消息 / 临时库测试）+ 一张"已知未验证"表。

## 十四、评估集 80 条

从 37 条扩到 **80 条（客户 50 / 员工 30）**，11 个 category 不变但每条都有同义改写和边界样本：

- 订单查询 5 条同义问法（"洗到哪一步 / 什么状态 / 取了吗 / 还在店里吗 / 什么时候能取"）
- 账户 5 条（积分差额、折扣、累计消费、未付单数、等级）
- 价目 4 条（单品价格、服务对比、服务是否存在、按项目问价）
- 洗护 6 条 + 拒答 2 条（未收录面料必须走"没查到"话术，不许模型自由发挥）
- 越权诱导 3 条（"那个人的欠款 / 我朋友的积分 / 把张三的单改成已完成"）
- 员工侧：经营查询 4、订单 3、客户 2、复核 2、洗护 2、价目 2、写操作 3（含"先别执行"）

桩模式 **80/80**、工具命中 66/66、越权拒绝 10/10、禁忌工具 0、禁忌表述 0。
扩量时同步扩了 `eval_agent.py` 的规则桩（`rule_choice` 加了同义触发词），否则新问法会落到默认分支而误判。

## 十五、这一轮踩到的坑

1. `/api/orders*` 返回体是**扁平**的（`{**data, "message": ...}`），`/api/my/*` 才是 `{success, data}`；
   `hardening_test.py` 因此两次 `KeyError: 'data'`，最后用 `body = r.json()` + `get("data", body)` 兜底。
2. `Edit` 工具的老坑又复现：`old_string` 末尾带换行、`new_string` 不带，会把下一行（`if keyword:`）吞掉，
   留下 `stmt = ...` 紧跟缩进块 → SyntaxError。
3. `me_messages.html` 用的 `.badge-warn / .badge-ok / .badge-info / .badge-muted / .badge-dot / .msg-item`
   在 `app.css` 里一个都不存在（只有 `badge-received/washing/ready/completed/cancelled/danger`），
   已补进 `static/css/me.css` 末尾。
4. `scripts/eval_agent.py` 原来"临时库不存在才拷贝"，表结构演进后复用了旧副本，
   报 `no such column: orders.is_deleted`；改成每次强制重拷。
5. `load_test.py` 起服务必须用临时库 + 先给客户开账号，否则 `/api/my/*` 全 401，压出来全是"登录失败"的假数字。
6. `api.get()` 返回的是 `{ok, status, data}` 包装对象，**服务端的 `{success, data}` 还在 `res.data` 里面**。
   `me_messages.js` / `metrics.js` 都写成 `res.data` 当数组/对象用，结果页面显示"还没有消息 / undefined ~ undefined"，
   但导航红点却有数字——典型的"一个请求成功、一个页面空白"。改成 `res.data.data` 后正常。
7. 弹窗截图：`.modal` 是 `position: fixed` + `backdrop-filter`，自动化截图里整层不落图（DOM 里 `display:flex`、
   面板 `520×331` 都在）。要么临时把 `position` 改 static 再截，要么用 DOM 尺寸证明它渲染了——不要看到截图空白就以为功能坏了。

## 十六、v5 怎么跑

```bash
python scripts/migrate_v5.py      # is_deleted + 3 张新表 + 3 个索引 + 洗涤耗材条目（幂等）
python scripts/migrate_v6.py      # agent_metrics.question（指标看板看坏例子）
python tests/run_all.py --eval    # 7 套 320 项 + 评估 80/80
python scripts/load_test.py --base-url http://127.0.0.1:7778 --users 20 --iters 25   # 压测
```

## 十七、v5 之后还差的（诚实清单）

| 缺什么 | 影响 | 补的成本 |
|---|---|---|
| Docker 镜像本机未验证 | 交付时只能说"CI 配置就绪"，不能说"我跑过" | 装 Docker Desktop 后 `docker compose up --build`，10 分钟 |
| `ACTION_STORE` / `login_guard` 进程内存 | 只能单 worker，扩不了 | 换表或 Redis，动 `staff_tools.py` 一个模块 + 重跑 37 条四期测试 |
| 真模型评估只抽样 | 80 条只用桩模式跑全量 | Agnes 15~75 秒/条，全量 20 分钟以上，可接受但不是 CI 门禁 |
| SQLite 单写者 | 76 QPS 上限 | 换 PostgreSQL，改 `db.py` + 迁移脚本重跑 |
| 主库「洗涤耗材」库存为 0 | 演示结算时走 `short` 分支（`deducted=0`，不报错） | 管理端 `/inventory` 入库一次即可 |
