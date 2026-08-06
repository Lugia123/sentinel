// Package api — Sentinel HTTP 路由与处理器(stdlib net/http,零外部 web 依赖)。
package api

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"gorm.io/gorm"

	"sentinel/internal/ai"
	"sentinel/internal/blob"
	"sentinel/internal/earnings"
	"sentinel/internal/engine"
	"sentinel/internal/explain"
	"sentinel/internal/investigate"
	"sentinel/internal/pipeline"
	"sentinel/internal/scheduler"
	"sentinel/internal/portfolio"
	"sentinel/internal/store"
	"sentinel/internal/allocate"
	"sentinel/internal/auth"
	"sentinel/internal/version"
)

type API struct {
	store     *store.Store
	runner    *engine.Runner
	port      *portfolio.Store
	explain   *explain.Service
	invest    *investigate.Service
	earn      *earnings.Service
	alloc     *allocate.Service
	authSvc   *auth.Service
	blob      *blob.Store
	gdb       *gorm.DB
	aiClient  *ai.Client // 新闻解读/专栏合成用(与策略无关)
	dataDir   string
	engineDir string
	ver       version.Info
}

func New(st *store.Store, rn *engine.Runner, pf *portfolio.Store, ex *explain.Service, inv *investigate.Service, earn *earnings.Service, al *allocate.Service, au *auth.Service, bs *blob.Store, gdb *gorm.DB, aic *ai.Client, dataDir, engineDir string, ver version.Info) *API {
	return &API{store: st, runner: rn, port: pf, explain: ex, invest: inv, earn: earn, alloc: al, authSvc: au, blob: bs, gdb: gdb, aiClient: aic, dataDir: dataDir, engineDir: engineDir, ver: ver}
}

func (a *API) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", a.health)
	mux.HandleFunc("/api/version", a.version)
	mux.HandleFunc("/api/datastatus", a.dataStatus)
	mux.HandleFunc("/api/altstatus", a.altStatus)
	mux.HandleFunc("/api/snapshot", a.snapshot)
	mux.HandleFunc("/api/snapshot/dates", a.dates)
	mux.HandleFunc("/api/risklight/history", a.riskHistory)
	mux.HandleFunc("/api/run", auth.RequireAdmin(a.run)) // 重算仅管理员
	mux.HandleFunc("/api/admin/settings/schedule", auth.RequireAdmin(a.schedule)) // 调度间隔(管理员维护)
	mux.HandleFunc("/api/positions", a.positions)
	mux.HandleFunc("/api/explain", a.explainHandler)
	mux.HandleFunc("/api/history", a.history)
	mux.HandleFunc("/api/blob", a.blobHandler)
	mux.HandleFunc("/api/meta", a.meta)
	mux.HandleFunc("/api/universe", a.universe)
	mux.HandleFunc("/api/strategies", a.strategies)
	mux.HandleFunc("/api/watchlist", a.watchlist)
	mux.HandleFunc("/api/watchlist/star", a.watchStar)
	mux.HandleFunc("/api/watchlist/custom", a.watchCustom)
	mux.HandleFunc("/api/focus", a.focus)
	mux.HandleFunc("/api/bandhist", a.bandHist)
	mux.HandleFunc("/api/moneyflow", a.moneyFlow)
	mux.HandleFunc("/api/moneyflow/sector", a.sectorFlow)
	mux.HandleFunc("/api/moneyflow/macro", a.macroFlow)
	mux.HandleFunc("/api/trend", a.trend)
	mux.HandleFunc("/api/trend/tickers", a.trendTickers)
	mux.HandleFunc("/api/dropped", a.dropped)
	mux.HandleFunc("/api/news/digest", a.newsDigest) // 新闻模块(只读 overlay,不碰策略)
	mux.HandleFunc("/api/news/stock", a.newsStock)
	mux.HandleFunc("/api/news/calendar", a.newsCalendar)
	mux.HandleFunc("/api/news/item", a.newsItem)
	mux.HandleFunc("/api/news/event-interpret", a.newsEventInterpret)
	mux.HandleFunc("/api/news/column", a.newsColumn)
	mux.HandleFunc("/api/news/column/digest", a.newsSectorDigest)
	mux.HandleFunc("/api/news/feed", a.newsFeed)
	mux.HandleFunc("/api/investigate", a.investigate)
	mux.HandleFunc("/api/earnings/quarters", a.earningsQuarters)
	mux.HandleFunc("/api/earnings", a.earningsInterpret)
	mux.HandleFunc("/api/allocate", a.allocateHandler)
	mux.HandleFunc("/api/capital", a.capital)
	mux.HandleFunc("/api/strategy", a.strategy)
	a.authSvc.Register(mux) // 认证/管理员路由
	// 中间件链:cors → 注入用户(解析令牌)→ 登录门(非公开路径需登录)→ mux
	return cors(a.authSvc.Inject(gate(mux)))
}

