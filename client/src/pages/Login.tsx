import { useState } from 'react'
import { login, forgotPassword, resetPassword, type AuthUser } from '../auth'

// 登录页(参考 Tinia:账号=邮箱)。含忘记密码 + 重置(URL ?reset=token 时进入重置模式)。
export default function Login({ onLogin }: { onLogin: (u: AuthUser) => void }) {
  const resetToken = new URLSearchParams(location.search).get('reset') || ''
  const [mode, setMode] = useState<'login' | 'forgot' | 'reset'>(resetToken ? 'reset' : 'login')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const doLogin = async () => {
    setErr(''); setBusy(true)
    try { onLogin(await login(email, pw)) } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }
  const doForgot = async () => {
    setErr(''); setMsg(''); setBusy(true)
    try {
      const r = await forgotPassword(email)
      setMsg(r.reset_link ? `${r.note} 链接:${r.reset_link}` : (r.note || '找回邮件已发送,请查收。'))
    } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }
  const doReset = async () => {
    setErr(''); setMsg('')
    if (pw.length < 6) { setErr('新密码至少6位'); return }
    if (pw !== pw2) { setErr('两次密码不一致'); return }
    setBusy(true)
    try {
      await resetPassword(resetToken, pw)
      setMsg('密码已重置,请用新密码登录。'); setMode('login')
      history.replaceState({}, '', location.pathname)
    } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-brand">SENTINEL</div>

        {mode === 'login' && (<>
          <input className="login-in" placeholder="邮箱(账号)" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doLogin()} />
          <input className="login-in" type="password" placeholder="密码" value={pw} onChange={(e) => setPw(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doLogin()} />
          <button className="login-btn" onClick={doLogin} disabled={busy}>{busy ? '登录中…' : '登录'}</button>
          <div className="login-links"><button className="linkbtn" onClick={() => { setMode('forgot'); setErr(''); setMsg('') }}>忘记密码?</button></div>
        </>)}

        {mode === 'forgot' && (<>
          <div className="login-hint">输入注册邮箱,我们会发送重置链接。</div>
          <input className="login-in" placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doForgot()} />
          <button className="login-btn" onClick={doForgot} disabled={busy}>{busy ? '发送中…' : '发送找回链接'}</button>
          <div className="login-links"><button className="linkbtn" onClick={() => { setMode('login'); setErr(''); setMsg('') }}>← 返回登录</button></div>
        </>)}

        {mode === 'reset' && (<>
          <div className="login-hint">设置新密码(重置链接)。</div>
          <input className="login-in" type="password" placeholder="新密码(≥6位)" value={pw} onChange={(e) => setPw(e.target.value)} />
          <input className="login-in" type="password" placeholder="确认新密码" value={pw2} onChange={(e) => setPw2(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doReset()} />
          <button className="login-btn" onClick={doReset} disabled={busy}>{busy ? '提交中…' : '重置密码'}</button>
          <div className="login-links"><button className="linkbtn" onClick={() => { setMode('login'); setErr(''); setMsg(''); history.replaceState({}, '', location.pathname) }}>← 返回登录</button></div>
        </>)}

        {err && <div className="login-err">{err}</div>}
        {msg && <div className="login-msg">{msg}</div>}
      </div>
    </div>
  )
}
