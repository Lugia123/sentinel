import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchSectorFlow, fetchSectorHistory, type SectorFlow, type SectorItem, type SectorHistory } from '../api'
import { InfoDot, riseColor, fallColor, cssVar } from '../ui'

// 板块资金分析 —— 一卡四视图(纯展示,不进策略):今日全景 / 历史热力(全行业)/ 累计吸金 / 轮动RRG。
// 颜色:热力随涨跌配色(红入绿出);曲线/RRG 用分类色(非涨跌语意)。
type View = 'today' | 'heat' | 'cum' | 'rrg'
const PAL = ['#e6c878', '#7ba7b0', '#9a8ec4', '#d19a66', '#84b6c4', '#c8a253', '#b98ec4', '#8ab0a0', '#cbb26a', '#79a7b8']
const yi1 = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(1)}亿`
const yi0 = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(0)}亿`

// 双向横条(今日全景用)
function RankBars({ items, field }: { items: SectorItem[]; field: 'net' | 'net5' }) {
  const max = Math.max(...items.map((i) => Math.abs(i[field])), 0.01)
  return (
    <div className="sf-rank">
      {items.map((it) => {
        const v = it[field], w = (Math.abs(v) / max) * 100
        return (
          <div className="sf-row" key={it.name}>
            <span className="sf-name" title={it.name}>{it.name}</span>
            <div className="sf-track"><div className="sf-bar" style={{ [v >= 0 ? 'left' : 'right']: '50%', width: `${w / 2}%`, background: v >= 0 ? 'var(--rise)' : 'var(--fall)' } as any} /></div>
            <span className={`sf-amt ${v >= 0 ? 'up' : 'down'}`}>{yi1(v)}</span>
          </div>
        )
      })}
    </div>
  )
}

function setup(cv: HTMLCanvasElement, h: number) {
  const dpr = Math.max(1, window.devicePixelRatio || 1)
  const w = cv.clientWidth || cv.parentElement?.clientWidth || 600
  cv.width = w * dpr; cv.height = h * dpr
  const x = cv.getContext('2d')!; x.scale(dpr, dpr)
  return { x, w, h }
}

