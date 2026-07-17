// Package explain — 用 DeepSeek 把某只持仓的策略计算结果讲成白话(带 DB 缓存)。
package explain

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"gorm.io/gorm"

	"sentinel/internal/ai"
	"sentinel/internal/store"
)

// 策略规则全文(注入 prompt,让 AI 严格据此解释,不编造)。
const RULES = `Sentinel 策略规则(严格据此解释,不得编造额外理由):
【选股】两条腿各选10只,各占一半仓位:
  - 动量腿:在98只大盘股里,先过"趋势门"(现价>200日线 且 200日线上行 且 现价>50日线 且 距52周高不超过25%),再按"相对SPY强度(近半年涨幅减SPY)"从高到低取前10。
  - 股东回报腿(SY):全市场按"股东收益率=净回购率+股息率"从高到低取前10。
【定仓】风险平价:波动越低给越多仓位(逆波动加权),各腿内部再分配。
【档位】-3到+3七档,由7个趋势子信号(站上20/50/200日线、200日线上行、21日动量为正、均线多头排列、接近52周高)求和映射而来。档位只用于"防御性减仓"(松·只减):+1及以上=持有,0=减一档,-1=减半,-2=减到1/4,-3=清仓。绝不追涨加仓(回测证追涨=负期望)。
【概率带】未来N日收益分布,用"波动缩放经验分布"算(把历史收益按波动标准化后取分位再还原)。70%区间=15%到85%分位。这是【离散度/波动范围】的校准估计,不是方向预测。
【风险灯】按SPY已实现波动做仓位闸(波动高=降总仓)。
【诚实边界】方向不可预测(已被严格回测证实);本系统是决策支持,不预测涨跌,只给趋势状态+校准的概率范围+风险提示。`

// RULES_CN A股策略规则(与美股不同的一套,严格据此解释)。
const RULES_CN = `Sentinel A股策略规则(严格据此解释,不得编造额外理由;与美股是两套独立策略):
【选股】按资金量级【二选一】的两套策略,各自成组、不叠加:
  A. 头号腿策略(小资金,容量约千万级):
     - 头号腿(主力,50只):全市场剔ST、只留可正常交易的,取流通市值最小约20%,再按40日均换手率从低到高取前50。多轮回测证实A股长期稳定有效的几乎只有"小市值"一个维度,低换手是干净代理。
     - 事件腿(20只,容量友好):分析师评级上修 + 业绩预告惊喜(rev+PEAD),做流通市值中性合成后取前20。
  B. 红利低波腿(大资金替代腿,50只,容量亿级+,与头号腿【二选一非叠加】):高股息率(TTM每股分红/价)× 低波动率(60日已实现波动)排名合成,再做流通市值中性后取前50。挑大盘高流动性,回撤更低、容量友好——微盘装不下的大资金用它替代头号腿(不是补充)。
【档位】-3到+3,由3个趋势子信号(站上20/60/200日线)求和。★A股逐票【只看不减】:档位仅展示趋势状态,每只动作恒为"持有"——A股是反转市,像美股那样对单只逐步减仓长期有害(回测证实),单票风险统一交给市场级风险灯管。
【风险灯(市场级Gate)】宽度(基准成分站上60日线比例)∧微盘拥挤度∧成交额未枯竭∧非小盘背离 → 满仓/半仓/空仓三档,管的是总仓位(头号腿与红利腿共用同一市场级风险灯)。
【概率带】未来20日收益分布,波动缩放经验分布(区间校准,非方向预测)。
【调仓】周频(每5个交易日重选,周内保持名单;换手用40日均阻尼降低无效换手)。全市场约5000只,剔ST/停牌僵尸股;只含存活股票,存在幸存者偏差。
【诚实边界】方向不可预测;本系统是决策支持,不预测涨跌,只给趋势状态+校准的概率范围+风险提示。`

