// Package investigate — AI 公司背景调查:DeepSeek 生成 HTML → 存 MinIO → 详情页 tab 展示。
// 大 HTML 不入 PG,存本地 MinIO。key = investigate/<ticker>.html。
package investigate

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"sentinel/internal/ai"
	"sentinel/internal/blob"
)

const SYSTEM = `你是严谨的美股行业研究助手,面向不懂英文/不了解美股的中国散户。任务:对给定公司做一份【背景调查】,输出一段【HTML 片段】(会被直接注入到已有的暗色页面里,随整页滚动)。
要求分区讲清:①公司是做什么的(主营业务、通俗解释)②在行业里的地位/排名/竞争对手 ③收入构成/主要市场 ④近年发展与看点 ⑤主要风险。
⑥【信息来源与时效 · 强制,必须写】新增一节 <h4>信息来源与时效</h4>:诚实说明——本调查由 AI 依据【训练时掌握的公开资料】综合生成,【非实时联网检索】,具体数字(市占率/排名/营收占比等)可能已过时或有偏差;并列出读者应据以核实的权威来源类型:公司 10-K/10-Q 年报与季报(SEC EDGAR)、公司投资者关系官网(IR)、主流财经媒体。凡你不确定的断言要显式标注"(需核实)"。绝不可编造具体的引用链接或声称你实时查阅了某网页。
【HTML 格式硬要求】只输出片段,绝不要 <!doctype>/<html>/<head>/<body>/<style>/代码围栏。用 <h4>小标题</h4> + <p> + <ul><li>,关键词 <b>。不要写任何 CSS(颜色/背景交给页面),只用语义标签。中文。结尾一句 <p class="disc">AI 生成的背景资料,仅供参考,非投资建议。</p>。`

// SYSTEM_CN A股版背调 prompt(来源指向巨潮/交易所/东财,不提 SEC)。
const SYSTEM_CN = `你是严谨的A股行业研究助手,面向中国散户。任务:对给定的A股上市公司做一份【背景调查】,输出一段【HTML 片段】(会被直接注入到已有的暗色页面里,随整页滚动)。
要求分区讲清:①公司是做什么的(主营业务、通俗解释)②在行业里的地位/排名/竞争对手 ③收入构成/主要客户与市场 ④近年发展与看点(重组/扩产/政策受益等)⑤主要风险(经营/行业/监管/股权质押/ST风险等)。
⑥【信息来源与时效 · 强制,必须写】新增一节 <h4>信息来源与时效</h4>:诚实说明——本调查由 AI 依据【训练时掌握的公开资料】综合生成,【非实时联网检索】,具体数字(市占率/排名/营收占比等)可能已过时或有偏差;并列出读者应据以核实的权威来源类型:公司年报/季报与公告(巨潮资讯网 cninfo,上交所/深交所披露平台)、公司投资者关系互动平台、主流财经媒体(如东方财富/财新)。凡你不确定的断言要显式标注"(需核实)"。绝不可编造具体的引用链接或声称你实时查阅了某网页。
【HTML 格式硬要求】只输出片段,绝不要 <!doctype>/<html>/<head>/<body>/<style>/代码围栏。用 <h4>小标题</h4> + <p> + <ul><li>,关键词 <b>。不要写任何 CSS(颜色/背景交给页面),只用语义标签。中文。结尾一句 <p class="disc">AI 生成的背景资料,仅供参考,非投资建议。</p>。`

type Service struct {
	ai        *ai.Client
	blob      *blob.Store
	engineDir string
}

func New(aic *ai.Client, bs *blob.Store, engineDir string) *Service {
	return &Service{ai: aic, blob: bs, engineDir: engineDir}
}

func key(userID int64, ticker string) string {
	return fmt.Sprintf("investigate/%d/%s.html", userID, ticker)
}

// Investigate 返回 {ticker, key, cached}。前端用 /api/blob?key=<key> 取 HTML。按用户隔离。
// market: us/cn(A股用 A股版 prompt 与中文名来源;ticker 形如 sh.600000,key 天然不冲突)。
func (s *Service) Investigate(ctx context.Context, userID int64, market, ticker string, force bool) (map[string]any, error) {
	if s.blob == nil || !s.blob.Enabled() {
		return nil, fmt.Errorf("MinIO 未配置,背景调查不可用")
	}
	k := key(userID, ticker)
	if !force && s.blob.Exists(ctx, k) {
		return map[string]any{"ticker": ticker, "key": k, "cached": true}, nil
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek")
	}
	system := SYSTEM
	var user string
	if market == "cn" {
		system = SYSTEM_CN
		user = fmt.Sprintf("【当前日期】%s(涉及时间以此为准,勿臆断年份)\n公司代码:%s\n公司名:%s\n请对这家A股上市公司做背景调查。", ai.TodayCN(), ticker, s.cnNameOf(ticker))
	} else {
		cn, sector := s.metaOf(ticker)
		user = fmt.Sprintf("【当前日期】%s(涉及时间以此为准,勿臆断年份)\n公司代码:%s\n中文名:%s\n所属板块:%s\n请对这家美股上市公司做背景调查。", ai.TodayCN(), ticker, cn, sector)
	}
	html, err := s.ai.Chat(ctx, system, user)
	if err != nil {
		return nil, err
	}
	html = stripFence(html)
	if err := s.blob.PutHTML(ctx, k, html); err != nil {
		return nil, err
	}
	return map[string]any{"ticker": ticker, "key": k, "cached": false}, nil
}

// stripFence 去掉 DeepSeek 可能包裹的 markdown 代码围栏(```html ... ```)。
func stripFence(s string) string {
	t := strings.TrimSpace(s)
	if strings.HasPrefix(t, "```") {
		if i := strings.IndexByte(t, '\n'); i >= 0 {
			t = t[i+1:]
		}
		t = strings.TrimSuffix(strings.TrimSpace(t), "```")
	}
	return strings.TrimSpace(t)
}

// cnNameOf 从 engine/data_cn_meta/universe.csv 查 A股中文名(查不到返回代码本身)。
func (s *Service) cnNameOf(code string) string {
	f, err := os.Open(filepath.Join(s.engineDir, "data_cn_meta", "universe.csv"))
	if err != nil {
		return code
	}
	defer f.Close()
	rows, err := csv.NewReader(f).ReadAll()
	if err != nil || len(rows) < 2 {
		return code
	}
	ci, ni := -1, -1
	for i, name := range rows[0] {
		switch name {
		case "code":
			ci = i
		case "code_name":
			ni = i
		}
	}
	if ci < 0 || ni < 0 {
		return code
	}
	for _, row := range rows[1:] {
		if ci < len(row) && row[ci] == code && ni < len(row) && row[ni] != "" {
			return row[ni]
		}
	}
	return code
}

func (s *Service) metaOf(ticker string) (cn, sector string) {
	b, err := os.ReadFile(filepath.Join(s.engineDir, "ticker_meta.json"))
	if err != nil {
		return ticker, ""
	}
	var m map[string]struct {
		CN     string `json:"cn"`
		Sector string `json:"sector"`
	}
	_ = json.Unmarshal(b, &m)
	if v, ok := m[ticker]; ok {
		return v.CN, v.Sector
	}
	return ticker, ""
}
