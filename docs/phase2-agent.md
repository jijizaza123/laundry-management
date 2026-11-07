# 二期进度：洗护知识库 + 客户端 Agent

> 一期（客户账号 + 权限地基）见 
>
> `phase1-progress.md`
>
> 。本文记录二期做了什么、为什么这么做、还有哪些没做。

## 一、这一期交付了什么



| # | 事项                                                        | 落点                                                                          |
| - | --------------------------------------------------------- | --------------------------------------------------------------------------- |
| 1 | `care_rules` 洗护知识库（10 条，含别名 / 水洗结论 / 建议工艺 / 禁忌 / 原因 / 出处） | `app/models.py`、`app/services/care_service.py`、`scripts/seed_care_rules.py` |
| 2 | 5 个只读工具（订单列表 / 单详情 / 账户 / 洗护规则 / 价目表）                     | `app/agent/tools.py`                                                        |
| 3 | 模型调用封装（Agnes OpenAI 兼容，超时重试）                              | `app/agent/llm.py`                                                          |
| 4 | 对话循环（手感上等价于 LangGraph 的最小图）                               | `app/agent/graph.py`                                                        |
| 5 | 接口 `POST /api/my/chat` + 页面 `/me/chat`                    | `app/routers/me.py`、`templates/me_chat.html`、`static/js/me_chat.js`         |
| 6 | Agent 测试 41 项（含打桩循环、越权、真模型可选）                             | `tests/agent_test.py`                                                       |

## 二、为什么工具签名里没有手机号



```
def query_my_orders(ctx: ToolContext, status: str | None = None, limit: int = 5)
def query_my_order_detail(ctx: ToolContext, order_no: str)
def query_my_account(ctx: ToolContext)
def query_care_rule(ctx: ToolContext, fabric: str)
def query_price_list(ctx: ToolContext)
```

`ctx` 由服务端从登录 token 里取出来的 `Customer` 构造，模型既看不到也改不了。

所以 "帮我查 147258 这个人的订单" 这类请求，即使模型想配合，也没有可用的参数 ——

实测这句话模型连工具都没调，直接回答 "我只能查您本人的记录"。

对比常见做法（`query_orders(phone: str)` + 提示词约束），这里的区别是：

**越权不是被拦住，而是压根没有这个能力**。提示词可以被绕，签名不能。

## 三、三个防幻觉的设计



1. **知识库只认命中的规则**。`query_care_rule` 未命中返回 `found=false` + 固定话术，

   系统提示词明确要求 "把 message 原样告诉用户，不要补充常识"。没把握就承认没把握。

2. **金额与时间只能引用工具返回**。提示词禁止自行换算、禁止承诺未提供的取衣时间。

3. **轮次用尽不硬编**。`AGENT_MAX_ROUNDS` 用完仍没答案，返回 "没查清，去看订单页或问师傅"。

每条回答都带出处（`GB/T 8685《纺织品 维护标签规范 符号法》` 等），

评测时可以直接核这句话是不是来自库里。

## 四、对话循环长什么样



```
messages = [system] + 历史 + 本轮问题
for round in 1..MAX_ROUNDS:
    assistant = llm(messages, tools)
    若 assistant 没有 tool_calls → 这就是答案，结束
    否则逐个执行工具 → 把结果以 role=tool 追加 → 下一轮
```

两个真实约束逼出了这个形状：



* **同一条 prompt 两次调用返回的工具数可能不同**（实测一次 2 个、一次 1 个），

  所以不能假设 "一轮把该调的都调完"，必须有 "调一个 → 拿结果 → 再补一轮" 的循环。

* **模型有时只调工具不给话**，直接返回空 content，所以要区分 "该出答案了" 和 "还要再跑一轮"。

为什么没直接上 LangGraph：目前只有 4 个节点，先用显式循环把状态、轮次上限、异常兜底写清楚；

换 LangGraph 时把 `while` 换成 `add_conditional_edges`，状态字段（messages /trace/rounds）可以原样搬。

## 五、可观测性

`/api/my/chat` 的返回里带 `trace`：每一轮做了什么、调了哪个工具、参数是什么、结果前 220 字。

前端在气泡下面显示 "查了你的订单列表・查了洗护规则库"。

出问题时不用猜是模型没调工具，还是工具查空了。

## 六、实测记录（都是真跑出来的）



| 项目                                        | 结果                                                                          |
| ----------------------------------------- | --------------------------------------------------------------------------- |
| `python tests/smoke_test.py`              | 65 / 65                                                                     |
| `python tests/permission_test.py`         | 52 / 52                                                                     |
| `python tests/agent_test.py`              | 41 / 41（模型打桩）                                                               |
| `AGENT_LIVE=1 python tests/agent_test.py` | 44 / 44（真实调用 Agnes）                                                         |
| 真实问答抽样                                    | "羊绒大衣到哪了 + 怎么护理" → 调 `query_my_orders` + `query_care_rule`，答案含订单状态、金额、禁忌、依据 |
| 越权诱导                                      | "查 147258 的订单" → 不调工具，直接说明只能查本人记录                                           |
| UI 实测                                     | `/me/chat` 点快捷问题 → 40 秒左右返回，气泡下方显示调用了哪个工具                                   |

### 踩到的坑



1. **这条模型链路很慢且不稳定**：同一天实测单次调用 15s / 42s / >75s 都出现过。

   所以默认超时提到 90 秒，并在超时后自动重试一次，仍失败才报 "稍后再问一句"。

2. `agnes-2.5-pro-beta` 返回 404 不可用（一期已记录，别换这个）。

3. 模型会输出 `**加粗**`，前端原先只转义不渲染，页面上裸露星号。

   两处一起改：提示词要求纯文本 + 前端做轻量 `**` 渲染。

4. 客户端测试库是主库副本，主库里没有客户账号，UI 测试要先注册一遍（已在实测里按此执行）。

## 七、明确没做（下一步）



| 事项                                            | 说明            |
| --------------------------------------------- | ------------- |
| `appointment` 预约表 + 上门取件两层单                   | 三期，方案第 7 节已设计 |
| 线上点单 + 到店复核（`original_amount` 快照、差异日志、客户确认差额） | 三期            |
| 管理端 Agent（9 个工具含 3 个写 + 人工确认）                 | 四期            |
| 评估集（35 条语料 + 越权诱导用例，跑分记录）                     | 四期，是简历上最能讲的部分 |
| 会话持久化（现在历史存在前端内存，刷新就没了）                       | 可选            |
| 换成 LangGraph（带 checkpointer 的多轮记忆）            | 可选，结构已对齐      |

## 八、恢复指引



```
cd C:\keshe3\laundry_management

python scripts\seed_care_rules.py     # 幂等，重跑只会覆盖同 fabric 的规则
python tests\smoke_test.py            # 65
python tests\permission_test.py       # 52
python tests\agent_test.py            # 41（不打真模型，秒出结果）
$env:AGENT_LIVE="1"; python tests\agent_test.py   # 44（会调真模型，约 1~2 分钟）

python run.py 7777
# 客户端 http://127.0.0.1:7777/me/chat（先注册一个手机号；主库还没有客户账号）
```

`.env` 里必须有 `AGNES_API_KEY`，没有的话 Agent 会直接提示 "还没配置模型密钥" 而不是崩掉。