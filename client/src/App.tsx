import { useEffect, useState } from 'react'
import { fetchSnapshot, runEngine, fetchVersion, fetchMeta, fetchWatchlist, addWatch, removeWatch, fetchFocus, type TickerMeta } from './api'
import type { Snapshot, Holding } from './types'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Help from './pages/Help'
import StockDetail from './pages/StockDetail'
import Trends from './pages/Trends'
import Login from './pages/Login'
import Admin from './pages/Admin'
import Modal from './components/Modal'
import { installFetchAuth, fetchMe, logout, changePassword, type AuthUser } from './auth'

installFetchAuth() // 全局 fetch 带 token

type View = 'signals' | 'positions' | 'trends' | 'help' | 'admin'
const NAV: { key: View; label: string; adminOnly?: boolean }[] = [
  { key: 'signals', label: '策略信号' },
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
  const [view, setView] = useState<View>('signals')
  const [sel, setSel] = useState<string | null>(null)
  const [meta, setMeta] = useState<TickerMeta>({})
  const [watch, setWatch] = useState<Set<string>>(new Set())
  const [focusH, setFocusH] = useState<Holding | null>(null)
  const [focusErr, setFocusErr] = useState('')
  const [userMenu, setUserMenu] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const isAdmin = me?.role === 'admin'

  // 启动:查当前登录用户
  useEffect(() => {
    fetchMe().then((u) => { setMe(u); setAuthReady(true) })
    const onUnauth = () => setMe(null)
    window.addEventListener('sentinel-unauth', onUnauth)
    return () => window.removeEventListener('sentinel-unauth', onUnauth)
  }, [])

  const load = async () => {
    setErr('')
    try { setSnap(await fetchSnapshot()) } catch (e: any) { setErr(String(e.message || e)) }
  }
  const loadWatch = async () => setWatch(new Set((await fetchWatchlist()).map((w) => w.ticker)))
  // 登录后加载 app 数据
  useEffect(() => {
    if (!me) return
    load(); fetchVersion().then((v) => setVer(v.version)); fetchMeta().then(setMeta); loadWatch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me])

  const toggleWatch = async (tk: string, on: boolean) => {
    if (on) await addWatch(tk); else await removeWatch(tk)
    await loadWatch()
  }
  const viewCustom = async (tk: string) => {
    setFocusErr(''); setFocusH(null)
    try {
      const res = await fetchFocus(tk)
      setFocusH(res.holding)
      await addWatch(tk, 'user'); await loadWatch()
    } catch (e: any) { setFocusErr(String(e.message || e)) }
  }
  const recompute = async () => {
    setRunning(true); setErr('')
    try { await runEngine(true); await load() } catch (e: any) { setErr('重算失败：' + String(e.message || e)) }
    setRunning(false)
  }
  const goto = (v: View) => { setView(v); setSel(null); setFocusH(null) }
  const selHolding = sel && snap ? snap.holdings.find((h) => h.ticker === sel) : null
  const detailH = focusH || selHolding

  if (!authReady) return <div className="login-wrap"><div className="muted">加载中…</div></div>
  if (!me) return <Login onLogin={(u) => setMe(u)} />

  const nav = NAV.filter((n) => !n.adminOnly || isAdmin)

  return (
    <>
      <div className="topbar">
        <div className="topbar-in">
          <div className="brand" onClick={() => goto('signals')}>SENTINEL<span className="ver">{ver}</span></div>
          <nav className="nav">
            {nav.map((n) => (
              <a key={n.key} className={!detailH && view === n.key ? 'active' : ''} onClick={() => goto(n.key)}>{n.label}</a>
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
                  <button onClick={() => { setPwOpen(true); setUserMenu(false) }}>修改密码</button>
                  <button onClick={() => { logout(); setMe(null) }}>退出登录</button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="wrap">
        <div className="sub" style={{ marginBottom: 14 }}>
          {snap ? `数据截至 ${snap.asof} 收盘` : '美股策略决策支持'} · 研究工具，非投资建议
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

        {focusErr && <div className="card err-card"><b>⚠️ {focusErr}</b></div>}
        {detailH && <StockDetail h={detailH} meta={meta} />}
        {!detailH && view === 'signals' && snap && <Dashboard snap={snap} meta={meta} watch={watch} onToggleWatch={toggleWatch} onSelect={setSel} onCustom={viewCustom} />}
        {!detailH && view === 'positions' && <Positions />}
        {!detailH && view === 'trends' && <Trends meta={meta} watch={watch} />}
        {!detailH && view === 'help' && <Help />}
        {!detailH && view === 'admin' && isAdmin && <Admin />}
        {!detailH && view === 'signals' && !snap && !err && <div className="card">加载中…</div>}

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
