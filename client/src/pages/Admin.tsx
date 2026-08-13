import { useEffect, useState } from 'react'
import {
  adminListUsers, adminCreateUser, adminDeleteUser, fetchMe, adminGetSMTP, adminSaveSMTP, adminTestEmail, adminGetSchedule, adminSaveSchedule,
  adminGetDatasource, adminSaveDatasource, adminTestDatasource, adminAltStatus,
  type AuthUser, type SMTPConfig, type DatasourceResp,
} from '../auth'

// 系统管理(仅管理员):按 tab 分区 —— 用户管理 / 数据源凭证 / 系统邮箱 / 自动运行。
// 各分区独立组件、各自按需加载(切到才拉),互不干扰。
type TabKey = 'users' | 'datasource' | 'smtp' | 'schedule'
const TABS: { k: TabKey; label: string; hint: string }[] = [
  { k: 'users', label: '用户管理', hint: '开设/删除登录账号。账号即邮箱;用户可自行改密、邮箱找回。' },
  { k: 'datasource', label: '数据源', hint: '外部行情/另类数据源的接口地址与 API Key。保存即生效,无需重启后端。' },
  { k: 'smtp', label: '系统邮箱', hint: '发送密码找回邮件的 SMTP 配置。' },
  { k: 'schedule', label: '自动运行', hint: '自动「刷新数据 + 跑双市场引擎」的频率。' },
]
const TKEY = 'sentinel.admin.tab'

export default function Admin() {
  const [tab, setTab] = useState<TabKey>(() => (TABS.some((t) => t.k === localStorage.getItem(TKEY)) ? (localStorage.getItem(TKEY) as TabKey) : 'users'))
  const pick = (k: TabKey) => { setTab(k); localStorage.setItem(TKEY, k) }
  const cur = TABS.find((t) => t.k === tab)!

  return (
    <>
      <div className="hint">🔧 <b>系统管理</b>(仅管理员)。{cur.hint}</div>
      <div className="seg" style={{ marginBottom: 14 }}>
        {TABS.map((t) => (
          <button key={t.k} className={t.k === tab ? 'on' : ''} onClick={() => pick(t.k)}>{t.label}</button>
        ))}
      </div>
      {tab === 'users' && <UsersTab />}
      {tab === 'datasource' && <DatasourceTab />}
      {tab === 'smtp' && <SMTPTab />}
      {tab === 'schedule' && <ScheduleTab />}
    </>
  )
}

