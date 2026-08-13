// 前端认证:token 存 localStorage,全局拦截 fetch 给 /api 带上 Authorization;
// 401 时清 token 并广播,由 App 切回登录页。
export interface AuthUser { id: number; email: string; role: string; name: string; created_at?: string }

const KEY = 'sentinel_token'
export const getToken = () => localStorage.getItem(KEY) || ''
export const setToken = (t: string) => localStorage.setItem(KEY, t)
export const clearToken = () => localStorage.removeItem(KEY)

// ── 涨跌配色偏好(用户隔离,随 /me 下发)。默认 red(A股:红涨绿跌);green=绿涨红跌(西式)。──
export type ColorScheme = 'green' | 'red'
const CKEY = 'sentinel_color_up'
export const getColorScheme = (): ColorScheme => (localStorage.getItem(CKEY) === 'green' ? 'green' : 'red')
export function applyColorScheme(v: ColorScheme) {
  localStorage.setItem(CKEY, v)
  if (typeof document !== 'undefined') document.documentElement.dataset.updown = v
}

// 安装一次全局 fetch 拦截器
let installed = false
export function installFetchAuth() {
  if (installed) return
  installed = true
  const orig = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.includes('/api/')) {
      const tok = getToken()
      if (tok) init.headers = { ...(init.headers || {}), Authorization: 'Bearer ' + tok }
    }
    const res = await orig(input, init)
    if (res.status === 401 && !url.includes('/api/auth/login')) {
      clearToken()
      window.dispatchEvent(new CustomEvent('sentinel-unauth'))
    }
    return res
  }
}

async function post(path: string, body: any) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok || j.error) throw new Error(j.error || '请求失败')
  return j
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const j = await post('/api/auth/login', { email, password })
  setToken(j.token)
  if (j.color_up) applyColorScheme(j.color_up)
  return j.user
}
export function logout() { clearToken() }
export async function fetchMe(): Promise<AuthUser | null> {
  const r = await fetch('/api/auth/me')
  if (!r.ok) return null
  const j = await r.json()
  if (j.color_up) applyColorScheme(j.color_up) // 登录态随用户偏好落地(用户隔离)
  return j.user
}
// 保存涨跌配色偏好(写回后端 + 本地即时生效)
export async function setColorPref(v: ColorScheme) {
  await post('/api/pref/color', { color_up: v })
  applyColorScheme(v)
}
export async function changePassword(current: string, next: string) {
  return post('/api/auth/change-password', { current, new: next })
}
export async function forgotPassword(email: string): Promise<{ smtp: boolean; reset_link?: string; note?: string }> {
  return post('/api/auth/forgot', { email })
}
export async function resetPassword(token: string, password: string) {
  return post('/api/auth/reset', { token, password })
}

// 管理员
export async function adminListUsers(): Promise<AuthUser[]> {
  const r = await fetch('/api/admin/users')
  return r.ok ? (await r.json()).users || [] : []
}
export async function adminCreateUser(email: string, password: string, role: string, name: string) {
  return post('/api/admin/users', { email, password, role, name })
}
// 删除用户登录账号(保留其关联数据)
export async function adminDeleteUser(id: number) {
  const r = await fetch(`/api/admin/users?id=${id}`, { method: 'DELETE' })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '删除失败')
}
export interface SMTPConfig { host: string; port: string; user: string; password: string; sender_name: string; use_tls: boolean }
export async function adminGetSMTP(): Promise<{ smtp: SMTPConfig; enabled: boolean }> {
  const r = await fetch('/api/admin/settings/smtp')
  return r.ok ? r.json() : { smtp: { host: '', port: '', user: '', password: '', sender_name: '', use_tls: false }, enabled: false }
}
export async function adminSaveSMTP(c: SMTPConfig) {
  const r = await fetch('/api/admin/settings/smtp', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(c) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存失败'); return j
}
export async function adminTestEmail(to: string) {
  return post('/api/admin/settings/smtp/test', { to })
}
// 调度间隔(小时)——管理员维护自动跑数据+双市场的频率
export async function adminGetSchedule(): Promise<{ interval_hours: number; markets: string[]; note: string }> {
  const r = await fetch('/api/admin/settings/schedule')
  return r.ok ? r.json() : { interval_hours: 4, markets: ['us', 'cn'], note: '' }
}
export async function adminSaveSchedule(interval_hours: number) {
  const r = await fetch('/api/admin/settings/schedule', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ interval_hours }) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存失败'); return j
}

// 数据源凭证(tushare:接口地址 host + api key)——管理员维护,存 DB,保存即热生效(无需重启后端)
export interface TushareCfg { url: string; token_masked: string; has_token: boolean; url_source: string; token_source: string }
export interface DatasourceResp { tushare: TushareCfg; enabled: boolean; default_url: string; note: string }
export async function adminGetDatasource(): Promise<DatasourceResp> {
  const r = await fetch('/api/admin/settings/datasource')
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '读取失败'); return j
}
export async function adminSaveDatasource(url: string, token: string): Promise<DatasourceResp> {
  const r = await fetch('/api/admin/settings/datasource', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, token }) })
  const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || '保存失败'); return j
}
export async function adminTestDatasource(url: string, token: string): Promise<{ ok: boolean; note?: string; error?: string }> {
  const r = await fetch('/api/admin/settings/datasource/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, token }) })
  const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || '测试失败'); return j
}
// 数据源健康(与顶部故障红条同源):最近成功刷新时间 / 报错
export async function adminAltStatus(): Promise<{ ok: boolean; source?: string; last_ok?: string; stale_hours?: number; last_error?: string }> {
  const r = await fetch('/api/altstatus')
  return r.ok ? r.json() : { ok: true }
}
