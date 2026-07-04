import { useEffect, useState } from 'react'
import { fetchSnapshot, runEngine, fetchVersion } from './api'
import type { Snapshot } from './types'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Help from './pages/Help'
import StockDetail from './pages/StockDetail'

type View = 'signals' | 'positions' | 'help'

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [ver, setVer] = useState('dev')
  const [err, setErr] = useState('')
  const [running, setRunning] = useState(false)
  const [view, setView] = useState<View>('signals')
  const [sel, setSel] = useState<string | null>(null) // 选中的详情股

  const load = async () => {
    setErr('')
    try { setSnap(await fetchSnapshot()) }
    catch (e: any) { setErr(String(e.message || e)) }
  }
  useEffect(() => { load(); fetchVersion().then((v) => setVer(v.version)) }, [])

  const recompute = async () => {
    setRunning(true); setErr('')
    try { await runEngine(true); await load() }
    catch (e: any) { setErr('重算失败：' + String(e.message || e)) }
    setRunning(false)
  }

  const selHolding = sel && snap ? snap.holdings.find((h) => h.ticker === sel) : null

  return (
    <div className="wrap">
      <div className="header">
        <div>
          <div className="title" onClick={() => { setView('signals'); setSel(null) }} style={{ cursor: 'pointer' }}>
            Sentinel<span className="ver">{ver}</span>
          </div>
          <div className="sub">{snap ? `数据截至 ${snap.asof} 收盘` : '美股策略决策支持'} · 研究工具，非投资建议</div>
        </div>
        <button onClick={recompute} disabled={running} title="重新跑一遍今天的策略引擎（约30秒），拉最新数据重算">
          {running ? '重算中…约30秒' : '↻ 重新运算今日策略'}
        </button>
      </div>

      {!sel && (
        <div className="tabs">
          <button className={view === 'signals' ? 'active' : ''} onClick={() => setView('signals')}>策略信号</button>
          <button className={view === 'positions' ? 'active' : ''} onClick={() => setView('positions')}>我的持仓</button>
          <button className={view === 'help' ? 'active' : ''} onClick={() => setView('help')}>帮助说明</button>
        </div>
      )}

      {err && (
        <div className="card err-card">
          <b>⚠️ {err.includes('Failed to fetch') || err.includes('fetch') ? '连不上后端服务' : err}</b>
          <div className="muted" style={{ marginTop: 6 }}>
            {err.includes('无快照')
              ? '数据库还没有今天的快照。点下面按钮生成（约30秒）。'
              : '请确认后端在运行（脚本 scripts/run-dev.sh 会自动起）。可重试。'}
          </div>
          <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
            <button onClick={load} disabled={running}>重试读取</button>
            <button className="ghost" onClick={recompute} disabled={running}>{running ? '生成中…' : '重新运算生成快照'}</button>
          </div>
        </div>
      )}

      {selHolding && <StockDetail h={selHolding} onBack={() => setSel(null)} />}

      {!sel && view === 'signals' && snap && <Dashboard snap={snap} onSelect={setSel} />}
      {!sel && view === 'positions' && <Positions />}
      {!sel && view === 'help' && <Help />}
      {!sel && view === 'signals' && !snap && !err && <div className="card">加载中…</div>}

      <div className="disc">
        研究工具，非投资建议。档位=趋势状态（松·只减防御跟法，只减不追涨）；概率带=波动范围的校准估计（非方向预言）；
        风险灯=波动目标体制闸。方向不可预测，本系统为决策支持，手动执行，盈亏自负。不清楚名词请看「帮助说明」。
      </div>
    </div>
  )
}