// gate 登录门:公开路径放行,其余需已登录。
func gate(next http.Handler) http.Handler {
	open := map[string]bool{
		"/api/auth/login": true, "/api/auth/forgot": true, "/api/auth/reset": true,
		"/api/health": true, "/api/version": true,
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodOptions || open[r.URL.Path] || auth.UserID(r) != 0 {
			next.ServeHTTP(w, r)
			return
		}
		http.Error(w, `{"error":"请先登录"}`, http.StatusUnauthorized)
	})
}

// earningsQuarters 列出可解读的季度。?ticker=X
func (a *API) earningsQuarters(w http.ResponseWriter, r *http.Request) {
	tk := r.URL.Query().Get("ticker")
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	qs, err := a.earn.QuartersWithStatus(r.Context(), auth.UserID(r), mktParam(r), normTicker(mktParam(r), tk))
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ticker": tk, "quarters": qs})
}

// earningsInterpret AI解读某季度(→HTML→MinIO)。?ticker=X&period=YYYY-MM-DD&force=1
func (a *API) earningsInterpret(w http.ResponseWriter, r *http.Request) {
	tk := r.URL.Query().Get("ticker")
	period := r.URL.Query().Get("period")
	if tk == "" || period == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker 或 period"})
		return
	}
	res, err := a.earn.Interpret(r.Context(), auth.UserID(r), mktParam(r), normTicker(mktParam(r), tk), period, r.URL.Query().Get("force") == "1")
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// investigate AI 公司背景调查(→HTML→MinIO)。?ticker=X&force=1;返回 {key},前端用 /api/blob?key= 取。
func (a *API) investigate(w http.ResponseWriter, r *http.Request) {
	tk := r.URL.Query().Get("ticker")
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	res, err := a.invest.Investigate(r.Context(), auth.UserID(r), mktParam(r), normTicker(mktParam(r), tk), r.URL.Query().Get("force") == "1")
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// dropped 掉出推荐列表:曾被策略选中、现已掉出(经 CD 防抖)的股票。?market=cn
func (a *API) dropped(w http.ResponseWriter, r *http.Request) {
	items, err := a.store.Dropped(mktParam(r))
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"dropped": items})
}