// ── 用户管理 ─────────────────────────────────────────────
function UsersTab() {
  const [users, setUsers] = useState<AuthUser[]>([])
  const [meId, setMeId] = useState(0)
  const [nEmail, setNEmail] = useState(''); const [nPw, setNPw] = useState(''); const [nName, setNName] = useState(''); const [nRole, setNRole] = useState('user')
  const [uMsg, setUMsg] = useState(''); const [uErr, setUErr] = useState('')
  const load = () => adminListUsers().then(setUsers)
  useEffect(() => { load(); fetchMe().then((m) => setMeId(m?.id || 0)) }, [])

  const createUser = async () => {
    setUErr(''); setUMsg('')
    try { await adminCreateUser(nEmail, nPw, nRole, nName); setUMsg(`已开设用户 ${nEmail}`); setNEmail(''); setNPw(''); setNName(''); load() }
    catch (e: any) { setUErr(String(e.message || e)) }
  }
  const delUser = async (u: AuthUser) => {
    if (!confirm(`删除用户「${u.email}」?\n仅删除登录账号,其持仓/关注/AI讲解等数据会保留。`)) return
    setUErr(''); setUMsg('')
    try { await adminDeleteUser(u.id); setUMsg(`已删除用户 ${u.email}`); load() }
    catch (e: any) { setUErr(String(e.message || e)) }
  }

  return (
    <div className="card">
      <h3>用户管理</h3>
      <div className="tbl-scroll">
        <table>
          <thead><tr><th>ID</th><th>邮箱(账号)</th><th>角色</th><th>名称</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td><td><b>{u.email}</b></td>
                <td><span className={u.role === 'admin' ? 'gold' : 'muted'}>{u.role === 'admin' ? '管理员' : '普通用户'}</span></td>
                <td>{u.name || '—'}</td><td className="muted">{(u.created_at || '').slice(0, 10)}</td>
                <td>{u.id === meId
                  ? <span className="muted" style={{ fontSize: 12 }}>当前账号</span>
                  : <button className="link-danger" onClick={() => delUser(u)}>删除登录</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
        <div className="ctl-lbl">开设新用户</div>
        <div className="admin-form">
          <input placeholder="邮箱" value={nEmail} onChange={(e) => setNEmail(e.target.value)} />
          <input placeholder="初始密码(≥6位)" value={nPw} onChange={(e) => setNPw(e.target.value)} />
          <input placeholder="名称(可选)" value={nName} onChange={(e) => setNName(e.target.value)} />
          <select className="qsel" value={nRole} onChange={(e) => setNRole(e.target.value)}>
            <option value="user">普通用户</option><option value="admin">管理员</option>
          </select>
          <button className="primary" onClick={createUser}>开设</button>
        </div>
        {uErr && <div className="down" style={{ fontSize: 13, marginTop: 6 }}>{uErr}</div>}
        {uMsg && <div className="up" style={{ fontSize: 13, marginTop: 6 }}>{uMsg}</div>}
      </div>
    </div>
  )
}

// ── 数据源(tushare:host + api key)────────────────────────
// token 不回显明文(只给打码);留空=不改。保存后后端立即注入进程 env,下次跑引擎即生效。
function DatasourceTab() {
  const [cfg, setCfg] = useState<DatasourceResp | null>(null)
  const [url, setUrl] = useState(''); const [token, setToken] = useState('')
  const [msg, setMsg] = useState(''); const [err, setErr] = useState(''); const [testing, setTesting] = useState(false)
  const [health, setHealth] = useState<{ ok: boolean; last_ok?: string; stale_hours?: number; last_error?: string } | null>(null)

  const load = () => adminGetDatasource().then((r) => { setCfg(r); setUrl(r.tushare.url) }).catch((e) => setErr(String(e.message || e)))
  useEffect(() => { load(); adminAltStatus().then(setHealth) }, [])

  const save = async () => {
    setErr(''); setMsg('')
    try { const r = await adminSaveDatasource(url, token); setCfg(r); setUrl(r.tushare.url); setToken(''); setMsg('已保存,已即时生效(下次跑引擎/刷新数据时使用新凭证)') }
    catch (e: any) { setErr(String(e.message || e)) }
  }
  const test = async () => {
    setErr(''); setMsg(''); setTesting(true)
    try { const r = await adminTestDatasource(url, token); r.ok ? setMsg(`✓ ${r.note}`) : setErr(`✗ ${r.error}`) }
    catch (e: any) { setErr(String(e.message || e)) }
    finally { setTesting(false) }
  }

  const ts = cfg?.tushare
  const srcTag = (s?: string) => (s === 'env' ? <span className="muted" style={{ fontSize: 11 }}> · 来自 server/.env</span>
    : s === 'db' ? <span className="muted" style={{ fontSize: 11 }}> · 来自本页配置</span> : null)

  return (
    <>
      <div className="card">
        <h3>
          tushare(A股 事件 / 红利 / 资金流){' '}
          {cfg?.enabled ? <span className="up" style={{ fontSize: 12 }}>· 已配置</span> : <span className="muted" style={{ fontSize: 12 }}>· 未配置</span>}
        </h3>
        <div className="muted" style={{ marginBottom: 10 }}>
          {cfg?.note || 'tushare 供 A股 事件/红利/资金流腿。'}
          {' '}接口地址一般为 <code>{cfg?.default_url || 'http://api.tushare.pro'}</code>;token 在 tushare 个人主页获取,<b>月卡会过期</b>,过期后在这里换新即可。
        </div>
        <div className="admin-grid">
          <label>接口地址(host)
            <input placeholder={cfg?.default_url || 'http://api.tushare.pro'} value={url} onChange={(e) => setUrl(e.target.value)} />
          </label>
          <label>API Token
            <input type="password" placeholder={ts?.has_token ? `留空=不改(当前 ${ts.token_masked})` : '粘贴 tushare token'} value={token} onChange={(e) => setToken(e.target.value)} />
          </label>
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          地址{srcTag(ts?.url_source) || <span> · 未配置</span>};Token{srcTag(ts?.token_source) || <span> · 未配置</span>}
          {(ts?.url_source === 'env' || ts?.token_source === 'env') && <span> —— 在此保存后改以数据库为准,覆盖 .env。</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
          <button className="primary" onClick={save}>保存配置</button>
          <button className="ghost" onClick={test} disabled={testing}>{testing ? '测试中…' : '测试连接'}</button>
        </div>
        {err && <div className="down" style={{ fontSize: 13, marginTop: 6 }}>{err}</div>}
        {msg && <div className="up" style={{ fontSize: 13, marginTop: 6 }}>{msg}</div>}
      </div>

      <div className="card">
        <h3>数据源健康 {health && (health.ok ? <span className="up" style={{ fontSize: 12 }}>· 正常</span> : <span className="down" style={{ fontSize: 12 }}>· 异常</span>)}</h3>
        <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.7 }}>
          最近成功刷新:{health?.last_ok || '—'}{health?.stale_hours != null && <span>({health.stale_hours} 小时前)</span>}<br />
          {health?.last_error ? <span className="down">最近错误:{health.last_error}</span> : '无错误记录'}<br />
          <span style={{ fontSize: 11.5 }}>凭证失效只影响 A股 事件/红利/资金流腿(继续用现有数据,不阻断策略);美股与 A股行情腿不涉及。</span>
        </div>
      </div>
    </>
  )
}