const SYSTEM = `你是资深量化投资顾问,要让【完全不懂这只股票的小白】和【专业投资者】读了都觉得有收获。基于给定的【策略规则】和【这只股票的计算结果】,解读它此刻在策略眼中的处境。

【铁律:不要复述页面上已有的数字】。页面别处已经列了排名、动量百分比、7 个子信号、概率带表格——把它们再念一遍毫无价值。你的任务是解释这些结果【意味着什么】,数字只在支撑某个判断时一笔带过,绝不堆砌。

四段各有分工:
① 这是什么 —— 先用一句话讲清这家公司大致是做什么的(用你的常识;若真不确定它的主营就跳过,绝不编造),让没听过的人知道在看什么;再用一句白话给出此刻对它的总结论。这段给小白看。
② 为什么会看它 —— 分两种情况(看下方选股理由):
  · 若是【策略选中】(选股依据=策略的腿,美股:动量/股东回报/双腿;A股:头号腿/事件腿/红利低波/双腿):讲逻辑不讲排名,这条腿背后的机制对外行意味着什么?头号腿/事件腿是小资金策略、红利低波是大资金替代腿(二选一),讲清它被这条腿选中意味着什么。
  · 若是【用户自定义追踪股】(选股理由含"用户自定义"):说明白——这是你自己加进来追踪的,策略并没主动选它、也不占策略仓位;这一栏就讲"用同一套档位/趋势规则看,它现在够不够格、离被策略选中还差什么"。
③ 现在强在哪、弱在哪 —— 给专业读者的洞察:当前趋势结构强在哪、最脆弱的一环在哪、风险点是什么。要有判断,不是把 7 个信号列出来。
④ 接下来盯什么 —— 1 到 2 个具体、可观察的触发点(例如跌破哪条均线档位会掉、哪个指标若反转要警惕)。

不预测涨跌方向(已被回测证明不可预测),不夸张,不编造规则外的机制。
【输出格式】HTML 片段(不要 <html>/<body>,不要代码围栏),<h4>小标题</h4> + <p>/<ul><li>,关键处 <b>。四个小标题固定为:这是什么 / 为什么会看它 / 现在强在哪、弱在哪 / 接下来盯什么。结尾 <p class="disc">研究工具,非投资建议。</p>。全文 350 字内,宁精炼勿啰嗦。`

type Service struct {
	store *store.Store
	ai    *ai.Client
	gdb   *gorm.DB
}

func New(st *store.Store, aic *ai.Client, gdb *gorm.DB) *Service {
	return &Service{store: st, ai: aic, gdb: gdb}
}

type holding struct {
	Ticker     string          `json:"ticker"`
	Sleeve     string          `json:"sleeve"`
	Price      float64         `json:"price"`
	Grade      int             `json:"grade"`
	GradeLabel string          `json:"grade_label"`
	Action     string          `json:"action"`
	Reason     string          `json:"reason"`
	Signals    json.RawMessage `json:"signals"`
	Indicators json.RawMessage `json:"indicators"`
	Prob       json.RawMessage `json:"prob"`
}

// SYSTEM_DROPPED 掉出分析:股票从策略推荐中掉出后,详情页 AI 讲解切到这个视角。
const SYSTEM_DROPPED = `你是资深量化投资顾问。一只曾被策略选中的股票【已从推荐列表掉出】,请基于【策略规则】和【掉出前最后一天的计算结果】+【掉出后的价格表现】,给读者讲清楚掉出这件事。
【铁律】策略每天按固定规则重选,掉出=不再满足入选条件,不是"策略讨厌它"或方向预测。不要复述数字,要解释含义。不确定的机制绝不编造。
四段固定结构:
① 为什么掉出 —— 对照选股规则推断最可能的落选原因(美股:动量相对排名回落/跌破趋势门(200日线/50日线/距52周高)/股东收益率排名被挤出;A股头号腿:40日换手率抬升排出低换手前50/流通市值涨出最小20%分位/事件分衰减/被ST或停牌;A股红利低波腿:股息率排名下滑或60日波动率抬升被挤出低波前50/取消或减少分红/流通市值中性合成分衰减;周频调仓到期重选时也会自然换出)。结合给你的掉出前指标点出最可疑的1-2条,措辞用"最可能""大概率"。【若提供了近期关联新闻/公告,可引用其中与掉出相关的事件佐证(如业绩预减、减持、被ST),但新闻仅作解释素材、非选股依据】。
② 掉出意味着什么 —— 讲清楚:掉出≠看空预测,只是不再是策略眼中"最优的那批";历史上掉出后有的继续涨有的回落,策略不预测方向。
③ 持有者怎么办 —— 结合当前市场级风险灯/档位动作口径给操作参考(不是投资建议):美股按档位动作;A股按市场级风险灯统一指令。
④ 什么情况下会回来 —— 说明重新满足入选条件即可回归推荐(以及防抖CD机制:连续满足才回来)。
【输出格式】HTML 片段(不要 <html>/<body>/代码围栏),<h4>小标题</h4> + <p>/<ul><li>,关键处 <b>。四个小标题固定:为什么掉出 / 掉出意味着什么 / 持有者怎么办 / 什么情况下会回来。结尾 <p class="disc">研究工具,非投资建议。</p>。全文 350 字内。`

