package auth

import (
	"context"
	"net/http"
	"strings"
)

type ctxKey int

const (
	kUID ctxKey = iota
	kRole
)

// Inject 解析令牌(Bearer 头 或 ?token=),有效则把 uid/role 放进 context(不阻塞)。
func (s *Service) Inject(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := ""
		if h := r.Header.Get("Authorization"); strings.HasPrefix(h, "Bearer ") {
			tok = strings.TrimPrefix(h, "Bearer ")
		} else if q := r.URL.Query().Get("token"); q != "" {
			tok = q
		}
		if tok != "" {
			if uid, role, err := s.Parse(tok); err == nil {
				ctx := context.WithValue(r.Context(), kUID, uid)
				ctx = context.WithValue(ctx, kRole, role)
				r = r.WithContext(ctx)
			}
		}
		next.ServeHTTP(w, r)
	})
}

// UserID 当前登录用户 id(未登录=0)。
func UserID(r *http.Request) int64 {
	if v, ok := r.Context().Value(kUID).(int64); ok {
		return v
	}
	return 0
}

// Role 当前用户角色(未登录="")。
func Role(r *http.Request) string {
	if v, ok := r.Context().Value(kRole).(string); ok {
		return v
	}
	return ""
}

func IsAdmin(r *http.Request) bool { return Role(r) == "admin" }

// RequireAuth 包装:未登录返回 401。
func RequireAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if UserID(r) == 0 {
			http.Error(w, `{"error":"请先登录"}`, http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

// RequireAdmin 包装:非管理员返回 403。
func RequireAdmin(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if UserID(r) == 0 {
			http.Error(w, `{"error":"请先登录"}`, http.StatusUnauthorized)
			return
		}
		if !IsAdmin(r) {
			http.Error(w, `{"error":"需要管理员权限"}`, http.StatusForbidden)
			return
		}
		next(w, r)
	}
}
