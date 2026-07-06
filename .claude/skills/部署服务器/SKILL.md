---
name: 部署服务器
description: 把 Sentinel 部署/更新到生产服务器(雨云 64.90.31.28 / f.bestfunc.com,Ubuntu 4核4GB)。基础服务(PostgreSQL/MinIO)跑 Docker,应用(Go后端+nginx+React)原生跑,Python 引擎用"路径镜像"复用本地硬编码路径。当用户要"部署""上线""更新服务器""发布新版本"时使用。
---

# /部署服务器 — Sentinel 生产部署与更新

把本地 Sentinel 部署或更新到生产服务器。**首次部署**看 §3;**日常更新(最常用)**直接看 §2。

## 0. 服务器与访问
- **服务器**:`64.90.31.28`(雨云/RainYun,**国内**机,Ubuntu 22.04,4核 3.8GB,95G 盘)
- **域名**:`f.bestfunc.com` → 64.90.31.28(自签 SSL)
- **访问**:`https://f.bestfunc.com`(浏览器有一次自签警告,继续即可)
- **SSH**:`ssh sentinel`(免密,密钥 `~/.ssh/sentinel_deploy`;别名已在 `~/.ssh/config`)
- **管理员**:`xugf@bestfunc.com` / `admin123`(⚠️ 弱密码,建议尽快改)
- **凭据**:全在服务器 `/Users/lugia/lugia_fc/sentinel/server/.env`(600 权限,含 DB/MinIO/JWT/DeepSeek);**绝不回显、不入库、不进 git**

## 1. 架构(什么跑在哪)
```
https://f.bestfunc.com
      │  nginx(443 自签SSL / 80→443)   /etc/nginx/sites-available/sentinel
      ├── /            → React 静态  /Users/lugia/lugia_fc/sentinel/client/dist
      └── /api/        → 127.0.0.1:8787
                            │  Go 后端(systemd: sentinel)  静态二进制
                            ├── PostgreSQL  Docker sentinel-pg  127.0.0.1:5433
                            ├── MinIO       Docker sentinel-minio 127.0.0.1:9000
                            └── Python 引擎  venv + 路径镜像(见 §4)
```
- **基础服务 Docker**:`/opt/sentinel/deploy/docker-compose.yml`(pg + minio,只绑 127.0.0.1 不公网)
- **应用原生**:Go 二进制交叉编译上传;nginx 反代;React 静态
- **应用根目录**:服务器上 `/Users/lugia/lugia_fc/sentinel`(**镜像本地路径**,让引擎硬编码路径能解析)

## 2. 日常更新(最常用)⭐
改完代码、本地测好后,按改了什么选对应步骤。所有 ssh 命令**放慢节奏,别密集重连**(见 §5 坑4)。

### 后端(Go)改动
```bash
cd /Users/lugia/lugia_fc/sentinel/server
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o /tmp/sentinel-server ./cmd/server
scp -i ~/.ssh/sentinel_deploy /tmp/sentinel-server root@64.90.31.28:/Users/lugia/lugia_fc/sentinel/server/
ssh sentinel 'systemctl restart sentinel && sleep 3 && systemctl is-active sentinel && journalctl -u sentinel -n 8 --no-pager'
```

### 前端(React)改动
```bash
cd /Users/lugia/lugia_fc/sentinel/client && npm run build
rsync -a -e "ssh -i ~/.ssh/sentinel_deploy" client/dist/ root@64.90.31.28:/Users/lugia/lugia_fc/sentinel/client/dist/
# nginx 直接服务静态,无需重启;刷新浏览器即可(可能要 Ctrl+Shift+R 清缓存)
```
> 注意:从 sentinel 根跑 rsync 时路径是 `client/dist/`;上面 cd 到 client 了,改成 `dist/ root@...:.../client/dist/`。

### 引擎(Python)改动
```bash
cd /Users/lugia/lugia_fc/sentinel
rsync -a -e "ssh -i ~/.ssh/sentinel_deploy" --exclude __pycache__ --exclude data --exclude data_cache \
  engine/ root@64.90.31.28:/Users/lugia/lugia_fc/sentinel/engine/
# 引擎是 subprocess,后端不用重启;下次调用即新代码。改了依赖才需 pip install(见 §4)
```