// Explain 返回某股白话讲解(按用户缓存;force=true 强制重算)。market: us/cn(取对应市场快照与规则)。
// 若该股在「掉出推荐」列表中,自动切换为掉出原因分析视角。
func (s *Service) Explain(ctx context.Context, userID int64, market, ticker, date string, force bool) (map[string]any, error) {
	if market != "cn" {
		market = "us"
	}
	if di := s.droppedInfo(market, ticker); di != nil {
		return s.explainDropped(ctx, userID, market, ticker, di, force)
	}
	raw, err := s.snapshot(market, date)
	if err != nil {
		return nil, err
	}
	var snap struct {
		Asof     string    `json:"asof"`
		Holdings []holding `json:"holdings"`
	}
	if err := json.Unmarshal(raw, &snap); err != nil {
		return nil, err
	}
	var h *holding
	for i := range snap.Holdings {
		if strings.EqualFold(snap.Holdings[i].Ticker, ticker) {
			h = &snap.Holdings[i]
			break
		}
	}
	if h == nil {
		// 自定义追踪股不在共享快照里,回退查该用户的 focus 缓存(每日追踪档位)
		tk := strings.ToUpper(ticker)
		if market == "cn" {
			tk = strings.ToLower(ticker) // A股代码存小写(sh.600000)
		}
		var raw2 string
		s.gdb.Raw(`SELECT holding::text FROM focus_cache WHERE user_id=? AND market=? AND ticker=? AND asof=?`,
			userID, market, tk, snap.Asof).Row().Scan(&raw2)
		if raw2 != "" {
			var ch holding
			if json.Unmarshal([]byte(raw2), &ch) == nil {
				h = &ch
			}
		}
	}
	if h == nil {
		return nil, fmt.Errorf("%s 不在 %s 的持仓里(自定义股请稍等档位算完再看讲解)", ticker, snap.Asof)
	}

	if !force {
		var cached string
		if s.gdb.Raw(`SELECT content FROM explanations WHERE user_id=? AND ticker=? AND asof=? AND kind='holding'`,
			userID, h.Ticker, snap.Asof).Row().Scan(&cached) == nil && cached != "" {
			return map[string]any{"ticker": h.Ticker, "asof": snap.Asof, "content": cached, "cached": true}, nil
		}
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek(server/.env 的 SENTINEL_DEEPSEEK_KEY);其余功能不受影响")
	}

	rules := RULES
	if market == "cn" {
		rules = RULES_CN
	}
	user := fmt.Sprintf("【当前日期】%s(时间判断以此为准,勿臆断年份)\n\n%s\n\n【这只股票 %s 的计算结果】\n档位:%d(%s)→ 动作:%s\n选股理由:%s\n档位子信号:%s\n关键指标:%s\n概率带:%s",
		ai.TodayCN(), rules, h.Ticker, h.Grade, h.GradeLabel, h.Action, h.Reason, string(h.Signals), string(h.Indicators), string(h.Prob))
	content, err := s.ai.Chat(ctx, SYSTEM, user)
	if err != nil {
		return nil, err
	}
	content = strings.TrimSpace(content)
	if strings.HasPrefix(content, "```") { // 去掉可能的代码围栏
		if i := strings.IndexByte(content, '\n'); i >= 0 {
			content = content[i+1:]
		}
		content = strings.TrimSuffix(strings.TrimSpace(content), "```")
	}
	s.gdb.Exec(`INSERT INTO explanations(user_id,ticker,asof,kind,content,model) VALUES (?,?,?,'holding',?,?)
		ON CONFLICT (user_id,ticker,asof,kind) DO UPDATE SET content=EXCLUDED.content, model=EXCLUDED.model, created_at=now()`,
		userID, h.Ticker, snap.Asof, content, "deepseek")
	return map[string]any{"ticker": h.Ticker, "asof": snap.Asof, "content": content, "cached": false}, nil
}

func (s *Service) snapshot(market, date string) ([]byte, error) {
	if date == "" || date == "latest" {
		return s.store.Latest(market)
	}
	return s.store.ByDate(market, date)
}

// droppedRec 掉出记录(查 dropped_stocks,nil=不在掉出列表)。
type droppedRec struct {
	LastSeen  string
	DroppedAt string
	LastPrice float64
	LastGrade int
	Context   string
}