// ── 系统邮箱(SMTP)──────────────────────────────────────
function SMTPTab() {
  const [smtp, setSmtp] = useState<SMTPConfig>({ host: '', port: '465', user: '', password: '', sender_name: 'Sentinel', use_tls: true })
  const [smtpEnabled, setSmtpEnabled] = useState(false)
  const [testTo, setTestTo] = useState(''); const [sMsg, setSMsg] = useState(''); const [sErr, setSErr] = useState('')
  useEffect(() => { adminGetSMTP().then((r) => { setSmtp({ ...r.smtp, password: '' }); setSmtpEnabled(r.enabled) }) }, [])

  const saveSmtp = async () => {
    setSErr(''); setSMsg('')
    try { await adminSaveSMTP(smtp); setSMsg('已保存系统邮箱配置'); const r = await adminGetSMTP(); setSmtpEnabled(r.enabled) }
    catch (e: any) { setSErr(String(e.message || e)) }
  }
  const testEmail = async () => {
    setSErr(''); setSMsg('')
    try { await adminTestEmail(testTo); setSMsg(`测试邮件已发往 ${testTo}`) }
    catch (e: any) { setSErr(String(e.message || e)) }
  }

  return (
    <div className="card">
      <h3>系统邮箱(SMTP) {smtpEnabled ? <span className="up" style={{ fontSize: 12 }}>· 已启用</span> : <span className="muted" style={{ fontSize: 12 }}>· 未配置</span>}</h3>
      <div className="muted" style={{ marginBottom: 10 }}>用于发送密码找回邮件。常见:QQ邮箱 smtp.qq.com:465(SSL) + 授权码;Gmail smtp.gmail.com:465。</div>
      <div className="admin-grid">
        <label>SMTP 服务器<input placeholder="如 smtp.qq.com" value={smtp.host} onChange={(e) => setSmtp({ ...smtp, host: e.target.value })} /></label>
        <label>端口<input placeholder="465" value={smtp.port} onChange={(e) => setSmtp({ ...smtp, port: e.target.value })} /></label>
        <label>发件邮箱<input placeholder="you@qq.com" value={smtp.user} onChange={(e) => setSmtp({ ...smtp, user: e.target.value })} /></label>
        <label>密码/授权码<input type="password" placeholder="留空=不改" value={smtp.password} onChange={(e) => setSmtp({ ...smtp, password: e.target.value })} /></label>
        <label>发件人名称<input placeholder="Sentinel" value={smtp.sender_name} onChange={(e) => setSmtp({ ...smtp, sender_name: e.target.value })} /></label>
        <label className="chk"><input type="checkbox" checked={smtp.use_tls} onChange={(e) => setSmtp({ ...smtp, use_tls: e.target.checked })} /> 使用 SSL/TLS(端口465勾选)</label>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <button className="primary" onClick={saveSmtp}>保存配置</button>
        <input placeholder="测试收件邮箱" value={testTo} onChange={(e) => setTestTo(e.target.value)} style={{ width: 180 }} />
        <button className="ghost" onClick={testEmail}>发测试邮件</button>
      </div>
      {sErr && <div className="down" style={{ fontSize: 13, marginTop: 6 }}>{sErr}</div>}
      {sMsg && <div className="up" style={{ fontSize: 13, marginTop: 6 }}>{sMsg}</div>}
    </div>
  )
}

// ── 自动运行调度 ─────────────────────────────────────────
function ScheduleTab() {
  const [schedH, setSchedH] = useState(4); const [schedNote, setSchedNote] = useState(''); const [schMsg, setSchMsg] = useState(''); const [schErr, setSchErr] = useState('')
  useEffect(() => { adminGetSchedule().then((r) => { setSchedH(r.interval_hours); setSchedNote(r.note) }) }, [])
  const saveSched = async () => {
    setSchMsg(''); setSchErr('')
    try { const r = await adminSaveSchedule(schedH); setSchMsg('已保存,下个周期生效'); setSchedNote(r.note) } catch (e: any) { setSchErr(String(e.message || e)) }
  }
  return (
    <div className="card">
      <h3>自动运行调度</h3>
      <div className="muted" style={{ marginBottom: 10 }}>每隔 N 小时自动「刷新数据 + 跑双市场(美股+A股)引擎」。EOD 数据每天更新一次,多跑=兜底重试(确保可靠抓到当天收盘)。改后下个周期生效。</div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <label>每
          <input type="number" min={1} max={24} value={schedH} onChange={(e) => setSchedH(Math.max(1, Math.min(24, parseInt(e.target.value) || 4)))} style={{ width: 64, margin: '0 6px' }} />
          小时跑一次
        </label>
        <button className="primary" onClick={saveSched}>保存</button>
      </div>
      {schedNote && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{schedNote}</div>}
      {schErr && <div className="down" style={{ fontSize: 13, marginTop: 6 }}>{schErr}</div>}
      {schMsg && <div className="up" style={{ fontSize: 13, marginTop: 6 }}>{schMsg}</div>}
    </div>
  )
}
