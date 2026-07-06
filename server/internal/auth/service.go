// Package auth — 用户/权限:bcrypt 密码 + JWT 会话 + 管理员种子 + 系统设置(SMTP)+ 邮件找回。
// 账号=邮箱。参考 Tinia 的 auth 模式,适配 net/http + 原生 SQL。
package auth

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

type User struct {
	ID        int64     `json:"id"`
	Email     string    `json:"email"`
	Role      string    `json:"role"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"created_at"`
}

type Service struct {
	db     *gorm.DB
	secret string
}

func New(db *gorm.DB, secret string) *Service {
	if secret == "" {
		secret = "sentinel-dev-secret-change-me"
	}
	return &Service{db: db, secret: secret}
}

// EnsureAdmin 若无任何用户,种子一个默认管理员(账号=邮箱)。
func (s *Service) EnsureAdmin(email, password string) error {
	var n int64
	s.db.Raw(`SELECT COUNT(*) FROM users`).Scan(&n)
	if n > 0 {
		return nil
	}
	return s.CreateUser(email, password, "admin", "管理员")
}

func (s *Service) CreateUser(email, password, role, name string) error {
	email = strings.ToLower(strings.TrimSpace(email))
	if email == "" || !strings.Contains(email, "@") {
		return fmt.Errorf("邮箱格式不对")
	}
	if len(password) < 6 {
		return fmt.Errorf("密码至少6位")
	}
	if role != "admin" {
		role = "user"
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	e := s.db.Exec(`INSERT INTO users(email,password_hash,role,name) VALUES(?,?,?,?)`, email, string(hash), role, name).Error
	if e != nil {
		if strings.Contains(e.Error(), "duplicate") || strings.Contains(e.Error(), "unique") {
			return fmt.Errorf("邮箱 %s 已存在", email)
		}
		return e
	}
	return nil
}

// Login 校验邮箱+密码,返回用户 + JWT。
func (s *Service) Login(email, password string) (*User, string, error) {
	email = strings.ToLower(strings.TrimSpace(email))
	var row struct {
		ID           int64
		Email        string
		PasswordHash string
		Role         string
		Name         string
		CreatedAt    time.Time
	}
	err := s.db.Raw(`SELECT id,email,password_hash,role,name,created_at FROM users WHERE email=?`, email).Scan(&row).Error
	if err != nil || row.ID == 0 {
		return nil, "", fmt.Errorf("邮箱或密码错误")
	}
	if bcrypt.CompareHashAndPassword([]byte(row.PasswordHash), []byte(password)) != nil {
		return nil, "", fmt.Errorf("邮箱或密码错误")
	}
	u := &User{ID: row.ID, Email: row.Email, Role: row.Role, Name: row.Name, CreatedAt: row.CreatedAt}
	tok, err := s.token(u)
	return u, tok, err
}

func (s *Service) token(u *User) (string, error) {
	claims := jwt.MapClaims{"uid": u.ID, "role": u.Role, "exp": time.Now().Add(30 * 24 * time.Hour).Unix()}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(s.secret))
}

// Parse 校验 JWT,返回 uid+role。
func (s *Service) Parse(tokenStr string) (int64, string, error) {
	t, err := jwt.Parse(tokenStr, func(t *jwt.Token) (any, error) { return []byte(s.secret), nil })
	if err != nil || !t.Valid {
		return 0, "", fmt.Errorf("无效令牌")
	}
	c, ok := t.Claims.(jwt.MapClaims)
	if !ok {
		return 0, "", fmt.Errorf("无效令牌")
	}
	uid, _ := c["uid"].(float64)
	role, _ := c["role"].(string)
	return int64(uid), role, nil
}

func (s *Service) GetUser(id int64) (*User, error) {
	var u User
	err := s.db.Raw(`SELECT id,email,role,name,created_at FROM users WHERE id=?`, id).Scan(&u).Error
	if err != nil || u.ID == 0 {
		return nil, fmt.Errorf("用户不存在")
	}
	return &u, nil
}

func (s *Service) ListUsers() ([]User, error) {
	var us []User
	err := s.db.Raw(`SELECT id,email,role,name,created_at FROM users ORDER BY id`).Scan(&us).Error
	return us, err
}

func (s *Service) ChangePassword(userID int64, cur, next string) error {
	var hash string
	s.db.Raw(`SELECT password_hash FROM users WHERE id=?`, userID).Scan(&hash)
	if hash == "" || bcrypt.CompareHashAndPassword([]byte(hash), []byte(cur)) != nil {
		return fmt.Errorf("当前密码不对")
	}
	if len(next) < 6 {
		return fmt.Errorf("新密码至少6位")
	}
	nh, _ := bcrypt.GenerateFromPassword([]byte(next), bcrypt.DefaultCost)
	return s.db.Exec(`UPDATE users SET password_hash=? WHERE id=?`, string(nh), userID).Error
}

// setPasswordDirect 管理员重置 / 找回用:直接设新密码。
func (s *Service) setPasswordDirect(userID int64, next string) error {
	if len(next) < 6 {
		return fmt.Errorf("新密码至少6位")
	}
	nh, _ := bcrypt.GenerateFromPassword([]byte(next), bcrypt.DefaultCost)
	return s.db.Exec(`UPDATE users SET password_hash=? WHERE id=?`, string(nh), userID).Error
}

// ── 系统设置(键值)──
func (s *Service) GetSetting(key string) string {
	var v string
	s.db.Raw(`SELECT value FROM settings WHERE key=?`, key).Scan(&v)
	return v
}
func (s *Service) SetSetting(key, value string) error {
	return s.db.Exec(`INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value`, key, value).Error
}

// ── 忘记密码:令牌 ──
func (s *Service) CreateResetToken(email string) (string, int64, error) {
	email = strings.ToLower(strings.TrimSpace(email))
	var uid int64
	s.db.Raw(`SELECT id FROM users WHERE email=?`, email).Scan(&uid)
	if uid == 0 {
		return "", 0, fmt.Errorf("该邮箱未注册")
	}
	b := make([]byte, 24)
	_, _ = rand.Read(b)
	tok := hex.EncodeToString(b)
	err := s.db.Exec(`INSERT INTO password_resets(token,user_id,expires_at) VALUES(?,?,?)`,
		tok, uid, time.Now().Add(2*time.Hour)).Error
	return tok, uid, err
}

func (s *Service) ConsumeResetToken(token, newPassword string) error {
	var row struct {
		UserID    int64
		ExpiresAt time.Time
		Used      bool
	}
	s.db.Raw(`SELECT user_id, expires_at, used FROM password_resets WHERE token=?`, token).Scan(&row)
	if row.UserID == 0 {
		return fmt.Errorf("找回链接无效")
	}
	if row.Used || time.Now().After(row.ExpiresAt) {
		return fmt.Errorf("找回链接已失效,请重新申请")
	}
	if err := s.setPasswordDirect(row.UserID, newPassword); err != nil {
		return err
	}
	return s.db.Exec(`UPDATE password_resets SET used=true WHERE token=?`, token).Error
}