// focus 单股观察:任意 ticker 用同规则分析(资金池=这一只)。?ticker=X&market=cn
func (a *API) focus(w http.ResponseWriter, r *http.Request) {
	mkt := mktParam(r)
	tk := normTicker(mkt, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	out, err := a.runner.RunFocus(mkt, tk, q(r, "asof", "latest"), q(r, "capital", "4000"))
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write([]byte(out))
}

// bandHist A股【未来20日收益范围】逐日历史(详情页价格图下方两图:收益% / 价格锥)。
// 单票现算(~0.5s,值永久不变故不缓存);当前仅 cn。
func (a *API) bandHist(w http.ResponseWriter, r *http.Request) {
	mkt := mktParam(r)
	tk := normTicker(mkt, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	n := 120
	if v := r.URL.Query().Get("n"); v != "" {
		if x, err := strconv.Atoi(v); err == nil && x >= 20 && x <= 500 {
			n = x
		}
	}
	out, err := a.runner.RunBandHist(mkt, tk, q(r, "asof", "latest"), n)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write([]byte(out))
}

// moneyFlow A股个股【资金流·量能】展示卡数据(纯展示,不进策略)。单票现算 ~1s;仅 cn。
func (a *API) moneyFlow(w http.ResponseWriter, r *http.Request) {
	mkt := mktParam(r)
	tk := normTicker(mkt, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	days := 40
	if v := r.URL.Query().Get("days"); v != "" {
		if x, err := strconv.Atoi(v); err == nil && x >= 10 && x <= 120 {
			days = x
		}
	}
	out, err := a.runner.RunMoneyflow(mkt, tk, days)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write([]byte(out))
}

// sectorFlow A股【板块资金热力】(行业净流入排行 + 近5日累计,纯展示)。全站共享、每日更新,
// 引擎 ~5s → 进程内缓存 30 分钟(免每次访问都拉 tushare)。
var sectorCache struct {
	sync.Mutex
	at   time.Time
	body string
}
var macroCache struct {
	sync.Mutex
	at   time.Time
	body string
}

// warmSector 拉一次板块资金流填入缓存(供后台预热,让用户永远命中热缓存)。
func (a *API) warmSector() {
	out, err := a.runner.RunSectorFlow(5)
	if err != nil {
		log.Printf("[sectorflow] 预热失败(继续用旧缓存): %v", err)
		return
	}
	sectorCache.Lock()
	sectorCache.body = out
	sectorCache.at = time.Now()
	sectorCache.Unlock()
}

// warmMacro 拉一次大盘+北向资金流填入缓存。
func (a *API) warmMacro() {
	out, err := a.runner.RunMacroFlow(20)
	if err != nil {
		log.Printf("[macroflow] 预热失败(继续用旧缓存): %v", err)
		return
	}
	macroCache.Lock()
	macroCache.body = out
	macroCache.at = time.Now()
	macroCache.Unlock()
}

// StartSectorWarmer 启动即预热 + 每 25 分钟刷新资金流(板块+大盘北向)缓存(非阻塞)。
func (a *API) StartSectorWarmer() {
	go func() {
		a.warmSector()
		a.warmMacro()
		t := time.NewTicker(25 * time.Minute)
		defer t.Stop()
		for range t.C {
			a.warmSector()
			a.warmMacro()
		}
	}()
}

// macroFlow A股【大盘 + 北向】资金流(纯展示)。全站共享、每日更新,缓存30分钟 + 后台预热。
func (a *API) macroFlow(w http.ResponseWriter, r *http.Request) {
	macroCache.Lock()
	fresh := macroCache.body != "" && time.Since(macroCache.at) < 30*time.Minute
	body := macroCache.body
	macroCache.Unlock()
	if !fresh {
		out, err := a.runner.RunMacroFlow(20)
		if err != nil {
			if body != "" {
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				_, _ = w.Write([]byte(body))
				return
			}
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		macroCache.Lock()
		macroCache.body = out
		macroCache.at = time.Now()
		macroCache.Unlock()
		body = out
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write([]byte(body))
}

func (a *API) sectorFlow(w http.ResponseWriter, r *http.Request) {
	sectorCache.Lock()
	fresh := sectorCache.body != "" && time.Since(sectorCache.at) < 30*time.Minute
	body := sectorCache.body
	sectorCache.Unlock()
	if !fresh {
		out, err := a.runner.RunSectorFlow(5)
		if err != nil {
			if body != "" { // 拉取失败但有旧缓存:返回旧的(降级),不报错
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				_, _ = w.Write([]byte(body))
				return
			}
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		sectorCache.Lock()
		sectorCache.body = out
		sectorCache.at = time.Now()
		sectorCache.Unlock()
		body = out
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write([]byte(body))
}

// strategies 返回当天启用的策略组合(从最新快照的 strategy_config 提取)。
func (a *API) strategies(w http.ResponseWriter, r *http.Request) {
	raw, err := a.store.Latest(mktParam(r))
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "无快照"})
		return
	}
	var snap struct {
		StrategyConfig json.RawMessage `json:"strategy_config"`
	}
	_ = json.Unmarshal(raw, &snap)
	if len(snap.StrategyConfig) == 0 {
		writeJSON(w, http.StatusOK, map[string]string{"note": "该快照无策略元数据(重算后即有)"})
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(snap.StrategyConfig)
}

// blobHandler 从 MinIO 取大 HTML(背调/财报):?key=... 直接返回 HTML。
func (a *API) blobHandler(w http.ResponseWriter, r *http.Request) {
	key := r.URL.Query().Get("key")
	if key == "" || a.blob == nil || !a.blob.Enabled() {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "缺 key 或 MinIO 未配置"})
		return
	}
	html, err := a.blob.GetHTML(r.Context(), key)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": err.Error()})
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(html))
}

// explainHandler AI 白话讲解某股:?ticker=X&date=&force=1
func (a *API) explainHandler(w http.ResponseWriter, r *http.Request) {
	ticker := r.URL.Query().Get("ticker")
	if ticker == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	res, err := a.explain.Explain(r.Context(), auth.UserID(r), mktParam(r), ticker, r.URL.Query().Get("date"), r.URL.Query().Get("force") == "1")
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (a *API) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "sentinel", "version": a.ver.Version})
}

