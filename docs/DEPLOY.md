# 部署指南

生产架构:PostgreSQL(Docker)+ Go 后端(systemd 原生)+ nginx 反代 + React 静态站。Python 引擎由 Go 后端按计划触发。

> 以下为通用步骤,请把 `<...>` 替换成你自己的值。密钥只放 `server/.env`,绝不入库。

## 1. 前置

服务器(Linux,建议 Ubuntu 22.04+,≥4GB 内存):
- Docker(跑 PostgreSQL,也可用系统自带 PG)
- Go 1.22+、Node 18+、Python 3.10+(装 `pandas numpy pyarrow requests baostock akshare`)
- nginx

## 2. 数据库(Docker PostgreSQL)

```bash
docker run -d --name sentinel-postgres -p 5432:5432 \
  -e POSTGRES_USER=sentinel -e POSTGRES_PASSWORD=<db-password> -e POSTGRES_DB=sentinel \
  -v sentinel-pgdata:/var/lib/postgresql/data postgres:16
```

## 3. 拉代码 + 配置

```bash
git clone <your-repo-url> sentinel && cd sentinel
cp server/.env.example server/.env
# 编辑 server/.env:
#   SENTINEL_DB_DSN=host=localhost port=5432 user=sentinel password=<db-password> dbname=sentinel sslmode=disable
#   SENTINEL_JWT_SECRET=$(openssl rand -hex 32)
#   SENTINEL_PYTHON=/path/to/python(装了引擎依赖的解释器)
#   SENTINEL_DATA_DIR=/path/to/data(引擎数据目录)
#   其余按需(DeepSeek/tushare/MinIO 可选)
```

## 4. 生成数据

数据不随仓库分发,首次需拉取(默认到 `engine/data`,或 `SENTINEL_DATA_DIR`):
```bash
cd engine
python lib/download_daily.py                                   # A股日线(baostock)
export SENTINEL_TS_URL=https://api.tushare.pro SENTINEL_TS_TOKEN=<token>
python ts_refresh.py --full                                    # A股另类数据(tushare)
```

## 5. 构建

```bash
# 后端二进制(带版本号;分支名决定版本)
cd server
go build -ldflags "-X sentinel/internal/version.Injected=$(git rev-parse --abbrev-ref HEAD)|$(git rev-parse --short HEAD)|$(git rev-parse --abbrev-ref HEAD)" -o sentinel-server ./cmd/server
# 前端静态站
cd ../client && npm install && npm run build          # 产出 client/dist
```

## 6. systemd 服务(后端)

`/etc/systemd/system/sentinel.service`:
```ini
[Unit]
Description=Sentinel backend
After=network.target docker.service

[Service]
WorkingDirectory=/path/to/sentinel/server
ExecStart=/path/to/sentinel/server/sentinel-server
EnvironmentFile=/path/to/sentinel/server/.env
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
systemctl daemon-reload && systemctl enable --now sentinel
journalctl -u sentinel -f          # 看启动日志(应显示「迁移完成」+ 版本号)
```
后端启动会自动应用数据库迁移;调度器每 N 小时自动刷新数据 + 跑引擎 + ingest(间隔可在系统管理页调整)。

## 7. nginx(前端静态 + API 反代)

`/etc/nginx/sites-available/sentinel`:
```nginx
server {
    listen 80;
    server_name <your-domain>;
    root /path/to/sentinel/client/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / {
        try_files $uri /index.html;   # SPA 路由
    }
}
```
```bash
ln -s /etc/nginx/sites-available/sentinel /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```
建议配 HTTPS(Let's Encrypt / certbot)。

## 8. 创建管理员

首次用管理员邮箱登录(`SENTINEL_ADMIN_EMAIL`)。**请设置强密码**,不要用默认/弱密码。

## 更新发布

重新 `go build`(带 ldflags 版本号)+ `npm run build`,替换二进制与 `client/dist`,`systemctl restart sentinel`。新迁移在重启时自动应用。

## 安全提醒

- 生产管理员用强密码;`.env` 权限 600、仅 root 可读。
- 数据库、对象存储不要暴露公网端口。
- 第三方数据代理(非官方 tushare/baostock)自担可用性与合规风险;生产建议用官方数据源。
