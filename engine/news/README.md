# news_lab — Sentinel A股新闻系统

27 轮研究(R1-R27)的产物。完整日志见 `docs/news-PROGRESS.md`,规划见 `docs/news-research-plan.md`。

## 一句话结论
**新闻的价值在信息层(L1)与解释层(L2)与风险层,不在可交易信号层(L3)。**
15 轮严格回测(R13-R25)证明:A股新闻**无强可交易 alpha**——看似的边际扣掉可交易性/前视/右尾后几乎全蒸发,
4 次撞到 SAFNA-A 的"松关联=噪声、信号计入摩擦即消失"。证伪本身是最重要的产出。

## 交付(按层)

### L1 信息层(确定价值,已交付)
- `news_collector.py` — 采集(东财全球快讯/新浪/同花顺/央视/个股新闻/公告),去重、白名单。
- `news_global.py` + `transmission.py` — GDELT 全球一手源 + 全球→A股传导映射(17主题,lead/lag)。
- `news_daily.py` — 每日金融要闻日报(分级→聚合→AI合成,含全球传导段)。
- `news_calendar.py` — 财报/前瞻事件日历。

### L2 解释层(确定价值,已交付)
- `news_link.py` — 实体链接(新闻→个股,业绩预告认领)。
- `news_profile.py` + `news_keywords.py` — 个股关联画像 + AI 累计叙事关键词。
- `news_classify.py` — 金融影响分级器(temp=0 自洽100%)。

### 风险/关注层(诚实定位,R27)
- `news_signals.py` — 个股信号旗:attention(预增关注)/avoid_risk(利空回避)/vol_warn(波动预警)。
  **严禁冒充可交易 alpha**,只做关注/风险提示。

### L3 信号层(已探索,诚实归零)
- `eventstudy.py` — PIT 事件研究引擎(向量化,安慰剂无偏,均值/中位/去尾)。
- `r13-r25_*.py` — 15 轮回测脚本。结论:见下"活/死清单"。

## 活/死清单(严格 PIT + 真实摩擦 + 对抗检验后)

**死(证伪/不可投资)**:宽基惊喜因子(扣摩擦 Sharpe0.13)· 预增×龙虎榜共振(前视偏差,严格PIT后中位负)·
AI情绪→方向(残差IC≈0)· 回购/增减持/解禁 alpha · 事件密度 · 龙虎榜净买入追涨(右尾彩票)。

**活(L1/L2/风险,非可交易 alpha)**:rev+PEAD 预增方向(关注)· 龙虎榜净卖出(回避)·
事件存在性(波动旗)· 全球传导 lead/lag(情境)。

## 方法论要点(拦下伪发现的三道闸)
1. **中位数/去尾**(R17):揭穿龙虎榜净买入是右尾彩票(均值+3%但中位负)。
2. **真实摩擦+涨停不可买**(R22):宽基因子 Sharpe 1.90→0.13。
3. **前视复查**(R25):共振"明星发现"大部分是用未来龙虎榜选股;严格PIT后中位转负。
没有这三道,会上线一个带前视、扣摩擦即亏的策略。

## 数据表(migrations 0012-0017)
news_items · stock_announcements · news_digest · event_calendar · stock_news · stock_profile · stock_keywords

## 生产集成建议
- 调度:每日盘后跑 collector(主题轮转防限频)+ news_daily;个股详情按需算 signals/keywords。
- 前端:今日要闻页(日报+全球传导)· 详情页新闻tab(关联新闻+叙事关键词+信号旗)· 掉出分析引用新闻。
- **红线**:signals 只标关注/风险,绝不显示"预期收益/会涨会跌"。诚实定位=研究工具,非投资建议。
