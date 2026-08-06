# 发布规则 —— 开发分支 → 公开开源仓

> 本文件是**内部维护记录**,记录如何把开发成果发布到公开 GitHub 仓,以及**绝不能泄露的红线**。

## 两个仓 / 分支的关系

| | 位置 | 内容 | 是否公开 |
|---|---|---|---|
| **开发分支** `feature/v*` | 仅本地(无远程) | 完整开发代码 + 历史,**可能含服务器信息、弱口令默认值、内部文档** | ❌ 绝不推任何远程 |
| **发布分支** `public` | 本地 + `origin/main` | 清理过的开源版:无密钥、无服务器地址、`.gitignore` 屏蔽敏感文件 | ✅ 公开 |
| **远程** `origin` | `github.com/Lugia123/sentinel` | = `public` 分支 | ✅ 公开仓 |

**`origin` 是公开仓。`git push origin <开发分支>` 会永久泄露(公开仓会被缓存/索引,不可撤销)。**

## 🔴 红线(绝不做)

1. **绝不** `git push origin feature/*` 或任何开发分支 → 公开仓。
2. **绝不**把这些推上公开仓:服务器 IP/域名、管理员账号密码、API token(tushare/DeepSeek/MinIO/JWT)、`/Users/...` 硬编码路径、`.env`、`.claude/`、`server/mcp`、`.mcp.json`、内部状态文档。
3. 凭据只存在服务器 `server/.env`(600 权限)与本地 `.claude/`,**永不入库**。

## ✅ 正确发布流程(把新功能发到公开仓)

新功能在开发分支 `feature/vX.Y` 上开发、提交(提交本身要保持干净——别在功能提交里夹带密钥)。发布时:

```bash
# 1. 从干净的 public 切出发布工作分支
git checkout public
git checkout -b release/vX.Y

# 2. 只把「干净的功能提交」cherry-pick 过来(不是整分支照搬!)
#    这样会自动叠加到 public 已清理的基线上,保留清理成果(如 config/main 的默认值、ts_refresh 路径)
git cherry-pick <功能提交1> <功能提交2> ...

# 3. 发布前四道安全核验(必须全部为空/通过)
git grep -nI "64\.90\.31\.28\|bestfunc\|admin123\|xugf" -- .        # 服务器/弱口令
git grep -nIE "[0-9a-f]{32}" -- . | grep -v example                  # token
git grep -nI "/Users/" -- .                                          # 硬编码路径
git ls-files | grep -iE "\.claude/|\.mcp\.json|server/mcp|\.env$"     # 敏感文件被跟踪?

# 4. 编译验证
(cd server && go build ./...) && (cd client && npx tsc --noEmit)

# 5. 看清将发布的完整清单(只应有目标功能)
git diff --name-status origin/main release/vX.Y

# 6. 快进 public 并推公开仓
git checkout public && git merge --ff-only release/vX.Y
git push origin public:main

# 7. 回开发分支,删临时分支
git checkout feature/vX.Y && git branch -D release/vX.Y
```

## 为什么用 cherry-pick 而不是 merge/照搬

`public` 是**孤儿分支**(与开发分支无共同祖先),且开发分支保留着开源时清理掉的东西
(`.claude/`、`config.go`/`main.go` 的 `bestfunc`/`admin123` 默认、`ts_refresh.py` 的 `/Users` 默认路径等)。
cherry-pick 只搬「功能提交的 diff」,叠加到 public 已清理的基线上 → **清理成果与新功能两全**,
且功能提交若没碰被清理的那几行,就不会把脏东西带过去。

## 本地开发仓的卫生

开发分支的 `.gitignore` 已屏蔽 `.claude/ .mcp.json server/mcp docs/mcp.md docs/status-v1.5.md`,
并已 `git rm --cached` 取消跟踪(文件留在磁盘,只是不再入库)。
注:历史提交里仍有旧副本——因开发分支**只在本地、绝不推远程**,不改写历史即可;
真正的防线是「只 cherry-pick 干净功能提交到 public」。

## 历史发布

- **v2.4**(2026-08):cherry-pick 6 个功能提交(数据源告警 · 未来20日收益范围 · 全局涨跌配色 P0 ·
  个股资金流卡 P1 · 板块资金热力 P2 · 大盘北向 P3)→ `origin/main` `8203a1d..49b438b`。核验四项全过。
