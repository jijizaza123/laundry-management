# 一期进度（客户账号 + 权限地基）

> 2026-11-07 开工，当日收工时的状态。下次接着做直接看本文最后一节「恢复指引」。

## 这一期做了什么

| # | 事项 | 状态 | 落点 |
|---|---|---|---|
| 1 | 数据库快照 | 完成 | `C:\keshe3\laundry_backup_v3_20261107_2050.db`（65536 字节） |
| 2 | `users` 加 `customer_id`（可空、唯一、外键 customers） | 完成 | `app/models.py` |
| 3 | 迁移脚本（ALTER TABLE + 唯一索引，幂等） | 完成 | `scripts/migrate_v3.py` |
| 4 | token 带 `cid`（客户身份唯一来源） | 完成 | `app/security.py` → `create_access_token(user_id, role, customer_id=None)` |
| 5 | 三层权限依赖 | 完成 | `app/deps.py` → `get_current_user` / `require_staff` / `require_customer` |
| 6 | 客户注册/登录（手机号即账号，自动绑定老档案） | 完成 | `app/services/auth_service.py`、`app/routers/auth.py` |
| 7 | 6 个管理路由挂 `require_staff` | 完成 | orders / customers / catalog / stats / inventory（5 个 router + auth 里禁止客户走管理端登录口） |
| 8 | 客户端 4 个只读接口 | 完成 | `app/routers/me.py`、`order_service` 新增 3 个按 `customer_id` 过滤的函数 |
| 9 | 客户端页面 | 完成 | `templates/me_login.html`、`me.html`、`me_orders.html`、`base_me.html`、`static/css/me.css`、`static/js/me_*.js` |
| 10 | 越权测试 | 完成 | `tests/permission_test.py` 52 项 |
| 11 | 回归 | 完成 | 冒烟 65 / 65 + 权限 52 / 52，全绿 |

## 权限设计（这期唯一不能妥协的部分）

三层，逐层收紧：

```
无 token / 签名错 / 过期  → 401   （get_current_user）
角色不是 admin/staff      → 403   （require_staff，挂在管理路由上）
角色不是 customer         → 403   （require_customer，挂在 /api/my/* 上）
订单不属于本人            → 404   （get_order_of_customer 里判 customer_id）
```

两条刻意的选择：

1. **客户端接口签名里不出现手机号 / 客户 ID**。`/api/my/orders` 就是无参接口，身份只从 token 的 `cid` 取。这样"传别人手机号查别人单"在能力上不可能，不靠提示词、不靠前端自觉，也不会因为以后接 Agent 就破防。
2. **跨客户访问返回 404，不是 403**。403 等于告诉对方"这单存在，只是不给你看"；404 什么都不说。测试里专门断言 404 的响应体不含对方订单号和手机号。

另有一个前端兜底：客户账号误开到管理端页面，`initShell` 会把人送回 `/me`，避免看到一屏 403 报错。

## 验证记录（都是真跑出来的）

- `python tests/smoke_test.py` → 通过 65 / 65（原有业务闭环全部没被打断）
- `python tests/permission_test.py` → 通过 52 / 52
- 真服务 + 浏览器实测（服务指向 `%TEMP%\laundry_ui.db` 副本，没动主库）：
  - 用老客户手机号 `123456` 注册 → 自动绑定 `lk` 档案 → 首页直接显示历史 4 单
  - `/me` 显示：在店 2、可取衣 1、待付款 ¥215.00、累计消费 ¥35.00、再消费 100 元升级
  - `/me/orders` 状态筛选正常；点「明细」行内展开，件数/单价/折扣/已付/待付都对
  - 客户 token 打开 `/` → 被送回 `/me`（这个第一次没生效，是浏览器缓存了旧 `app.js`，清缓存后确认生效）
  - 管理员 `admin/admin123` 登录 `/login` → 看板正常（今日收衣 3、在店 5、可取衣 3）

## 踩到并修掉的坑

1. `deps.py` 里函数名写成了 `get_current_customer`，`me.py` 导入 `require_customer` → 启动 ImportError。已统一命名。
2. 模板里删掉了 `id="levelName"`，`me.js` 还在写它 → 渲染到一半抛 TypeError，导致概览卡片全是 `-`、订单一直「加载中」。已删掉这行引用。
3. 折扣文案 `100% 折` 语义错（看着像打一折）→ 改成"原价消费，暂无折扣"/"享 9.5 折"。
4. 模板用了不存在的 `modal-box` 类（设计系统里叫 `modal-panel`）。同时发现这个自动化浏览器截图里固定层（fixed + 遮罩）压根不落图，于是直接改成**行内展开明细**，不用弹窗——移动端体验反而更好，也免得评测时截图看不出效果。
5. `api.js` 里 `/me` 前缀判断会把 `/members` 也当成客户端页 → 改成正则 `^\/me(\/|$)`。

## 没做 / 留给下一期

| 事项 | 归属 | 备注 |
|---|---|---|
| `appointment` 预约表 + `orders.source` / `appointment_id` | 三期 | 上门取件两层单，方案已定 |
| 线上点单 + 到店复核链路（`original_amount` 快照、差异日志、客户确认） | 三期 | 方案第 6 节 |
| `care_rules` 洗护知识库 + 出处 + 拒答 | 三期 | 方案第 6 节 |
| 客户端 Agent（4 个只读工具 + 图循环） | 二期 | 一期只把数据接口备好，Agent 还没接 |
| 管理端 Agent（9 个工具，3 个写，人工确认） | 四期 | — |
| 评估集（35 条语料 + 越权诱导用例） | 四期 | — |
| 预约取衣提醒 / 短信 / 支付 | 不做 | 方案「明确不做」清单 |

## 恢复指引（下次开工）

```powershell
cd C:\keshe3\laundry_management

# 1) 确认改造后的库结构没问题（幂等，跑一次就行）
python scripts\migrate_v3.py

# 2) 跑回归，确认起点是绿的
python tests\smoke_test.py
python tests\permission_test.py

# 3) 起服务看页面
python run.py 7777
# 管理端 http://127.0.0.1:7777/login  admin/admin123
# 客户端 http://127.0.0.1:7777/me/login  手机号 123456 / pass1234（这号是 UI 实测时在测试库里建的，
#   主库 laundry.db 里还没有客户账号，需要重新注册一遍）
```

下一期建议顺序：`care_rules` 表 + 客户端 Agent（先把 4 个只读工具挂上，跑通「模型调工具 → 拿结果 → 再补一轮」的循环），再做上门取件。

密钥在 `.env`（已在 `.gitignore` 里）。模型用 `agnes-3.0-flash`，实测 `agnes-2.5-pro-beta` 返回 404 不能用。
