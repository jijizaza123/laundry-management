# 部署到云服务器（Ubuntu）

目标：一台全新 Ubuntu 22.04 / 24.04，用 Docker Compose 跑起来，公网可访问；
数据落在 Docker 卷里，重启/重建容器不丢；密钥不进仓库。

> 单进程约束：Agent 的动作卡（`ACTION_STORE`）在进程内存，镜像固定 1 个 worker。
> 要横向扩，先按 `docs/architecture-decisions.md` 第 5 条把动作卡落表/落 Redis。

---

## 0. 准备

服务器上装 Docker（国内网络可用镜像源）：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo docker compose version    # 需要 v2，`docker-compose` 单独版不用
```

安全组 / 防火墙只开 `22`、`80`、`443`。**不要**把 `8000` 直接对公网裸奔，
除非你只是临时验证（下面第 4 节给反代方案）。

## 1. 拉代码

```bash
git clone https://github.com/<你的用户名>/<仓库名>.git laundry
cd laundry
```

## 2. 写 `.env`（关键，别提交）

```bash
cat > .env <<'EOF'
LAUNDRY_ENV=production
LAUNDRY_SECRET_KEY=请替换成随机值
LAUNDRY_STAFF_INVITE_CODE=
AGNES_API_KEY=请替换成你的 key
AGNES_MODEL=agnes-3.0-flash
EOF
```

生成密钥（64 位十六进制，别手打）：

```bash
openssl rand -hex 32
```

说明：
- `LAUNDRY_SECRET_KEY` 低于 32 字符或缺失 → 进程直接 `RuntimeError` 退出，这是故意的。
- `LAUNDRY_STAFF_INVITE_CODE` 留空 = 关闭员工公开注册，只能在管理端「用户」里建号。
  公网演示建议留空，否则任何人都能注册成员工。
- `.env` 已在 `.gitignore` 里；`docker compose` 会自动读取同目录 `.env` 做变量替换。

## 3. 构建并启动

```bash
sudo docker compose up -d --build
sudo docker compose ps          # 状态应为 healthy（healthcheck 打 /api/health）
sudo docker compose logs -f app
```

第一次进页面会是空的：没有价目、没有分类、没有耗材。补初始化数据：

```bash
sudo docker compose exec app python scripts/seed_demo.py
```

它会打印一次管理员密码（随机生成，替换掉 `admin123`）和演示客户账号
（`13800138000 / demo1234`）。**记下来，只显示这一次**。

已有数据的老库搬家：把 `laundry.db` 传到服务器后放进卷里，再跑 `scripts/migrate_v2.py` 到
`migrate_v6.py`（顺序不能反，v2→v6 是对旧表逐版 ALTER）。新库不需要迁移。

## 4. 反向代理 + HTTPS（有域名就走这段）

用 Caddy 最省事，自动申请证书：

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
your.domain.com {
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy
```

没有域名就先用 `http://<公网IP>:8000` 验证，但**别公开放着**——管理端能被爆破。

## 5. 验证清单（部署完照着打一遍）

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status":"ok","service":"laundry-management","version":"2.1.0"}

# 管理端能登录（用 seed 打印的密码）
curl -s -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<上面打印的>"}' | head -c 120

# 客户能登录
curl -s -X POST http://127.0.0.1:8000/api/customer/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800138000","password":"demo1234"}' | head -c 120
```

浏览器再点一遍：客户 `/me/login` 下单 → 管理端 `/review` 复核调价 → 客户 `/me/orders` 确认 →
管理端改状态到「可取衣」→ 客户 `/me/messages` 收到通知。这条链路走通，部署才算成功。

## 6. 备份与升级

```bash
# 备份（SQLite 单文件，复制前先停 5 秒最稳）
sudo docker compose stop app
sudo docker run --rm -v laundry_laundry-data:/data -v $PWD:/backup alpine \
  cp /data/laundry.db /backup/laundry_$(date +%Y%m%d_%H%M).db
sudo docker compose start app

# 升级
git pull
sudo docker compose up -d --build
```

## 常见坑

| 现象 | 原因 |
|---|---|
| 容器起来就退出，日志 `production 环境必须设置 LAUNDRY_SECRET_KEY` | `.env` 没写或太短 |
| 页面能开，点「线上点单」提示没有服务项目 | 没跑 `seed_demo.py` |
| 客户登录 401 | 老客户没在「会员」页开账号；新客户要在 `/me/login` 注册 |
| 容器 healthy 但外网打不开 | 安全组没放行端口，或反代写错了 upstream |
| 提交订单报「提交金额与明细计算结果不一致」 | 前端缓存了旧价目，强制刷新 |
| 多个 worker 后动作卡失效 | 设计限制，先落表/Redis |