### 新增数据库迁移
把新 `server/migrations/000X_*.sql` scp 到服务器 `server/migrations/`,`systemctl restart sentinel` 即自动按序应用(schema_migrations 跟踪,幂等)。

### 快速验证(更新后必做)
```bash
AT=$(curl -sk -X POST https://f.bestfunc.com/api/auth/login -H 'Content-Type: application/json' -d '{"email":"xugf@bestfunc.com","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sk -H "Authorization: Bearer $AT" https://f.bestfunc.com/api/snapshot | python3 -c "import sys,json;d=json.load(sys.stdin);print('asof',d['asof'],'持仓',len(d['holdings']))"
```

## 3. 首次部署(全新服务器)
按序执行。**关键坑见 §5,务必先读。**

1. **SSH 密钥**:`ssh-keygen -t ed25519 -f ~/.ssh/sentinel_deploy`;`sshpass -f <pwfile> ssh-copy-id -i ...pub root@IP`;写 `~/.ssh/config` 别名。
2. **装 Docker**:`ssh sentinel 'curl -fsSL https://get.docker.com | sh && systemctl enable --now docker'`(**先等初始更新完,见坑1**)。
3. **起 PG+MinIO**:创建 `/opt/sentinel/deploy/docker-compose.yml`(pg16 + minio,随机强密码,绑 127.0.0.1),`docker compose up -d`。建 bucket:`docker run --rm --network host --entrypoint sh minio/mc -c "mc alias set local http://127.0.0.1:9000 minioadmin <pw> && mc mb -p local/sentinel"`。
4. **迁移数据库**:本地 `docker exec bestfunc-postgres pg_dump -U bestfunc -d sentinel --no-owner --no-acl | gzip > db.sql.gz`;scp;`gunzip -c db.sql.gz | docker exec -i sentinel-pg psql -U sentinel -d sentinel`。
5. **Go 后端**:交叉编译(§2)→ scp → 建 `/Users/lugia/lugia_fc/sentinel/{server/migrations,client,data,engine}` → 写 `server/.env`(§6)→ systemd 单元 `/etc/systemd/system/sentinel.service`(WorkingDirectory=server 目录,findRoot 靠"含 engine 子目录"定位根)→ `systemctl enable --now sentinel`。
6. **React**:`npm run build` → scp `dist/`。
7. **nginx + 自签 SSL + 域名**:见 §7。
8. **Python 引擎**:见 §4(rsync ~800MB 数据 + venv + 装依赖)。
9. **收尾**:改管理员邮箱/密码(§8)。

## 4. Python 引擎部署(路径镜像法)
引擎依赖研究仓的库+数据,全是硬编码 `/Users/lugia/lugia_fc/...` 绝对路径。**不改代码,而是在 Linux 上重建相同绝对路径**放文件——最省事最稳。

**要 rsync 的路径(源→服务器同路径,~800MB)**:
- `safna_jr/round12/lib`、`round22/groupB`、`round24/groupB`(库,~1MB,`--exclude __pycache__`)
- `safna_jr/round20/data_broad`(324M,1393 CSV;`engine/data` 符号链接指向它)
- `safna_jr/round16/groupA/data/raw_secfacts`(449M,基本面 JSON)
- `safna_jr/动量哨兵研究/round8/data`(21M,98池)
- `safna_jr/动量哨兵研究/round2/data/SPY.csv`
- `sentinel/engine/`(.py + strategies,`--exclude data --exclude __pycache__ --exclude data_cache`);之后 `ln -sfn .../round20/data_broad engine/data`

**venv + 依赖**(用清华源):
```bash
ssh sentinel 'apt-get install -y python3.10-venv python3-pip
V=/Users/lugia/lugia_fc/sentinel/engine/.venv; python3 -m venv $V
$V/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pandas numpy asyncpg requests'
```
`.env` 里 `SENTINEL_PYTHON` 指向 `$V/bin/python`。测试:`$V/bin/python focus.py NVDA --asof latest`。
> 内存已优化(focus ~113M / run_daily ~739M,见引擎 `_load_lite`),4GB 够跑重算+并发加自定义股。

