import { useEffect, useState } from 'react'
import { fetchSnapshot, runEngine, fetchVersion, fetchMeta, fetchWatchlist, setStar, getMarket, setMarket, fetchAltStatus, fetchFocus, type Market, type TickerMeta, type DroppedItem, type AltStatus } from './api'
import type { Snapshot, Holding } from './types'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Help from './pages/Help'
import StockDetail from './pages/StockDetail'
import Trends from './pages/Trends'
import News from './pages/News'
import RiskLight from './pages/RiskLight'
import MoneyFlowPage from './pages/MoneyFlowPage'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Modal from './components/Modal'
import { installFetchAuth, fetchMe, logout, changePassword, setColorPref, getColorScheme, type AuthUser, type ColorScheme } from './auth'

installFetchAuth() // 全局 fetch 带 token

// 深链:详情页用新标签打开(?stock=code&market=cn),避免点详情丢失列表 tab/分页/搜索状态。
// 启动时若带 stock 参数 → 直接进该股详情;market 参数需在首个 fetch 前写入全局市场。
const _boot = new URLSearchParams(typeof location !== 'undefined' ? location.search : '')
const _bootStock = _boot.get('stock') || ''
const _bootMarket = _boot.get('market')
if (_bootMarket === 'cn' || _bootMarket === 'us') setMarket(_bootMarket)

type View = 'signals' | 'positions' | 'trends' | 'news' | 'risklight' | 'moneyflow' | 'help' | 'admin'
const NAV: { key: View; label: string; adminOnly?: boolean; cnOnly?: boolean }[] = [
  { key: 'news', label: '今日要闻' },
  { key: 'signals', label: '策略信号' },
  { key: 'moneyflow', label: '资金流', cnOnly: true },
  { key: 'positions', label: '我的持仓' },
  { key: 'trends', label: '分析走势' },
  { key: 'help', label: '帮助说明' },
  { key: 'admin', label: '系统管理', adminOnly: true },
]

