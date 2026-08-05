package auth

import (
	"encoding/json"
	"net/http"
	"strconv"
)

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
func fail(w http.ResponseWriter, code int, msg string) { writeJSON(w, code, map[string]string{"error": msg}) }

// Register 把认证相关路由挂到 mux(open=无需登录;其余靠 Inject 中间件带上 user)。
func (s *Service) Register(mux *http.ServeMux) {
	mux.HandleFunc("/api/auth/login", s.hLogin)
	mux.HandleFunc("/api/auth/me", s.hMe)
	mux.HandleFunc("/api/auth/change-password", RequireAuth(s.hChangePassword))
	mux.HandleFunc("/api/pref/color", RequireAuth(s.hColorPref))
	mux.HandleFunc("/api/auth/forgot", s.hForgot)
	mux.HandleFunc("/api/auth/reset", s.hReset)
	mux.HandleFunc("/api/admin/users", RequireAdmin(s.hUsers))
	mux.HandleFunc("/api/admin/settings/smtp", RequireAdmin(s.hSMTP))
	mux.HandleFunc("/api/admin/settings/smtp/test", RequireAdmin(s.hSMTPTest))
}

func (s *Service) hLogin(w http.ResponseWriter, r *http.Request) {
	var b struct{ Email, Password string }
	_ = json.NewDecoder(r.Body).Decode(&b)
	u, tok, err := s.Login(b.Email, b.Password)
	if err != nil {
		fail(w, http.StatusUnauthorized, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"token": tok, "user": u, "color_up": s.ColorUp(u.ID)})
}

func (s *Service) hMe(w http.ResponseWriter, r *http.Request) {
	uid := UserID(r)
	if uid == 0 {
		fail(w, http.StatusUnauthorized, "未登录")
		return
	}
	u, err := s.GetUser(uid)
	if err != nil {
		fail(w, http.StatusUnauthorized, "未登录")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"user": u, "color_up": s.ColorUp(uid)})
}

// hColorPref 设置涨跌配色偏好(用户隔离):{"color_up":"green"|"red"}。
func (s *Service) hColorPref(w http.ResponseWriter, r *http.Request) {
	var b struct {
		ColorUp string `json:"color_up"`
	}
	_ = json.NewDecoder(r.Body).Decode(&b)
	if b.ColorUp != "green" && b.ColorUp != "red" {
		fail(w, http.StatusBadRequest, "color_up 仅 green/red")
		return
	}
	if err := s.SetPref(UserID(r), "color_up", b.ColorUp); err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "color_up": b.ColorUp})
}

func (s *Service) hChangePassword(w http.ResponseWriter, r *http.Request) {
	var b struct{ Current, New string }
	_ = json.NewDecoder(r.Body).Decode(&b)
	if err := s.ChangePassword(UserID(r), b.Current, b.New); err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *Service) hForgot(w http.ResponseWriter, r *http.Request) {
	var b struct{ Email string }
	_ = json.NewDecoder(r.Body).Decode(&b)
	tok, _, err := s.CreateResetToken(b.Email)
	if err != nil { // 不暴露邮箱是否存在,但这里为方便 dev 返回提示
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	base := s.GetSetting("app_base_url")
	if base == "" {
		base = "http://localhost:5173"
	}
	link := base + "/?reset=" + tok
	if !s.SMTPEnabled() {
		// 未配置邮箱:dev 兜底,直接返回链接(生产应配置邮箱)
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "smtp": false, "reset_link": link,
			"note": "系统邮箱未配置,已直接返回找回链接(dev)。配置后将改为发邮件。"})
		return
	}
	if err := s.SMTP().Send(b.Email, "Sentinel 密码找回", resetEmailHTML(link)); err != nil {
		fail(w, http.StatusInternalServerError, "发送邮件失败:"+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "smtp": true, "note": "找回邮件已发送,请查收。"})
}

func (s *Service) hReset(w http.ResponseWriter, r *http.Request) {
	var b struct{ Token, Password string }
	_ = json.NewDecoder(r.Body).Decode(&b)
	if err := s.ConsumeResetToken(b.Token, b.Password); err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

// hUsers GET=列出用户;POST=管理员开设新用户。
func (s *Service) hUsers(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		us, _ := s.ListUsers()
		writeJSON(w, http.StatusOK, map[string]any{"users": us})
	case http.MethodPost:
		var b struct{ Email, Password, Role, Name string }
		_ = json.NewDecoder(r.Body).Decode(&b)
		if err := s.CreateUser(b.Email, b.Password, b.Role, b.Name); err != nil {
			fail(w, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
	case http.MethodDelete:
		id, _ := strconv.ParseInt(r.URL.Query().Get("id"), 10, 64)
		if err := s.DeleteUser(id, UserID(r)); err != nil {
			fail(w, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
	default:
		fail(w, http.StatusMethodNotAllowed, "方法不支持")
	}
}

// hSMTP GET=读配置(密码不回显);PUT=保存。
func (s *Service) hSMTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		c := s.SMTP()
		c.Password = "" // 不回显密码
		writeJSON(w, http.StatusOK, map[string]any{"smtp": c, "enabled": s.SMTPEnabled()})
	case http.MethodPut:
		var c SMTPConfig
		_ = json.NewDecoder(r.Body).Decode(&c)
		if err := s.SaveSMTP(c); err != nil {
			fail(w, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
	default:
		fail(w, http.StatusMethodNotAllowed, "方法不支持")
	}
}

// hSMTPTest 发一封测试邮件到指定邮箱(校验配置)。
func (s *Service) hSMTPTest(w http.ResponseWriter, r *http.Request) {
	var b struct{ To string }
	_ = json.NewDecoder(r.Body).Decode(&b)
	if b.To == "" {
		fail(w, http.StatusBadRequest, "填收件邮箱")
		return
	}
	body := `<div style="font-family:sans-serif"><h3>Sentinel 测试邮件</h3><p>系统邮箱配置正常 ✅</p></div>`
	if err := s.SMTP().Send(b.To, "Sentinel 测试邮件", body); err != nil {
		fail(w, http.StatusInternalServerError, "发送失败:"+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}
