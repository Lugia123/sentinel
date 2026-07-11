import { useEffect, useState } from 'react'
import {
  adminListUsers, adminCreateUser, adminDeleteUser, fetchMe, adminGetSMTP, adminSaveSMTP, adminTestEmail, adminGetSchedule, adminSaveSchedule,
  type AuthUser, type SMTPConfig,
} from '../auth'

// 系统管理(仅管理员):用户管理 + 系统邮箱(SMTP)。参考 Tinia 的系统管理。
export default function Admin() {
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

  // SMTP
  const [smtp, setSmtp] = useState<SMTPConfig>({ host: '', port: '465', user: '', password: '', sender_name: 'Sentinel', use_tls: true })
  const [smtpEnabled, setSmtpEnabled] = useState(false)
  const [testTo, setTestTo] = useState(''); const [sMsg, setSMsg] = useState(''); const [sErr, setSErr] = useState('')
  useEffect(() => { adminGetSMTP().then((r) => { setSmtp({ ...r.smtp, password: '' }); setSmtpEnabled(r.enabled) }) }, [])
  // 调度间隔
  const [schedH, setSchedH] = useState(4); const [schedNote, setSchedNote] = useState(''); const [schMsg, setSchMsg] = useState(''); const [schErr, setSchErr] = useState('')
  useEffect(() => { adminGetSchedule().then((r) => { setSchedH(r.interval_hours); setSchedNote(r.note) }) }, [])
  const saveSched = async () => {
    setSchMsg(''); setSchErr('')
    try { const r = await adminSaveSchedule(schedH); setSchMsg('已保存,下个周期生效'); setSchedNote(r.note) } catch (e: any) { setSchErr(String(e.message || e)) }
  }
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
    <>
      <div className="hint">🔧 <b>系统管理</b>(仅管理员)。开设用户、维护系统邮箱。账号即邮箱;用户可自行改密/邮箱找回。</div>

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
      <div className="admin-card">
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
    </>
  )
}