## 5. 踩过的坑(务必知道)
1. **全新机首次开机跑 unattended-upgrades**(~50min,升级 250 个系统包含内核,**占着 apt 锁**)。装任何包前先等它完:`while pgrep -x unattended-upgr && ! fuser /var/lib/dpkg/lock-frontend; do :; done`——但注意常驻的 `unattended-upgrade-shutdown --wait-for-signal` 也匹配 `unattended-upgr` 却**不占锁**,别被它误导,以 `fuser /var/lib/dpkg/lock-frontend` 和 dpkg.log 最后修改时间为准。
2. **needrestart 装包后自动重启 openssh → 踢掉你的 SSH**。先禁:`echo '$nrconf{restart}="l";' > /etc/needrestart/conf.d/no-restart.conf`。装包一律 **detached**(`nohup ... &` + 轮询日志),断连不影响。
3. **国内机用国内源**:apt 已是清华源;pip 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
4. **别密集重连 SSH**:短时间多次 ssh 会撞 sshd `MaxStartups`,报 `kex_exchange_identification: Connection closed by remote host`,像宕机其实没事。**间隔 ≥30s 温和重试**即可恢复,不用重启服务器。
5. **端口**:80/443 首次可能需在雨云面板放行/绑域名;本例 80/443 直接可达。

## 6. server/.env 模板(生产)
```
SENTINEL_PORT=8787
SENTINEL_DB_DSN=host=127.0.0.1 port=5433 user=sentinel password=<PG随机> dbname=sentinel sslmode=disable
SENTINEL_DEEPSEEK_KEY=<key>
SENTINEL_DEEPSEEK_BASE=https://api.deepseek.com
SENTINEL_DEEPSEEK_MODEL=deepseek-chat
SENTINEL_MINIO_ENDPOINT=127.0.0.1:9000
SENTINEL_MINIO_KEY=minioadmin
SENTINEL_MINIO_SECRET=<MinIO随机>
SENTINEL_MINIO_BUCKET=sentinel
SENTINEL_DATA=/Users/lugia/lugia_fc/sentinel/data
SENTINEL_ENGINE=/Users/lugia/lugia_fc/sentinel/engine
SENTINEL_PYTHON=/Users/lugia/lugia_fc/sentinel/engine/.venv/bin/python
SENTINEL_CAPITAL=4000
SENTINEL_SCHEDULE=05:30
SENTINEL_JWT_SECRET=<openssl rand -hex 32>
SENTINEL_ADMIN_EMAIL=xugf@bestfunc.com
```

## 7. nginx + 自签证书 + 域名
```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 730 \
  -keyout /etc/nginx/ssl/sentinel.key -out /etc/nginx/ssl/sentinel.crt \
  -subj "/CN=f.bestfunc.com" -addext "subjectAltName=DNS:f.bestfunc.com,IP:64.90.31.28"
# 站点:80 default_server → 301 https;443 ssl default_server,server_name f.bestfunc.com _;
#   root=client/dist;location /api/ proxy_pass 127.0.0.1:8787(proxy_read_timeout 300s 给AI留时间);location / try_files $uri /index.html
nginx -t && systemctl reload nginx
```
换域名:改证书 `CN`/`subjectAltName` + 站点 `server_name`,reload。

## 8. 改管理员账号
- **改邮箱**:`docker exec sentinel-pg psql -U sentinel -d sentinel -c "UPDATE users SET email='新@邮箱' WHERE role='admin';"`(EnsureAdmin 只在零用户时 seed,改名安全)。
- **改密码**:登录后前端「修改密码」,或重置。

## 红线
- 密钥只在服务器 `server/.env`(600),**绝不回显/入库/进 git**;rsync 传代码时 `--exclude .env`。
- 自签证书浏览器会警告,正常;生产要正规证书可换 Let's Encrypt(域名已就绪)。
- 数据计算类改动上线前本地交叉验证;免责声明"研究工具,非投资建议"保留。