func (a *API) version(w http.ResponseWriter, r *http.Request) { writeJSON(w, http.StatusOK, a.ver) }

// dataStatus 数据源完整性:快照(DB)+ 价格覆盖(DB)+ 数据源清单。
func (a *API) dataStatus(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	dates, _ := a.store.Dates(market)
	status := map[string]any{"snapshot_dates": dates, "n_snapshots": len(dates), "storage": "PostgreSQL"}
	if raw, err := a.store.Latest(market); err == nil {
		var snap map[string]any
		_ = json.Unmarshal(raw, &snap)
		status["latest_asof"] = snap["asof"]
		if hs, ok := snap["holdings"].([]any); ok {
			status["n_holdings"] = len(hs)
		}
		status["risk_light"] = snap["risk_light"]
	}
	var nPrices int64
	var priceAsof string
	a.gdb.Raw(`SELECT count(*) FROM prices WHERE market=? AND date=(SELECT max(date) FROM prices WHERE market=?)`, market, market).Row().Scan(&nPrices)
	a.gdb.Raw(`SELECT max(date)::text FROM prices WHERE market=?`, market).Row().Scan(&priceAsof)
	status["price_table"] = map[string]any{"asof": priceAsof, "n_tickers": nPrices}
	status["sources"] = map[string]string{
		"prices":       "safna_jr/round20/data_broad(1393只 OHLCV+指标)→ 选股/档位/概率/盈亏",
		"fundamentals": "SEC EDGAR PIT(SY 股东收益率)→ 选股SY腿",
		"note":         "历史至2026-06-25;实时刷新(yfinance)待接",
	}
	writeJSON(w, http.StatusOK, status)
}

// altStatus A股【事件/红利腿 tushare】数据源健康,供前端顶部故障红条判断。
// tushare 是唯一需 token(月卡会过期)的源,仅影响 A股 事件/红利/板块;美股与 A股头号腿(baostock)不涉及。
// ok=false 当:①上次成功刷新已陈旧(超 3× 调度间隔,至少12h)——数据接口很可能故障;或 ②从未成功且已报错。
// 全新部署尚未跑过(无成功记录且无错误)→ ok=true,不误报。
func (a *API) altStatus(w http.ResponseWriter, r *http.Request) {
	lastOK := a.store.GetSetting(scheduler.AltLastOKKey)
	errMark := a.store.GetSetting(scheduler.AltErrKey)
	interval := 4
	if v := a.store.GetSetting(scheduler.SettingKey); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 && n <= 24 {
			interval = n
		}
	}
	staleHours := float64(3 * interval) // 容忍几个周期抖动,避免单次网络抖动误报
	if staleHours < 12 {
		staleHours = 12
	}
	resp := map[string]any{"ok": true, "source": "A股事件/红利数据"}
	if lastOK != "" {
		if sec, err := strconv.ParseInt(lastOK, 10, 64); err == nil {
			ageH := time.Since(time.Unix(sec, 0)).Hours()
			resp["last_ok"] = time.Unix(sec, 0).Format("2006-01-02 15:04")
			resp["stale_hours"] = int(ageH)
			if ageH > staleHours {
				resp["ok"] = false
			}
		}
	} else if errMark != "" {
		resp["ok"] = false // 从未成功且已报错 = 确实故障
	}
	if errMark != "" {
		resp["last_error"] = errMark
	}
	writeJSON(w, http.StatusOK, resp)
}

func (a *API) snapshot(w http.ResponseWriter, r *http.Request) {
	date := r.URL.Query().Get("date")
	market := mktParam(r)
	var (
		raw json.RawMessage
		err error
	)
	if date == "" || date == "latest" {
		raw, err = a.store.Latest(market)
	} else {
		raw, err = a.store.ByDate(market, date)
	}
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "无快照,请先 POST /api/run 生成", "detail": err.Error()})
		return
	}
	raw = a.personalizeSnapshot(auth.UserID(r), market, raw) // 按用户资金池缩放 + 合并其自定义股(隔离,分市场)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(raw)
}

