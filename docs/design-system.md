# Sentinel 设计规范 · 黑金(Obsidian & Gold)

> 版本 1（feature/v1.2）。风格调整只改这份 + `client/src/index.css` 的 `:root` tokens。

## 设计定位
- **受众**：不懂量化的散户小白。信息要一眼看懂、不吓人。
- **调性**：高级、克制、沉稳的「黑金」。深炭暖底 + 古金点缀，不是俗气的亮黄金；不是蓝紫科技风。
- **场景**：金融数据密集（表格/图表/徽章/多层卡片），暗色为主，长时间看不累。

## 反例（明确不做，避免 AI 味）
纯黑 #000、纯白 #fff、蓝紫渐变、霓虹描边、玻璃拟态、发光边框、渐变文字、每个标题上放大圆角图标、到处相同的卡片网格。

## 一、颜色 tokens
中性色**统一偏金棕暖调**（不用中性灰、不用冷蓝），金色作稀缺强调（只用在:品牌、激活态、关键数字、主按钮）。

```css
:root {
  /* 背景层级（暖近黑 → 炭 → 抬升面）*/
  --bg:        #0c0a07;   /* 页面底,暖近黑(非纯黑)*/
  --surface:   #16120d;   /* 卡片 */
  --surface-2: #1f1913;   /* 表头/次级/输入 */
  --elevated:  #241d15;   /* 悬浮层(tooltip/下拉)*/
  --border:    #2c2418;   /* 边框,暖金棕 */
  --border-2:  #3a2f1e;   /* 强边框/分隔 */

  /* 文字层级(暖米白,非纯白)*/
  --ink:       #f1e9da;   /* 主文字 */
  --ink-soft:  #bcae97;   /* 次要 */
  --ink-mute:  #837763;   /* 弱化(暗底仍可读)*/

  /* 金色强调(古金,克制)*/
  --gold:      #c8a253;   /* 主强调:品牌/激活/主按钮 */
  --gold-hi:   #e6c878;   /* 高亮/hover */
  --gold-dim:  #8a7238;   /* 暗金:细线/次强调 */
  --gold-glow: rgba(200,162,83,.14); /* 极淡金背景 */

  /* 涨跌(沉稳,非霓虹)*/
  --up:        #6fae86;   /* 涨/多/盈:鼠尾草绿 */
  --down:      #cf6f5d;   /* 跌/空/亏:陶土红 */
  --neutral:   #b9a888;   /* 中性:暖灰金 */
  --warn:      --gold;    /* 高亮/减仓 用金 */

  /* 图表色(暖系,依次)*/
  --c1:#c8a253; --c2:#6fae86; --c3:#cf6f5d; --c4:#9a8ec4; --c5:#7ba7b0;
  --grid: #241d15;

  --shadow: 0 4px 24px rgba(0,0,0,.5);
  --radius: 12px;
}
```
**语义恒定**：涨/多/盈=绿(--up)，跌/空/亏=红(--down)，关键数字/激活/减仓提示=金(--gold)，中性=暖灰金。金色**稀缺使用**——满屏金就俗了。

## 二、字体
- 中文用系统 **PingFang SC**（Mac 上最干净高级，非 slop）；数字/拉丁用 tabular-nums 对齐。
- 品牌字 `Sentinel` 用较大字重 + 字间距（letter-spacing），金色。
- 层级靠**字重 + 字号 + 颜色**拉开，不靠花哨字体。数字统一 `font-variant-numeric: tabular-nums`。

```css
body { font-family: "PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.num, table td, .big { font-variant-numeric: tabular-nums; }
```

## 三、间距与节奏
- 基准 4px 网格；卡片内 padding 16–20，卡片间距 16。
- 有节奏：紧凑分组（表格行 8/10）、慷慨分隔（区块间 20–24）。不要到处一样的 padding。
- 不把所有东西塞卡片；不卡片套卡片。

## 四、组件规范
- **Header(顶栏)**：固定顶部,`--surface` 底 + 底部 1px `--border`。左=金色品牌+版本;中/右=导航菜单(激活项**金色下划线**+金字);最右=主操作(重算,ghost 金边)。高 56px。
- **卡片**：`--surface` 底,1px `--border`,`--radius`,`--shadow`,padding 16–20。标题 13px `--ink-soft` 600。不用发光边。
- **表格**：表头 `--surface-2` 底 `--ink-mute`;行下 1px `--border`;hover 行 `--gold-glow` 暖染;数字右对齐 tabular。可点击行右侧金色 `›`。
- **徽章 pill**：小圆角,12px 600。金=强调(动量/激活),绿=多/盈,红=空/亏,暖灰=中性。背景用对应色 12–16% 透明。
- **按钮**：主=`--gold` 实底 + 深色字(稀缺,只 1 个/屏);次=ghost(`--border` 边 `--ink-soft` 字,hover 金边);文本链接=金字。不要每个按钮都主色。
- **tooltip(修 #1)**：`--elevated` 底 + `--gold-dim` 细边;**用 `position: fixed` + 跟随触发点定位(或 portal 到 body)**,绝不被表格 `overflow` 裁掉;z-index ≥ 1000。
- **风险灯**：绿/金/红 圆点 + 极淡同色光晕(唯一允许的微光,语义性)。

## 五、动效(克制)
- 只在状态变化用:入场淡入 + 轻微上移(transform/opacity);ease-out(quart/expo)。
- 不动 width/height/padding;不用 bounce/弹性。页面加载可做一次错落淡入。

## 六、可读性硬规则
- 暗底文字一律 `--ink`/`--ink-soft`,弱化最低到 `--ink-mute`(仍达对比)。不用更暗的灰。
- 金色不用于大段正文(仅点缀/数字/激活),避免疲劳。
