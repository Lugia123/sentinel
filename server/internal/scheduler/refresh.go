package scheduler

import (
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"
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

func lastLine(s string) string {
	s = strings.TrimRight(s, "\n")
	if i := strings.LastIndexByte(s, '\n'); i >= 0 {
		return s[i+1:]
	}
	return s
}