// personalizeSnapshot 把共享快照个性化为当前用户视图:
//  1) 按该用户的资金池线性缩放 target_shares/target_value(资金池只是线性因子,不用重跑引擎)
//  2) 并入该用户的自定义追踪股(watchlist source=user,sleeve=custom股数0,隔离)
func (a *API) personalizeSnapshot(uid int64, market string, raw json.RawMessage) json.RawMessage {
	if uid == 0 {
		return raw
	}
	var snap map[string]any
	if json.Unmarshal(raw, &snap) != nil {
		return raw
	}
	asof, _ := snap["asof"].(string)
	holdings, _ := snap["holdings"].([]any)
	changed := false

	// 1) 按用户资金池缩放
	userCap := a.authSvc.GetCapital(uid, market)
	snapCap, _ := snap["capital"].(float64)
	if userCap > 0 && snapCap > 0 && userCap != snapCap {
		scale := userCap / snapCap
		for _, h := range holdings {
			m, ok := h.(map[string]any)
			if !ok {
				continue
			}
			if ts, ok := m["target_shares"].(float64); ok {
				m["target_shares"] = float64(int(ts*scale*1000+0.5)) / 1000
			}
			if tv, ok := m["target_value"].(float64); ok {
				m["target_value"] = float64(int(tv*scale*100+0.5)) / 100
			}
		}
		snap["capital"] = userCap
		changed = true
	}

	// 2) 合并该用户的自定义股
	held := map[string]bool{}
	for _, h := range holdings {
		if m, ok := h.(map[string]any); ok {
			if tk, ok := m["ticker"].(string); ok {
				held[strings.ToUpper(tk)] = true
			}
		}
	}
	var customTk []string
	a.gdb.Raw(`SELECT ticker FROM watchlist WHERE user_id=? AND market=? AND custom=true`, uid, market).Scan(&customTk)
	for _, tk := range customTk {
		tk = normTicker(market, tk)
		if tk == "" || held[strings.ToUpper(tk)] {
			continue
		}
		if h := a.cachedFocus(uid, market, tk, asof); h != nil { // 只用缓存,不阻塞
			holdings = append(holdings, h)
			held[strings.ToUpper(tk)] = true
			changed = true
		} else {
			go a.warmFocus(uid, market, tk, asof) // 缓存冷(如新交易日):后台预热,本次跳过
		}
	}

	if !changed {
		return raw
	}
	snap["holdings"] = holdings
	if out, err := json.Marshal(snap); err == nil {
		return out
	}
	return raw
}

// capital 每个用户的资金池:GET 读 / PUT 改。
func (a *API) capital(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{"capital": a.authSvc.GetCapital(uid, mktParam(r))})
	case http.MethodPut:
		var b struct {
			Capital float64 `json:"capital"`
		}
		_ = json.NewDecoder(r.Body).Decode(&b)
		if err := a.authSvc.SetCapital(uid, mktParam(r), b.Capital); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"capital": b.Capital})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET/PUT"})
	}
}

// strategy 用户×市场策略偏好(A股「headline 头号腿·微盘 / dividend 红利低波·大资金」二选一)
func (a *API) strategy(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{"strategy": a.authSvc.GetStrategy(uid, mktParam(r))})
	case http.MethodPut:
		var b struct {
			Strategy string `json:"strategy"`
		}
		_ = json.NewDecoder(r.Body).Decode(&b)
		if err := a.authSvc.SetStrategy(uid, mktParam(r), b.Strategy); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"strategy": b.Strategy})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET/PUT"})
	}
}

func (a *API) latestAsof(market string) string {
	var asof string
	a.gdb.Raw(`SELECT asof::text FROM snapshots WHERE market=? ORDER BY asof DESC LIMIT 1`, market).Row().Scan(&asof)
	return asof
}

// cachedFocus 只读缓存的自定义股档位(无则返回 nil,不跑 focus,不阻塞)。
func (a *API) cachedFocus(uid int64, market, ticker, asof string) map[string]any {
	var cached string
	a.gdb.Raw(`SELECT holding::text FROM focus_cache WHERE user_id=? AND market=? AND ticker=? AND asof=?`, uid, market, ticker, asof).Row().Scan(&cached)
	if cached != "" {
		var h map[string]any
		if json.Unmarshal([]byte(cached), &h) == nil {
			return h
		}
	}
	return nil
}

