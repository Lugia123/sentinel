// Package investigate — AI 公司背景调查:DeepSeek 生成 HTML → 存 MinIO → 详情页 tab 展示。
// 大 HTML 不入 PG,存本地 MinIO。key = investigate/<ticker>.html。
package investigate

import (
	"context"
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
【HTML 格式硬要求】只输出片段,绝不要 <!doctype>/<html>/<head>/<body>/<style>/代码围栏。用 <h4>小标题</h4> + <p> + <ul><li>,关键词 <b>。不要写任何 CSS(颜色/背景交给页面),只用语义标签。中文。结尾一句 <p class="disc">AI 生成的背景资料,仅供参考,非投资建议。</p>。`

type Service struct {
	ai        *ai.Client
	blob      *blob.Store
	engineDir string
}

func New(aic *ai.Client, bs *blob.Store, engineDir string) *Service {
	return &Service{ai: aic, blob: bs, engineDir: engineDir}
}

func key(ticker string) string { return "investigate/" + ticker + ".html" }

// Investigate 返回 {ticker, key, cached}。前端用 /api/blob?key=<key> 取 HTML。
func (s *Service) Investigate(ctx context.Context, ticker string, force bool) (map[string]any, error) {
	if s.blob == nil || !s.blob.Enabled() {
		return nil, fmt.Errorf("MinIO 未配置,背景调查不可用")
	}
	k := key(ticker)
	if !force && s.blob.Exists(ctx, k) {
		return map[string]any{"ticker": ticker, "key": k, "cached": true}, nil
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek")
	}
	cn, sector := s.metaOf(ticker)
	user := fmt.Sprintf("公司代码:%s\n中文名:%s\n所属板块:%s\n请对这家美股上市公司做背景调查。", ticker, cn, sector)
	html, err := s.ai.Chat(ctx, SYSTEM, user)
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