export default function App() {
  const [me, setMe] = useState<AuthUser | null>(null)
  const [authReady, setAuthReady] = useState(false)
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [ver, setVer] = useState('dev')
  const [err, setErr] = useState('')
  const [running, setRunning] = useState(false)
  const [view, setView] = useState<View>('news') // 默认进今日要闻页
  const [sel, setSel] = useState<string | null>(_bootStock || null) // 深链启动股(其余情况点行开新标签,当前标签 sel 恒 null)
  const [focusH, setFocusH] = useState<Holding | null>(null) // 非推荐股:/api/focus 重算的完整档位
  const [focusErr, setFocusErr] = useState('')
  const [droppedSel, setDroppedSel] = useState<DroppedItem | null>(null) // 掉出股详情(holding 来自掉出前 context)
  const [meta, setMeta] = useState<TickerMeta>({})
  const [watch, setWatch] = useState<Set<string>>(new Set())
  const [userMenu, setUserMenu] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const [market, setMarketState] = useState<Market>(getMarket())
  const [altStatus, setAltStatus] = useState<AltStatus | null>(null) // A股数据源健康(tushare token过期→红条)
  const [colorUp, setColorUp] = useState<ColorScheme>(getColorScheme()) // 涨跌配色(用户隔离)
  const isAdmin = me?.role === 'admin'

  // 切换涨跌配色:写回后端(用户隔离)+ 本地即时生效;重载确保图表(ECharts 已渲染色值)一并刷新
  const switchColor = async (v: ColorScheme) => {
    if (v === colorUp) return
    setColorUp(v)
    try { await setColorPref(v) } catch { /* 本地已生效,后端失败下次同步 */ }
    window.location.reload()
  }

  // 切换市场:设全局市场 → 重载快照/关注(元数据 us 用中文名映射,cn 用快照内 name)
  const switchMarket = async (m: Market) => {
    if (m === market) return
    if (m !== 'cn' && view === 'moneyflow') setView('signals') // 资金流仅A股,切美股回退
    setMarket(m); setMarketState(m); setSel(null); setDroppedSel(null); setSnap(null); setErr('')
    try { setSnap(await fetchSnapshot()) } catch (e: any) { setErr(String(e.message || e)) }
    loadWatch()
  }

  // 启动:查当前登录用户
  useEffect(() => {
    fetchMe().then((u) => { setMe(u); setAuthReady(true); setColorUp(getColorScheme()) })
    const onUnauth = () => setMe(null)
    window.addEventListener('sentinel-unauth', onUnauth)
    return () => window.removeEventListener('sentinel-unauth', onUnauth)
  }, [])

  const load = async () => {
    setErr('')
    try { setSnap(await fetchSnapshot()) } catch (e: any) { setErr(String(e.message || e)) }
  }
  const loadWatch = async () => setWatch(new Set((await fetchWatchlist()).filter((w) => w.starred).map((w) => w.ticker)))
  // 登录后加载 app 数据
  useEffect(() => {
    if (!me) return
    load(); fetchVersion().then((v) => setVer(v.version)); fetchMeta().then(setMeta); loadWatch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me])

  // A股数据源健康:仅 A股视图轮询(tushare 只影响 A股),每5分钟一次;非 A股清空
  useEffect(() => {
    if (!me || market !== 'cn') { setAltStatus(null); return }
    let alive = true
    const tick = () => fetchAltStatus().then((s) => { if (alive) setAltStatus(s) })
    tick()
    const id = setInterval(tick, 5 * 60 * 1000)
    return () => { alive = false; clearInterval(id) }
  }, [me, market])

  const toggleWatch = async (tk: string, on: boolean) => {
    await setStar(tk, on)
    await loadWatch()
    await load()   // ★关注=自选:关注的任意股(含板块tab里非持仓股)合并进快照→出现在自选列表
  }
  const recompute = async () => {
    setRunning(true); setErr('')
    try { await runEngine(true); await load() } catch (e: any) { setErr('重算失败：' + String(e.message || e)) }
    setRunning(false)
  }
  const goto = (v: View) => {
    setView(v); setSel(null); setDroppedSel(null)
    if (location.search) history.replaceState(null, '', location.pathname) // 清 ?stock,避免刷新又深链回详情
  }
  // 点股票 → 新标签打开详情(列表状态不丢);深链 URL 让新标签独立解析该股
  const openStock = (tk: string) => {
    const url = `${location.pathname}?stock=${encodeURIComponent(tk)}&market=${market}`
    window.open(url, '_blank', 'noopener')
  }
  // 深链/选中股:在推荐持仓里 → 直接用;否则(非推荐股)调 /api/focus 重算完整档位
  const holdingH = sel && snap ? snap.holdings.find((h) => h.ticker === sel) : null
  useEffect(() => {
    if (!sel || !snap) return
    if (snap.holdings.some((h) => h.ticker === sel)) { setFocusH(null); setFocusErr(''); return }
    let alive = true
    setFocusH(null); setFocusErr('')
    fetchFocus(sel).then((r) => { if (alive) setFocusH(r.holding) })
      .catch((e) => { if (alive) setFocusErr(String(e.message || e)) })
    return () => { alive = false }
  }, [sel, snap])
  const detailH = holdingH || (sel && focusH && focusH.ticker === sel ? focusH : null)
  const inDetail = !!sel || !!droppedSel
  // 掉出股详情:holding 用掉出前最后一天的 context(页面会标注这是掉出前数据)
  const droppedH: Holding | null = droppedSel ? (() => { try { return JSON.parse(droppedSel.context) } catch { return null } })() : null

  if (!authReady) return <div className="login-wrap"><div className="muted">加载中…</div></div>
  if (!me) return <Login onLogin={(u) => { setMe(u); setColorUp(getColorScheme()) }} />

  const nav = NAV.filter((n) => (!n.adminOnly || isAdmin) && (!n.cnOnly || market === 'cn'))

  return (
    <>
      <div className="topbar">
        <div className="topbar-in">
          <div className="brand" onClick={() => goto('news')}>SENTINEL<span className="ver">{ver}</span></div>
          <div className="market-switch" title="切换市场:美股 / A股">
            <button className={market === 'us' ? 'ms-on' : ''} onClick={() => switchMarket('us')}>🇺🇸 美股</button>
            <button className={market === 'cn' ? 'ms-on' : ''} onClick={() => switchMarket('cn')}>🇨🇳 A股</button>
          </div>
          <nav className="nav">
            {nav.map((n) => (
              <a key={n.key} className={!inDetail && view === n.key ? 'active' : ''} onClick={() => goto(n.key)}>{n.label}</a>
            ))}
          </nav>
          <div className="topbar-right">
            {isAdmin && (
              <button className="ghost mini" onClick={recompute} disabled={running}
                title="重新跑一遍今天的策略引擎（约30秒，仅管理员）。">
                {running ? '重算中…' : '↻ 重算'}
              </button>
            )}
            <div className="user-menu">
              <button className="ghost mini" onClick={() => setUserMenu((v) => !v)}>👤 {me.name || me.email.split('@')[0]} ▾</button>
              {userMenu && (
                <div className="user-pop" onMouseLeave={() => setUserMenu(false)}>
                  <div className="user-pop-email">{me.email}{isAdmin && <span className="gold"> · 管理员</span>}</div>
                  <div className="pop-sec">涨跌配色</div>
                  <div className="color-toggle">
                    <button className={colorUp === 'red' ? 'on' : ''} onClick={() => switchColor('red')}>红涨绿跌</button>
                    <button className={colorUp === 'green' ? 'on' : ''} onClick={() => switchColor('green')}>绿涨红跌</button>
                  </div>
                  <button onClick={() => { setPwOpen(true); setUserMenu(false) }}>修改密码</button>
                  <button onClick={() => { logout(); setMe(null) }}>退出登录</button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="wrap">
        {market === 'cn' && altStatus && !altStatus.ok && (
          <div className="data-alert" role="alert">
            ⚠ {altStatus.source || '数据'}接口故障，相关指标可能未更新
          </div>
        )}
        <div className="sub" style={{ marginBottom: 14 }}>
          {market === 'cn' ? 'A股' : '美股'}{snap ? ` · 数据截至 ${snap.asof} 收盘` : '策略决策支持'} · 研究工具，非投资建议
        </div>

        {err && (
          <div className="card err-card">
            <b>⚠️ {err.includes('fetch') ? '连不上后端服务' : err}</b>
            <div className="muted" style={{ marginTop: 6 }}>
              {err.includes('无快照') ? '数据库还没有今天的快照。' + (isAdmin ? '点下面按钮生成（约30秒）。' : '请联系管理员生成。') : '请确认后端在运行。可重试。'}
            </div>
            <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
              <button className="ghost" onClick={load} disabled={running}>重试读取</button>
              {isAdmin && <button onClick={recompute} disabled={running}>{running ? '生成中…' : '重新运算生成快照'}</button>}
            </div>
          </div>
        )}

        {droppedH && droppedSel && <StockDetail h={droppedH} meta={meta} market={market} riskLight={snap?.risk_light} dropped={droppedSel} />}
        {/* 选中股(深链):在推荐里直接显示;非推荐股 focus 重算中显加载,失败显错 */}
        {!droppedH && sel && (detailH
          ? <StockDetail h={detailH} meta={meta} market={market} riskLight={snap?.risk_light} />
          : <div className="card"><div className="muted" style={{ padding: 20 }}>
              {focusErr ? `⚠ 无法加载 ${sel} 的详情:${focusErr}` : `⏳ 正在计算 ${sel} 的完整档位/概率(约几秒)…`}
            </div></div>)}
        {!droppedH && !inDetail && view === 'signals' && snap && <Dashboard snap={snap} meta={meta} watch={watch} onToggleWatch={toggleWatch} onSelect={openStock} onSelectDropped={setDroppedSel} onReload={async () => { await load(); await loadWatch() }} onOpenRiskLight={() => goto('risklight')} onOpenMoneyflow={() => goto('moneyflow')} />}
        {!droppedH && !inDetail && view === 'positions' && <Positions market={market} />}
        {!droppedH && !inDetail && view === 'trends' && <Trends meta={meta} watch={watch} market={market} />}
        {!droppedH && !inDetail && view === 'news' && <News market={market} />}
        {!droppedH && !inDetail && view === 'risklight' && <RiskLight initialMarket={market} onBack={() => goto('signals')} />}
        {!droppedH && !inDetail && view === 'moneyflow' && market === 'cn' && <MoneyFlowPage />}
        {!droppedH && !inDetail && view === 'help' && <Help market={market} />}
        {!droppedH && !inDetail && view === 'admin' && isAdmin && <Admin />}
        {!droppedH && !inDetail && view === 'signals' && !snap && !err && <div className="card">加载中…</div>}

        <div className="disc">
          研究工具，非投资建议。档位=趋势状态（松·只减防御跟法，只减不追涨）；概率带=波动范围的校准估计（非方向预言）；
          风险灯=波动目标体制闸。方向不可预测，本系统为决策支持，手动执行，盈亏自负。不清楚名词请看「帮助说明」。
        </div>
      </div>

      {pwOpen && <ChangePw onClose={() => setPwOpen(false)} />}
    </>
  )
}

function ChangePw({ onClose }: { onClose: () => void }) {
  const [cur, setCur] = useState(''); const [n1, setN1] = useState(''); const [n2, setN2] = useState('')
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const submit = async () => {
    setErr(''); setMsg('')
    if (n1.length < 6) { setErr('新密码至少6位'); return }
    if (n1 !== n2) { setErr('两次新密码不一致'); return }
    try { await changePassword(cur, n1); setMsg('密码已修改'); setTimeout(onClose, 800) }
    catch (e: any) { setErr(String(e.message || e)) }
  }
  return (
    <Modal title="修改密码" onClose={onClose}>
      <div className="admin-grid" style={{ gridTemplateColumns: '1fr' }}>
        <label>当前密码<input type="password" value={cur} onChange={(e) => setCur(e.target.value)} /></label>
        <label>新密码(≥6位)<input type="password" value={n1} onChange={(e) => setN1(e.target.value)} /></label>
        <label>确认新密码<input type="password" value={n2} onChange={(e) => setN2(e.target.value)} /></label>
      </div>
      {err && <div className="down" style={{ fontSize: 13, marginTop: 8 }}>{err}</div>}
      {msg && <div className="up" style={{ fontSize: 13, marginTop: 8 }}>{msg}</div>}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="ghost" onClick={onClose}>取消</button>
        <button className="primary" onClick={submit}>确认修改</button>
      </div>
    </Modal>
  )
}