// warmFocus 计算并缓存某用户某股在 asof 的档位(阻塞~3秒;加自定义股/后台预热用)。
// sleeve=custom,不占仓位。返回 holding(失败返回 nil)。
func (a *API) warmFocus(uid int64, market, ticker, asof string) map[string]any {
	if h := a.cachedFocus(uid, market, ticker, asof); h != nil {
		return h
	}
	out, err := a.runner.RunFocus(market, ticker, asof, "4000")
	if err != nil {
		return nil
	}
	var fr struct {
		Holding map[string]any `json:"holding"`
	}
	if json.Unmarshal([]byte(out), &fr) != nil || fr.Holding == nil {
		return nil
	}
	fr.Holding["sleeve"] = "custom"
	fr.Holding["target_shares"] = 0.0
	fr.Holding["target_value"] = 0.0
	fr.Holding["base_weight"] = 0.0
	fr.Holding["reason"] = "用户自定义 · 每日追踪(不占策略仓位)"
	if hb, e := json.Marshal(fr.Holding); e == nil {
		a.gdb.Exec(`INSERT INTO focus_cache(user_id,market,ticker,asof,holding) VALUES(?,?,?,?,?::jsonb)
			ON CONFLICT (user_id,market,ticker,asof) DO UPDATE SET holding=EXCLUDED.holding`, uid, market, ticker, asof, string(hb))
	}
	return fr.Holding
}

func (a *API) dates(w http.ResponseWriter, r *http.Request) {
	ds, err := a.store.Dates(mktParam(r))
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"dates": ds})
}

// run 触发引擎(产 JSON)→ ingest 快照+价格入 PostgreSQL。
func (a *API) run(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "用 POST"})
		return
	}
	asof := q(r, "asof", "latest")
	res, err := pipeline.RunAndIngest(a.runner, a.store, a.dataDir, mktParam(r), asof, q(r, "capital", "4000"), r.URL.Query().Get("sy") != "0", nil)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error(), "log": res.Log})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "done", "snapshot_id": res.SnapshotID, "n_prices": res.NPrices, "log": res.Log})
}

func (a *API) positions(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		res, err := a.port.Compute(auth.UserID(r), mktParam(r), r.URL.Query().Get("date"))
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, res)
	case http.MethodPost:
		var ps []portfolio.Input
		if err := json.NewDecoder(r.Body).Decode(&ps); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "body 应为持仓数组: " + err.Error()})
			return
		}
		mkt := mktParam(r)
		for i := range ps {
			ps[i].Ticker = normTicker(mkt, ps[i].Ticker)
		}
		if err := a.port.Save(auth.UserID(r), mkt, ps); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "saved", "n": len(ps)})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET 或 POST"})
	}
}

func q(r *http.Request, k, d string) string {
	if v := r.URL.Query().Get(k); v != "" {
		return v
	}
	return d
}

// schedule 管理员维护调度间隔(小时)。GET 读当前;PUT {interval_hours} 改(clamp[1,24])。
func (a *API) schedule(w http.ResponseWriter, r *http.Request) {
	cur := 4
	if v := a.store.GetSetting(scheduler.SettingKey); v != "" {
		if n, e := strconv.Atoi(v); e == nil && n >= 1 && n <= 24 {
			cur = n
		}
	}
	if r.Method == http.MethodPut {
		var body struct {
			IntervalHours int `json:"interval_hours"`
		}
		if json.NewDecoder(r.Body).Decode(&body) != nil || body.IntervalHours < 1 || body.IntervalHours > 24 {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "interval_hours 须为 1-24 的整数"})
			return
		}
		if e := a.store.SetSetting(scheduler.SettingKey, strconv.Itoa(body.IntervalHours)); e != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": e.Error()})
			return
		}
		cur = body.IntervalHours
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"interval_hours": cur, "markets": scheduler.MARKETS,
		"note": "每 " + strconv.Itoa(cur) + " 小时自动刷新数据+跑双市场;EOD数据每天更一次,多跑=兜底重试;下个周期生效",
	})
}

// mktParam 从请求读市场(?market=cn/us),默认 us(向后兼容)。
func mktParam(r *http.Request) string {
	if r.URL.Query().Get("market") == "cn" {
		return "cn"
	}
	return "us"
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