export default function SectorAnalysis() {
  const [view, setView] = useState<View>('today')
  const [win, setWin] = useState(40)
  const [sf, setSf] = useState<SectorFlow | null>(null)      // 今日全景
  const [hist, setHist] = useState<SectorHistory | null>(null) // 历史矩阵(懒加载)
  const [histLoading, setHistLoading] = useState(false)
  const [tip, setTip] = useState<string>('')                  // 热力 hover 提示

  const treeRef = useRef<HTMLDivElement>(null)
  const heatRef = useRef<HTMLCanvasElement>(null)
  const cumRef = useRef<HTMLCanvasElement>(null)
  const rrgRef = useRef<HTMLCanvasElement>(null)

  // 今日全景:进页即拉
  useEffect(() => { fetchSectorFlow().then(setSf) }, [])
  // 历史矩阵:首次切到 heat/cum/rrg 才拉
  useEffect(() => {
    if ((view === 'heat' || view === 'cum' || view === 'rrg') && !hist && !histLoading) {
      setHistLoading(true); fetchSectorHistory().then((d) => { setHist(d); setHistLoading(false) })
    }
  }, [view, hist, histLoading])

  // ── 今日全景 treemap ──
  useEffect(() => {
    if (view !== 'today' || !treeRef.current || !sf) return
    const chart = echarts.init(treeRef.current)
    const rise = riseColor(), fall = fallColor(), border = cssVar('--bg') || '#0c0a07'
    const top = [...sf.industries].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, 40)
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' }, formatter: (p: any) => p.name.replace('\n', ' ') },
      series: [{
        type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false }, width: '100%', height: '100%', top: 2, left: 2, right: 2, bottom: 2,
        label: { color: '#0c0a07', fontSize: 11, fontWeight: 600, overflow: 'truncate' }, itemStyle: { borderColor: border, borderWidth: 2, gapWidth: 2 },
        data: top.map((i) => ({ name: `${i.name}\n${yi0(i.net)}`, value: Math.abs(i.net), itemStyle: { color: i.net >= 0 ? rise : fall } })),
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [view, sf])

  // ── 历史热力矩阵(全部行业)──
  useEffect(() => {
    if (view !== 'heat' || !heatRef.current || !hist) return
    const cv = heatRef.current
    const inds = hist.industries                      // 已按最终累计降序
    const N = Math.min(win, hist.dates.length)
    const dates = hist.dates.slice(-N)
    const rowH = 8, padL = 78, padT = 4, padB = 16, padR = 6
    const H = padT + padB + inds.length * rowH
    const s = setup(cv, H); const x = s.x, W = s.w
    const iw = W - padL - padR, cw = iw / N
    // 标度上限用 85 分位(而非绝对最大),否则少数极端值把多数格子压暗
    const absv: number[] = []
    for (const it of inds) for (const v of it.net.slice(-N)) if (v) absv.push(Math.abs(v))
    absv.sort((a, b) => a - b)
    const vmax = Math.max(0.01, absv.length ? absv[Math.floor(absv.length * 0.85)] : 0.01)
    const rise = riseColor(), fall = fallColor()
    const rgb = (hex: string) => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)]
    const [rr, rg, rb] = rgb(rise), [fr, fg, fb] = rgb(fall)
    for (let i = 0; i < inds.length; i++) {
      const net = inds[i].net.slice(-N)
      for (let d = 0; d < N; d++) {
        const v = net[d], t = Math.max(-1, Math.min(1, v / vmax)), a = 0.08 + 0.85 * Math.abs(t)
        x.fillStyle = v >= 0 ? `rgba(${rr},${rg},${rb},${a})` : `rgba(${fr},${fg},${fb},${a})`
        x.fillRect(padL + d * cw, padT + i * rowH, cw + 0.5, rowH - 0.5)
      }
      if (rowH >= 7) { x.fillStyle = '#bcae97'; x.font = '8.5px sans-serif'; x.textAlign = 'right'; x.textBaseline = 'middle'; x.fillText(inds[i].name.slice(0, 8), padL - 6, padT + i * rowH + rowH / 2) }
    }
    x.fillStyle = '#8a7e66'; x.font = '9.5px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'top'
    x.fillText(`${N}日前`, padL + cw * 2, H - 12); x.fillText('今日', padL + iw - cw * 2, H - 12)
    // hover
    const onMove = (e: MouseEvent) => {
      const rect = cv.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const i = Math.floor((my - padT) / rowH), d = Math.floor((mx - padL) / cw)
      if (i >= 0 && i < inds.length && d >= 0 && d < N) setTip(`${inds[i].name} · ${dates[d]} · ${yi1(inds[i].net.slice(-N)[d])}`)
      else setTip('')
    }
    cv.addEventListener('mousemove', onMove); cv.addEventListener('mouseleave', () => setTip(''))
    return () => { cv.removeEventListener('mousemove', onMove) }
  }, [view, hist, win])

  // ── 累计吸金曲线(top 12 by |最终累计|)──
  useEffect(() => {
    if (view !== 'cum' || !cumRef.current || !hist) return
    const cv = cumRef.current; const s = setup(cv, 300); const x = s.x, W = s.w, H = s.h
    const N = Math.min(win, hist.dates.length)
    const top = [...hist.industries].sort((a, b) => Math.abs(b.cum[b.cum.length - 1]) - Math.abs(a.cum[a.cum.length - 1])).slice(0, 12)
    // 每条线在窗口内的累计:以窗口起点为0(相对该窗口的净流入)
    const series = top.map((it) => { const seg = it.cum.slice(-N); const base = seg[0]; return { name: it.name, v: seg.map((c) => c - base) } })
    const padL = 44, padR = 74, padT = 10, padB = 22, iw = W - padL - padR, ih = H - padT - padB
    let mn = 0, mx = 0; for (const s2 of series) for (const v of s2.v) { mn = Math.min(mn, v); mx = Math.max(mx, v) }
    const X = (d: number) => padL + (d / (N - 1)) * iw, Y = (v: number) => padT + ih - ((v - mn) / (mx - mn || 1)) * ih
    x.strokeStyle = '#241d15'; x.lineWidth = 1; x.beginPath(); x.moveTo(padL, Y(0)); x.lineTo(W - padR, Y(0)); x.stroke()
    x.fillStyle = '#8a7e66'; x.font = '9px sans-serif'; x.textAlign = 'right'; x.textBaseline = 'middle'; x.fillText('0', padL - 4, Y(0))
    series.forEach((s2, k) => {
      x.strokeStyle = PAL[k % PAL.length]; x.lineWidth = k < 3 ? 2.2 : 1.3; x.beginPath()
      s2.v.forEach((v, d) => { const xx = X(d), yy = Y(v); d ? x.lineTo(xx, yy) : x.moveTo(xx, yy) }); x.stroke()
      const ly = Y(s2.v[s2.v.length - 1]); x.fillStyle = PAL[k % PAL.length]; x.beginPath(); x.arc(X(N - 1), ly, 2.4, 0, 7); x.fill()
      if (k < 8) { x.font = '10px sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle'; x.fillText(s2.name.slice(0, 6), W - padR + 5, ly) }
    })
    x.fillStyle = '#8a7e66'; x.font = '9.5px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'top'
    x.fillText(`${N}日前`, padL + 16, H - 12); x.fillText('今日', W - padR - 16, H - 12)
    const onR = () => { }; window.addEventListener('resize', onR); return () => window.removeEventListener('resize', onR)
  }, [view, hist, win])

  // ── 轮动 RRG(top 8 by |最终累计|)──
  useEffect(() => {
    if (view !== 'rrg' || !rrgRef.current || !hist) return
    const cv = rrgRef.current; const s = setup(cv, 380); const x = s.x, W = s.w, H = s.h
    const N = Math.min(win, hist.dates.length)
    const inds = hist.industries
    // 相对强度 rs[t] = 行业cum - 全市场均值cum;动量 = rs[t]-rs[t-K]。
    // 用【截面百分位排名】定位(而非绝对值),彻底抗离群、均匀散布到四象限:
    //   x = (rs 在全行业的百分位 - 0.5)*2 ∈ [-1,1];y 同理用动量百分位。
    const M = inds.length, T = hist.dates.length
    const mktAvg: number[] = []
    for (let t = 0; t < T; t++) { let sum = 0; for (const it of inds) sum += it.cum[t]; mktAvg.push(sum / M) }
    const K = 5
    const rsAt = (it: typeof inds[number], t: number) => it.cum[t] - mktAvg[t]
    const momAt = (it: typeof inds[number], t: number) => rsAt(it, t) - rsAt(it, t - K)
    // 预排序:每个 t 的全行业 rs / 动量 升序数组,用于求百分位
    const pct = (sorted: number[], v: number) => { let lo = 0, hi = sorted.length; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] < v) lo = m + 1; else hi = m } return sorted.length ? lo / sorted.length : 0.5 }
    const rsSort: Record<number, number[]> = {}, momSort: Record<number, number[]> = {}
    const start = Math.max(0, T - N)
    for (let t = Math.max(start, K); t < T; t++) {
      rsSort[t] = inds.map((it) => rsAt(it, t)).sort((a, b) => a - b)
      momSort[t] = inds.map((it) => momAt(it, t)).sort((a, b) => a - b)
    }
    // 选最强4 + 最弱4(按最新 rs),横跨领先↔落后,呈现完整轮动格局
    const byRs = [...inds].sort((a, b) => rsAt(b, T - 1) - rsAt(a, T - 1))
    const top = [...byRs.slice(0, 4), ...byRs.slice(-4)]
    const pts = top.map((it) => {
      const tail: [number, number][] = []
      for (let t = Math.max(start, K); t < T; t++) {
        tail.push([(pct(rsSort[t], rsAt(it, t)) - 0.5) * 2, (pct(momSort[t], momAt(it, t)) - 0.5) * 2])
      }
      return { name: it.name, tail: tail.slice(-5) }
    })
    const rng = 1 // 百分位 [-1,1]
    const pad = 40, iw = W - pad * 2, ih = H - pad * 2, cx = pad + iw / 2, cy = pad + ih / 2
    const X = (v: number) => cx + (v / rng) * (iw / 2) * 0.94, Y = (v: number) => cy - (v / rng) * (ih / 2) * 0.94
    // 象限底色
    const q: [string, number, number][] = [['rgba(207,111,93,.05)', cx, pad], ['rgba(138,114,56,.05)', cx, cy], ['rgba(111,174,134,.05)', pad, cy], ['rgba(123,167,176,.05)', pad, pad]]
    q.forEach(([c, qx, qy]) => { x.fillStyle = c; x.fillRect(qx, qy, iw / 2, ih / 2) })
    x.strokeStyle = '#2c2418'; x.lineWidth = 1; x.beginPath(); x.moveTo(cx, pad); x.lineTo(cx, pad + ih); x.moveTo(pad, cy); x.lineTo(pad + iw, cy); x.stroke()
    x.font = '11px sans-serif'; x.fillStyle = '#bcae97'; x.textBaseline = 'top'
    x.textAlign = 'right'; x.fillText('领先', pad + iw - 6, pad + 4); x.fillText('走弱', pad + iw - 6, pad + ih - 16)
    x.textAlign = 'left'; x.fillText('落后', pad + 6, pad + ih - 16); x.fillText('改善', pad + 6, pad + 4)
    x.fillStyle = '#8a7e66'; x.font = '9px sans-serif'; x.textAlign = 'center'; x.fillText('← 相对强度 →', cx, pad + ih + 12)
    pts.forEach((p, k) => {
      const col = PAL[k % PAL.length], tl = p.tail; if (!tl.length) return
      x.strokeStyle = col; x.lineWidth = 1.5; x.beginPath(); tl.forEach(([a, b], i) => { const xx = X(a), yy = Y(b); i ? x.lineTo(xx, yy) : x.moveTo(xx, yy) }); x.stroke()
      tl.forEach(([a, b], i) => { x.fillStyle = col; x.globalAlpha = 0.3 + 0.14 * i; x.beginPath(); x.arc(X(a), Y(b), 2, 0, 7); x.fill() }); x.globalAlpha = 1
      const [la, lb] = tl[tl.length - 1]; x.fillStyle = col; x.beginPath(); x.arc(X(la), Y(lb), 4.5, 0, 7); x.fill()
      x.fillStyle = '#f1e9da'; x.font = '11px sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle'; x.fillText(p.name.slice(0, 6), X(la) + 7, Y(lb))
    })
  }, [view, hist, win])

  const TABS: [View, string][] = [['today', '今日全景'], ['heat', '历史热力'], ['cum', '累计吸金'], ['rrg', '轮动 RRG']]
  const info = '板块主力净流入(东财行业,超大+大单)。今日全景=当日快照;历史热力=日期×行业矩阵(全部行业,红入绿出);累计吸金=各行业窗口内累计净流入曲线;轮动RRG=相对强度×动量+近5日尾巴。数据只反映各板块自身冷热与相对轮动,不表示资金在板块间转移。颜色随涨跌配色。纯展示,非投资建议。'

  return (
    <div className="card">
      <div className="sf-head">
        <h3>板块资金分析 · 行业 <InfoDot text={info} /></h3>
        <span className="muted" style={{ fontSize: 12 }}>{sf ? `${sf.industries.length} 个行业` : ''}{hist ? ` · 数据截至 ${hist.asof}` : sf ? ` · ${sf.asof}` : ''}</span>
      </div>

      <div className="sa-bar">
        <div className="seg">{TABS.map(([v, t]) => <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>{t}</button>)}</div>
        {view !== 'today' && <div className="win">{[20, 40, 60].map((d) => <button key={d} className={win === d ? 'on' : ''} onClick={() => setWin(d)}>{d}日</button>)}</div>}
      </div>

      {/* 今日全景 */}
      {view === 'today' && (!sf ? <div className="muted">加载中…</div> : <>
        <div className="sf-sub">全行业全景（面积=今日主力净额，颜色=方向）</div>
        <div ref={treeRef} style={{ height: 320 }} />
        <div className="sf-cols">
          <div><div className="sf-sub">今日主力净流入 · 前12</div><RankBars items={sf.industries.filter((i) => i.net > 0).slice(0, 12)} field="net" /></div>
          <div><div className="sf-sub">今日主力净流出 · 前12</div><RankBars items={[...sf.industries].filter((i) => i.net < 0).sort((a, b) => a.net - b.net).slice(0, 12)} field="net" /></div>
        </div>
        <div className="sf-sub" style={{ marginTop: 16 }}>持续吸金榜 · 近{sf.days}日累计 · 前12</div>
        <RankBars items={[...sf.industries].sort((a, b) => b.net5 - a.net5).slice(0, 12)} field="net5" />
      </>)}

      {/* 历史热力 */}
      {view === 'heat' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…（首次约 1 分钟，之后秒开）</div> : <>
        <div className="sf-sub">日期 × 行业 · 主力净流入热力（全部 {hist.industries.length} 行业，按累计排序，可滚动 · 红入绿出）<span className="sa-tip">{tip}</span></div>
        <div className="sa-heat-scroll"><canvas ref={heatRef} /></div>
      </>)}

      {/* 累计吸金 */}
      {view === 'cum' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…</div> : <>
        <div className="sf-sub">各行业累计主力净流入（近{win}日，以窗口起点为0）· 前12 · 线升=持续吸金</div>
        <canvas ref={cumRef} style={{ width: '100%' }} />
      </>)}

      {/* 轮动 RRG */}
      {view === 'rrg' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…</div> : <>
        <div className="sf-sub">板块相对轮动（X=相对强度 · Y=强度动量 · 尾巴=近5日路径）· 前8</div>
        <canvas ref={rrgRef} style={{ width: '100%' }} />
        <div className="legend" style={{ fontSize: 11, color: 'var(--ink-mute)', marginTop: 6 }}>点在「领先」且向右上=资金强且在增强;轮动通常顺时针:改善→领先→走弱→落后。仅相对轮动,非资金转移。</div>
      </>)}
    </div>
  )
}
