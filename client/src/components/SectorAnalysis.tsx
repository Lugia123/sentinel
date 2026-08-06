import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchSectorFlow, fetchSectorHistory, type SectorFlow, type SectorItem, type SectorHistory } from '../api'
import { InfoDot, riseColor, fallColor, cssVar } from '../ui'

// 板块资金分析 —— 一卡四视图(纯展示,不进策略):今日全景 / 历史热力 / 累计吸金 / 轮动RRG。
// 交互:视图/时间窗分段切换、行业数量筛选(按当前净额排位)、canvas hover 浮层。
// 颜色:热力随涨跌配色(红入绿出);曲线/RRG 用分类色(非涨跌语意)。
type View = 'today' | 'heat' | 'cum' | 'rrg'
const PAL = ['#e6c878', '#7ba7b0', '#9a8ec4', '#d19a66', '#84b6c4', '#c8a253', '#b98ec4', '#8ab0a0', '#cbb26a', '#79a7b8', '#d3a95f', '#93b5c6']
const yi1 = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(1)}亿`
const yi0 = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(0)}亿`

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

type Tip = { show: boolean; x: number; y: number; html: string }

export default function SectorAnalysis() {
  const [view, setView] = useState<View>('today')
  const [win, setWin] = useState(40)
  const [nMode, setNMode] = useState<'top' | 'range'>('top')
  const [topN, setTopN] = useState(30)
  const [lo, setLo] = useState(1)
  const [hi, setHi] = useState(30)
  const [sf, setSf] = useState<SectorFlow | null>(null)
  const [hist, setHist] = useState<SectorHistory | null>(null)
  const [histLoading, setHistLoading] = useState(false)
  const [tip, setTip] = useState<Tip>({ show: false, x: 0, y: 0, html: '' })

  const wrapRef = useRef<HTMLDivElement>(null)
  const treeRef = useRef<HTMLDivElement>(null)
  const heatRef = useRef<HTMLCanvasElement>(null)
  const cumRef = useRef<HTMLCanvasElement>(null)
  const rrgRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => { fetchSectorFlow().then(setSf) }, [])
  useEffect(() => {
    if ((view === 'heat' || view === 'cum' || view === 'rrg') && !hist && !histLoading) {
      setHistLoading(true); fetchSectorHistory().then((d) => { setHist(d); setHistLoading(false) })
    }
  }, [view, hist, histLoading])

  // 按【当前时刻净额】排位后取子集(前N 或 第lo-hi名)。curOf 取当日净额。
  function pick<T>(list: T[], curOf: (t: T) => number): T[] {
    const ranked = [...list].sort((a, b) => curOf(b) - curOf(a)) // 净额降序:#1=最大流入
    if (nMode === 'range') { const a = Math.max(1, Math.min(lo, hi)), b = Math.max(lo, hi); return ranked.slice(a - 1, b) }
    return ranked.slice(0, topN)
  }
  // hover 浮层坐标(相对卡片)
  const showTip = (e: MouseEvent, html: string) => {
    const r = wrapRef.current?.getBoundingClientRect(); if (!r) return
    setTip({ show: true, x: e.clientX - r.left, y: e.clientY - r.top, html })
  }
  const hideTip = () => setTip((t) => (t.show ? { ...t, show: false } : t))

  // ── 今日全景 treemap ──
  useEffect(() => {
    if (view !== 'today' || !treeRef.current || !sf) return
    const chart = echarts.init(treeRef.current)
    const rise = riseColor(), fall = fallColor(), border = cssVar('--bg') || '#0c0a07'
    const sel = pick(sf.industries, (i) => i.net)
    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { backgroundColor: '#1f1913', borderColor: '#2c2418', textStyle: { color: '#f1e9da' }, formatter: (p: any) => p.name.replace('\n', ' ') },
      series: [{
        type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false }, width: '100%', height: '100%', top: 2, left: 2, right: 2, bottom: 2,
        label: { color: '#0c0a07', fontSize: 11, fontWeight: 600, overflow: 'truncate' }, itemStyle: { borderColor: border, borderWidth: 2, gapWidth: 2 },
        data: sel.map((i) => ({ name: `${i.name}\n${yi0(i.net)}`, value: Math.abs(i.net) || 0.01, itemStyle: { color: i.net >= 0 ? rise : fall } })),
      }],
    })
    const onR = () => chart.resize(); window.addEventListener('resize', onR)
    return () => { window.removeEventListener('resize', onR); chart.dispose() }
  }, [view, sf, nMode, topN, lo, hi])

  // ── 历史热力矩阵 ──
  useEffect(() => {
    if (view !== 'heat' || !heatRef.current || !hist) return
    const cv = heatRef.current
    const N = Math.min(win, hist.dates.length)
    const last = hist.dates.length - 1
    const inds = pick(hist.industries, (it) => it.net[last])   // 按当前净额排位
    const dates = hist.dates.slice(-N)
    const rowH = Math.max(8, Math.min(20, Math.floor(520 / inds.length)))
    const font = rowH >= 15 ? 12 : rowH >= 11 ? 11 : rowH >= 9 ? 10 : 8.5
    const padL = 92, padT = 4, padB = 16, padR = 8
    const H = padT + padB + inds.length * rowH
    const s = setup(cv, H); const x = s.x, W = s.w
    const iw = W - padL - padR, cw = iw / N
    // 85 分位标度
    const absv: number[] = []
    for (const it of inds) for (const v of it.net.slice(-N)) if (v) absv.push(Math.abs(v))
    absv.sort((a, b) => a - b)
    const vmax = Math.max(0.01, absv.length ? absv[Math.floor(absv.length * 0.85)] : 0.01)
    const rise = riseColor(), fall = fallColor()
    const rgb = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]
    const [rr, rg, rb] = rgb(rise), [fr, fg, fb] = rgb(fall)
    for (let i = 0; i < inds.length; i++) {
      const net = inds[i].net.slice(-N)
      for (let d = 0; d < N; d++) {
        const v = net[d], t = Math.max(-1, Math.min(1, v / vmax)), a = 0.06 + 0.9 * Math.abs(t)
        x.fillStyle = v >= 0 ? `rgba(${rr},${rg},${rb},${a})` : `rgba(${fr},${fg},${fb},${a})`
        x.fillRect(padL + d * cw, padT + i * rowH, cw + 0.4, rowH - 0.6)
      }
      x.fillStyle = '#c9bda3'; x.font = `${font}px sans-serif`; x.textAlign = 'right'; x.textBaseline = 'middle'
      x.fillText(inds[i].name.length > 9 ? inds[i].name.slice(0, 9) : inds[i].name, padL - 6, padT + i * rowH + rowH / 2)
    }
    x.fillStyle = '#8a7e66'; x.font = '9.5px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'top'
    x.fillText(`${N}日前`, padL + cw * 2, H - 12); x.fillText('今日', padL + iw - cw * 2, H - 12)
    const onMove = (e: MouseEvent) => {
      const rect = cv.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const i = Math.floor((my - padT) / rowH), d = Math.floor((mx - padL) / cw)
      if (i >= 0 && i < inds.length && d >= 0 && d < N) {
        const v = inds[i].net.slice(-N)[d]
        showTip(e, `<b>${inds[i].name}</b><br/>${dates[d]}<br/><span style="color:${v >= 0 ? rise : fall}">主力净额 ${yi1(v)}</span>`)
      } else hideTip()
    }
    cv.addEventListener('mousemove', onMove); cv.addEventListener('mouseleave', hideTip)
    return () => { cv.removeEventListener('mousemove', onMove); cv.removeEventListener('mouseleave', hideTip) }
  }, [view, hist, win, nMode, topN, lo, hi])

  // ── 累计吸金曲线 ──
  useEffect(() => {
    if (view !== 'cum' || !cumRef.current || !hist) return
    const cv = cumRef.current; const s = setup(cv, 320); const x = s.x, W = s.w, H = s.h
    const N = Math.min(win, hist.dates.length)
    const last = hist.dates.length - 1
    const sel = pick(hist.industries, (it) => it.net[last])
    const series = sel.map((it) => { const seg = it.cum.slice(-N); const base = seg[0]; return { name: it.name, v: seg.map((c) => c - base) } })
    const padL = 46, padR = 92, padT = 12, padB = 24, iw = W - padL - padR, ih = H - padT - padB
    let mn = 0, mx = 0; for (const s2 of series) for (const v of s2.v) { mn = Math.min(mn, v); mx = Math.max(mx, v) }
    const X = (d: number) => padL + (d / (N - 1)) * iw, Y = (v: number) => padT + ih - ((v - mn) / (mx - mn || 1)) * ih
    // 网格
    x.strokeStyle = '#241d15'; x.lineWidth = 1
    x.beginPath(); x.moveTo(padL, Y(0)); x.lineTo(W - padR, Y(0)); x.stroke()
    x.fillStyle = '#8a7e66'; x.font = '9px sans-serif'; x.textAlign = 'right'; x.textBaseline = 'middle'; x.fillText('0亿', padL - 4, Y(0))
    const labelSlots: number[] = []
    series.forEach((s2, k) => {
      const col = PAL[k % PAL.length]
      x.strokeStyle = col; x.lineWidth = k < 3 ? 2.2 : 1.3; x.beginPath()
      s2.v.forEach((v, d) => { const xx = X(d), yy = Y(v); d ? x.lineTo(xx, yy) : x.moveTo(xx, yy) }); x.stroke()
      let ly = Y(s2.v[s2.v.length - 1])
      while (labelSlots.some((s3) => Math.abs(s3 - ly) < 11)) ly += 11  // 防标签重叠
      labelSlots.push(ly)
      x.fillStyle = col; x.beginPath(); x.arc(X(N - 1), Y(s2.v[s2.v.length - 1]), 2.4, 0, 7); x.fill()
      x.font = '10.5px sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle'
      x.fillText(`${s2.name.length > 6 ? s2.name.slice(0, 6) : s2.name} ${yi0(s2.v[s2.v.length - 1])}`, W - padR + 5, ly)
    })
    x.fillStyle = '#8a7e66'; x.font = '9.5px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'top'
    x.fillText(`${N}日前`, padL + 16, H - 13); x.fillText('今日', W - padR - 16, H - 13)
    const dates = hist.dates.slice(-N)
    const onMove = (e: MouseEvent) => {
      const rect = cv.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top
      if (mx < padL || mx > W - padR) { hideTip(); return }
      const d = Math.max(0, Math.min(N - 1, Math.round((mx - padL) / iw * (N - 1))))
      // 找最近的线
      let best = -1, bd = 1e9
      series.forEach((s2, k) => { const dy = Math.abs(Y(s2.v[d]) - my); if (dy < bd) { bd = dy; best = k } })
      if (best < 0) { hideTip(); return }
      const rows = series.map((s2, k) => `<span style="color:${PAL[k % PAL.length]}">${k === best ? '▶ ' : ''}${s2.name}: ${yi1(s2.v[d])}</span>`).slice(0, 12).join('<br/>')
      showTip(e, `<b>${dates[d]}</b><br/>${rows}`)
    }
    cv.addEventListener('mousemove', onMove); cv.addEventListener('mouseleave', hideTip)
    return () => { cv.removeEventListener('mousemove', onMove); cv.removeEventListener('mouseleave', hideTip) }
  }, [view, hist, win, nMode, topN, lo, hi])

  // ── 轮动 RRG ──
  useEffect(() => {
    if (view !== 'rrg' || !rrgRef.current || !hist) return
    const cv = rrgRef.current; const s = setup(cv, 400); const x = s.x, W = s.w, H = s.h
    const N = Math.min(win, hist.dates.length)
    const inds = hist.industries, M = inds.length, T = hist.dates.length, K = 5
    const mktAvg: number[] = []
    for (let t = 0; t < T; t++) { let sum = 0; for (const it of inds) sum += it.cum[t]; mktAvg.push(sum / M) }
    const rsAt = (it: typeof inds[number], t: number) => it.cum[t] - mktAvg[t]
    const momAt = (it: typeof inds[number], t: number) => rsAt(it, t) - rsAt(it, t - K)
    // 去极值标准化:对全行业 rs/动量按 5~95 分位截尾后求均值/标准差 → z,再夹到 ±2.6。散布不被离群压扁。
    const winsorZ = (vals: number[]) => {
      const s2 = [...vals].sort((a, b) => a - b); const p5 = s2[Math.floor(s2.length * 0.05)], p95 = s2[Math.floor(s2.length * 0.95)]
      const cl = vals.map((v) => Math.max(p5, Math.min(p95, v)))
      const m = cl.reduce((a, b) => a + b, 0) / cl.length
      const sd = Math.sqrt(cl.reduce((a, b) => a + (b - m) * (b - m), 0) / cl.length) || 1
      return (v: number) => Math.max(-2.6, Math.min(2.6, (Math.max(p5, Math.min(p95, v)) - m) / sd)) / 2.6
    }
    // 选股:按当前净额取子集(跨流入/流出),数量随筛选
    const last = T - 1
    const sel = pick(inds, (it) => Math.abs(it.net[last]))  // RRG 用 |当前净额| 取最活跃
    const zx: Record<number, (v: number) => number> = {}, zy: Record<number, (v: number) => number> = {}
    const start = Math.max(0, T - N)
    for (let t = Math.max(start, K); t < T; t++) { zx[t] = winsorZ(inds.map((it) => rsAt(it, t))); zy[t] = winsorZ(inds.map((it) => momAt(it, t))) }
    const pts = sel.map((it) => {
      const tail: [number, number][] = []
      for (let t = Math.max(start, K); t < T; t++) tail.push([zx[t](rsAt(it, t)), zy[t](momAt(it, t))])
      return { name: it.name, tail: tail.slice(-5), net: it.net[last] }
    })
    const pad = 40, iw = W - pad * 2, ih = H - pad * 2, cx = pad + iw / 2, cy = pad + ih / 2
    const X = (v: number) => cx + v * (iw / 2) * 0.92, Y = (v: number) => cy - v * (ih / 2) * 0.92
    const q: [string, number, number][] = [['rgba(207,111,93,.05)', cx, pad], ['rgba(138,114,56,.05)', cx, cy], ['rgba(111,174,134,.05)', pad, cy], ['rgba(123,167,176,.05)', pad, pad]]
    q.forEach(([c, qx, qy]) => { x.fillStyle = c; x.fillRect(qx, qy, iw / 2, ih / 2) })
    x.strokeStyle = '#2c2418'; x.lineWidth = 1; x.beginPath(); x.moveTo(cx, pad); x.lineTo(cx, pad + ih); x.moveTo(pad, cy); x.lineTo(pad + iw, cy); x.stroke()
    x.font = '11px sans-serif'; x.fillStyle = '#bcae97'; x.textBaseline = 'top'
    x.textAlign = 'right'; x.fillText('领先', pad + iw - 6, pad + 4); x.fillText('走弱', pad + iw - 6, pad + ih - 16)
    x.textAlign = 'left'; x.fillText('落后', pad + 6, pad + ih - 16); x.fillText('改善', pad + 6, pad + 4)
    x.fillStyle = '#8a7e66'; x.font = '9px sans-serif'; x.textAlign = 'center'; x.fillText('← 相对强度 →', cx, pad + ih + 14)
    const dots: { x: number; y: number; name: string; net: number }[] = []
    pts.forEach((p, k) => {
      const col = PAL[k % PAL.length], tl = p.tail; if (!tl.length) return
      x.strokeStyle = col; x.lineWidth = 1.5; x.beginPath(); tl.forEach(([a, b], i) => { const xx = X(a), yy = Y(b); i ? x.lineTo(xx, yy) : x.moveTo(xx, yy) }); x.stroke()
      tl.forEach(([a, b], i) => { x.fillStyle = col; x.globalAlpha = 0.28 + 0.14 * i; x.beginPath(); x.arc(X(a), Y(b), 2, 0, 7); x.fill() }); x.globalAlpha = 1
      const [la, lb] = tl[tl.length - 1]; const dx = X(la), dy = Y(lb)
      x.fillStyle = col; x.beginPath(); x.arc(dx, dy, 4.5, 0, 7); x.fill()
      x.fillStyle = '#f1e9da'; x.font = '11px sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle'
      x.fillText(p.name.length > 6 ? p.name.slice(0, 6) : p.name, dx + 7, dy)
      dots.push({ x: dx, y: dy, name: p.name, net: p.net })
    })
    const onMove = (e: MouseEvent) => {
      const rect = cv.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top
      let best: typeof dots[number] | null = null, bd = 18 * 18
      for (const d of dots) { const dd = (d.x - mx) ** 2 + (d.y - my) ** 2; if (dd < bd) { bd = dd; best = d } }
      if (!best) { hideTip(); return }
      const quad = best.x >= cx ? (best.y <= cy ? '领先' : '走弱') : (best.y <= cy ? '改善' : '落后')
      showTip(e, `<b>${best.name}</b><br/>象限 ${quad}<br/><span style="color:${best.net >= 0 ? riseColor() : fallColor()}">今日净额 ${yi1(best.net)}</span>`)
    }
    cv.addEventListener('mousemove', onMove); cv.addEventListener('mouseleave', hideTip)
    return () => { cv.removeEventListener('mousemove', onMove); cv.removeEventListener('mouseleave', hideTip) }
  }, [view, hist, win, nMode, topN, lo, hi])

  const TABS: [View, string][] = [['today', '今日全景'], ['heat', '历史热力'], ['cum', '累计吸金'], ['rrg', '轮动 RRG']]
  const total = sf ? sf.industries.length : (hist ? hist.industries.length : 0)
  const info = '板块主力净流入(东财行业,超大+大单)。今日全景=当日快照;历史热力=日期×行业矩阵(红入绿出);累计吸金=窗口内累计净流入曲线;轮动RRG=相对强度×动量+近5日尾巴。行业按【当前净额】排位,可调数量/范围。数据只反映各板块自身冷热与相对轮动,不表示资金在板块间转移。颜色随涨跌配色。纯展示,非投资建议。'

  return (
    <div className="card sa-wrap" ref={wrapRef}>
      <div className="sf-head">
        <h3>板块资金分析 · 行业 <InfoDot text={info} /></h3>
        <span className="muted" style={{ fontSize: 12 }}>{total ? `${total} 个行业` : ''}{hist ? ` · 截至 ${hist.asof}` : sf ? ` · ${sf.asof}` : ''}</span>
      </div>

      <div className="sa-bar">
        <div className="seg">{TABS.map(([v, t]) => <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>{t}</button>)}</div>
        {view !== 'today' && <div className="seg sm">{[20, 40, 60].map((d) => <button key={d} className={win === d ? 'on' : ''} onClick={() => setWin(d)}>{d}日</button>)}</div>}
      </div>

      {/* 行业数量/范围筛选(按当前净额排位)*/}
      <div className="sa-filter">
        <span className="sa-flabel">显示</span>
        <div className="seg sm">
          {[20, 30, 50, 100].map((n) => <button key={n} className={nMode === 'top' && topN === n ? 'on' : ''} onClick={() => { setNMode('top'); setTopN(n) }}>前{n}</button>)}
          <button className={nMode === 'top' && topN >= 9999 ? 'on' : ''} onClick={() => { setNMode('top'); setTopN(9999) }}>全部</button>
        </div>
        <span className="sa-range">
          第 <input type="number" min={1} value={lo} onChange={(e) => setLo(+e.target.value || 1)} />
          – <input type="number" min={1} value={hi} onChange={(e) => setHi(+e.target.value || 1)} /> 名
          <button className={nMode === 'range' ? 'on' : ''} onClick={() => setNMode('range')}>应用</button>
        </span>
        <span className="sa-fhint">按当前净额排位</span>
      </div>

      {view === 'today' && (!sf ? <div className="muted">加载中…</div> : <>
        <div className="sf-sub">全行业全景（面积=今日主力净额，颜色=方向）· 悬停看板块</div>
        <div ref={treeRef} style={{ height: 340 }} />
      </>)}

      {view === 'heat' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…（首次约 1 分钟，之后秒开）</div> : <>
        <div className="sf-sub">日期 × 行业 · 主力净流入热力（红入绿出，85分位标度）· 悬停看数值</div>
        <div className="sa-heat-scroll"><canvas ref={heatRef} /></div>
      </>)}

      {view === 'cum' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…</div> : <>
        <div className="sf-sub">各行业累计主力净流入（近{win}日，以窗口起点为0）· 线升=持续吸金 · 悬停看某日各行业</div>
        <canvas ref={cumRef} style={{ width: '100%' }} />
      </>)}

      {view === 'rrg' && (histLoading || !hist ? <div className="muted">历史矩阵加载中…</div> : <>
        <div className="sf-sub">板块相对轮动（X=相对强度 · Y=强度动量 · 尾巴=近5日路径）· 悬停看板块</div>
        <canvas ref={rrgRef} style={{ width: '100%' }} />
        <div className="legend" style={{ fontSize: 11, color: 'var(--ink-mute)', marginTop: 6 }}>点在「领先」且向右上=资金强且在增强;轮动通常顺时针:改善→领先→走弱→落后。仅相对轮动,非资金转移。</div>
      </>)}

      {tip.show && <div className="sa-tip-box" style={{ left: tip.x, top: tip.y }} dangerouslySetInnerHTML={{ __html: tip.html }} />}
    </div>
  )
}
