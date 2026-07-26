# Sentinel v1.5 状态(用户/权限 + 数据隔离)

分支 `feature/v1.5-auth`(基于 v1.4)。加入多用户鉴权、系统管理、邮件、数据隔离。**研究工具,非投资建议。**

## 交付

### 用户 / 权限(参考 Tinia)
- **登录页**:账号=邮箱 + 密码;忘记密码 → 邮件找回;URL `?reset=token` 进重置。
- **默认管理员**:首次启动种子(`SENTINEL_ADMIN_EMAIL`/`SENTINEL_ADMIN_PASSWORD`,由 env 设置(无弱默认))。
- **系统管理**(仅管理员):用户管理(列表 + 开设用户)+ 系统邮箱 SMTP(配置 + 测试发信)。
- **用户自助**:改密码;忘记密码邮箱找回。
- 技术:JWT(30天)+ bcrypt;中间件 Inject/RequireAuth/RequireAdmin;登录门(公开路径外全需登录)。
- **重算(/api/run)仅管理员**。

### 数据隔离(migration 0005)
| 数据 | 隔离? | 实现 |
|---|---|---|
| 策略推荐股(快照) | 共享 | 所有用户看同一份 |
| AI 讲解(概览/背调/财报) | ✅按用户 | explain 缓存含 user_id;背调/财报 blob key 前缀 `<uid>/` |
| 用户自定义股 | ✅按用户 | watchlist 加 user_id;快照读取时按用户合并(mergeCustomHoldings + focus_cache) |
| 我的持仓 | ✅按用户 | positions 加 user_id;Get/Save/Compute 按 uid |
| 走势·选股 | 系统股共享 | trend/tickers 来自共享快照持仓(系统股) |

- 每日运行改为**纯策略共享快照**(不再全局 append 自定义股);各用户的自定义股在 `/api/snapshot` 时按用户合并(sleeve=custom,股数0,focus 缓存于 focus_cache)。

### MCP
- 全 app 加鉴权后,MCP server 启动时以管理员登录拿 JWT,httpCall 带 Bearer → 21 工具仍可驱动。

## bug 修复
- **添加自定义股票只有大盘股**:改用 `/api/universe`(数据池全 1393 只,98 只带中文名),不再只限 ticker_meta 的 98 只。
  - 注:NIO/PLUG/RIVN/SOFI 等不在这个固定历史数据集(1393)里,仍搜不到——数据限制非 bug。

## 实测
- 未登录 401;admin/普通用户登录;普通用户重算/admin接口 403;忘记密码返回找回链接。
- 隔离:admin 关注[AAPL]、u1 空;admin 快照20(含AAPL custom)、u1 快照19(无)。
- 前端:登录门 / 系统管理(仅管理员)/ 重算仅管理员 / 用户菜单改密退出;admin 登录→20持仓含AAPL自选·追踪。
- MCP 21 工具带鉴权全通。

## 备注 / 待办
- 测试残留:默认管理员 admin@sentinel.local;测试用户 u1@test.com(张三);admin 有 AAPL 作自定义追踪演示。
- 未完全覆盖:走势页「用户自定义股」显示其个人历史(当前自定义股不进 holdings 历史表,故走势只列系统股;无泄漏,但个人自定义股暂无多日走势)。
- SMTP 未配置时忘记密码走 dev 兜底(直接返回链接);配置后自动发邮件。
- 未合并 main,等验收。