// recentNewsContext 取该股近 30 天关联新闻/信号公告(A股),拼成 AI 掉出分析的素材段(无则空)。
// 新闻独立于策略:这里只把已采集的新闻作为"解释素材"注入,不影响任何策略计算。
func (s *Service) recentNewsContext(market, ticker string) string {
	if market != "cn" {
		return ""
	}
	var titles []string
	s.gdb.Raw(`(SELECT title FROM news_items WHERE ticker=? AND published_at >= now() - interval '30 days' ORDER BY published_at DESC LIMIT 5)
		UNION ALL
		(SELECT title FROM stock_announcements WHERE market=? AND ticker=? AND is_signal AND ann_date >= current_date - 30 ORDER BY ann_date DESC LIMIT 5)`,
		ticker, market, ticker).Scan(&titles)
	if len(titles) == 0 {
		return ""
	}
	out := "\n【近期关联新闻/公告(供参考,新闻独立于策略)】\n"
	for _, t := range titles {
		out += "· " + t + "\n"
	}
	return out
}

func (s *Service) droppedInfo(market, ticker string) *droppedRec {
	var d droppedRec
	s.gdb.Raw(`SELECT last_seen::text AS last_seen, dropped_at::text AS dropped_at, last_price, last_grade, context::text AS context
		FROM dropped_stocks WHERE market=? AND ticker=? AND status='dropped'`, market, ticker).Scan(&d)
	if d.DroppedAt == "" {
		return nil
	}
	return &d
}

// explainDropped 掉出原因分析:注入掉出前 holding + 掉出后价格表现,缓存 kind='dropped'。
func (s *Service) explainDropped(ctx context.Context, userID int64, market, ticker string, di *droppedRec, force bool) (map[string]any, error) {
	if !force {
		var cached string
		if s.gdb.Raw(`SELECT content FROM explanations WHERE user_id=? AND ticker=? AND asof=? AND kind='dropped'`,
			userID, ticker, di.DroppedAt).Row().Scan(&cached) == nil && cached != "" {
			return map[string]any{"ticker": ticker, "asof": di.DroppedAt, "content": cached, "cached": true, "dropped": true}, nil
		}
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek(server/.env 的 SENTINEL_DEEPSEEK_KEY);其余功能不受影响")
	}
	// 掉出后现价(该市场最新价),给 AI 讲"掉出后表现"
	var priceNow float64
	s.gdb.Raw(`SELECT close FROM prices WHERE market=? AND ticker=? ORDER BY date DESC LIMIT 1`, market, ticker).Row().Scan(&priceNow)
	perf := "无最新价"
	if priceNow > 0 && di.LastPrice > 0 {
		perf = fmt.Sprintf("掉出时价 %.2f → 现价 %.2f(%+.1f%%)", di.LastPrice, priceNow, (priceNow-di.LastPrice)/di.LastPrice*100)
	}
	rules := RULES
	if market == "cn" {
		rules = RULES_CN
	}
	// 注入近期关联新闻/公告(A股):让掉出分析"有据"而非纯推断(新闻独立,仅作解释素材)
	newsCtx := s.recentNewsContext(market, ticker)
	user := fmt.Sprintf("【当前日期】%s(时间判断以此为准,勿臆断年份)\n\n%s\n\n【股票 %s 已从推荐掉出】\n最后在推荐中:%s;判定掉出:%s;掉出时档位:%d\n掉出后表现:%s\n【掉出前最后一天的完整计算结果】\n%s%s",
		ai.TodayCN(), rules, ticker, di.LastSeen, di.DroppedAt, di.LastGrade, perf, di.Context, newsCtx)
	content, err := s.ai.Chat(ctx, SYSTEM_DROPPED, user)
	if err != nil {
		return nil, err
	}
	content = strings.TrimSpace(content)
	if strings.HasPrefix(content, "```") {
		if i := strings.IndexByte(content, '\n'); i >= 0 {
			content = content[i+1:]
		}
		content = strings.TrimSuffix(strings.TrimSpace(content), "```")
	}
	s.gdb.Exec(`INSERT INTO explanations(user_id,ticker,asof,kind,content,model) VALUES (?,?,?,'dropped',?,?)
		ON CONFLICT (user_id,ticker,asof,kind) DO UPDATE SET content=EXCLUDED.content, model=EXCLUDED.model, created_at=now()`,
		userID, ticker, di.DroppedAt, content, "deepseek")
	return map[string]any{"ticker": ticker, "asof": di.DroppedAt, "content": content, "cached": false, "dropped": true}, nil
}
