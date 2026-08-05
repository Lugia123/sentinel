package scheduler

import (
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// tushare 另类数据(A股事件/红利腿)健康标记 —— 存 settings 表,供 /api/altstatus 判断故障红条。
const (
	AltLastOKKey = "ts_alt_last_ok" // 最近一次成功刷新的 unix 秒(前端算 staleness)
	AltErrKey    = "ts_alt_error"   // 最近一次失败标记("时间|简述";成功后清空)
)

// refreshData 增量刷新某市场 EOD 数据(新交易日才拉,幂等)。
// 调 engine/refresh_data.py --market <m>:内部检测本地最新日 vs 数据源最新交易日,
// 已最新则秒退(skip),有新日才增量拉。US=yfinance / CN=baostock。脚本不存在则跳过。
func (s *Scheduler) refreshData(market string) {
	if market != "cn" {
		market = "us"
	}
	script := filepath.Join(s.rn.EngineDir(), "refresh_data.py")
	if _, err := os.Stat(script); err != nil {
		return // 刷新脚本未部署(S2 前),跳过——用现有数据
	}
	out, err := s.rn.RunPython(script, []string{"--market", market}, 40*time.Minute)
	if err != nil {
		log.Printf("[scheduler] [%s] 数据刷新失败(继续用现有数据):%v", market, err)
		return
	}
	if line := strings.TrimSpace(out); line != "" {
		log.Printf("[scheduler] [%s] 数据刷新:%s", market, lastLine(line))
	}
}

// refreshAlt 增量刷新 A股【事件腿+红利腿】的 tushare 另类数据(仅 cn)。
// 调 engine/ts_refresh.py --since <日>:拉分红/业绩预告/研报评级 → 覆写引擎读的 parquet(schema 不变)。
// 窗口自适应(见下方):既保留~45交易日回看余量,又能在 token 续期晚时补齐整段断档。
// 记录成功时刻(AltLastOKKey)/失败标记(AltErrKey)供 /api/altstatus 驱动前端故障红条。
// 头号腿行情不涉及(仍走 baostock)。凭证 SENTINEL_TS_URL/SENTINEL_TS_TOKEN 由 server/.env 注入进程 env,RunPython 继承。
// 脚本不存在或凭证缺失则内部跳过;失败只记日志+故障标记、继续用现有 parquet(失败隔离,不阻断策略)。
func (s *Scheduler) refreshAlt(market string) {
	if market != "cn" {
		return
	}
	script := filepath.Join(s.rn.EngineDir(), "ts_refresh.py")
	if _, err := os.Stat(script); err != nil {
		return
	}
	// 断档自愈 + 保留旧45天余量:窗口起点取「上次成功日-7天」与「今天-60天(~45交易日)」中更早者。
	//   健康节奏 → 起点=今天-60天,重拉~45交易日(与旧 --days 45 等价,catch 修订);
	//   token 续期晚(断档>45天)→ 起点=上次成功日锚点,完整覆盖整段缺口,不再被45天窗口截断。
	since := time.Now().AddDate(0, 0, -60) // 兜底下限:至少回看约45交易日
	if v := s.st.GetSetting(AltLastOKKey); v != "" {
		if sec, err := strconv.ParseInt(v, 10, 64); err == nil {
			if cand := time.Unix(sec, 0).AddDate(0, 0, -7); cand.Before(since) {
				since = cand
			}
		}
	}
	out, err := s.rn.RunPython(script, []string{"--since", since.Format("20060102")}, 30*time.Minute)
	if err != nil {
		// 失败:记故障标记(供前端红条),保留 last_ok 不变(缺口锚点)→ 恢复后 --since 覆盖整段断档
		_ = s.st.SetSetting(AltErrKey, time.Now().Format("2006-01-02 15:04")+"|另类数据接口拉取失败")
		log.Printf("[scheduler] [cn] 另类数据(tushare)刷新失败(继续用现有 parquet):%v", err)
		return
	}
	// 成功:更新最近成功时刻 + 清除故障标记
	_ = s.st.SetSetting(AltLastOKKey, strconv.FormatInt(time.Now().Unix(), 10))
	_ = s.st.SetSetting(AltErrKey, "")
	if line := strings.TrimSpace(out); line != "" {
		log.Printf("[scheduler] [cn] 另类数据刷新:%s", lastLine(line))
	}
}

func lastLine(s string) string {
	s = strings.TrimRight(s, "\n")
	if i := strings.LastIndexByte(s, '\n'); i >= 0 {
		return s[i+1:]
	}
	return s
}
