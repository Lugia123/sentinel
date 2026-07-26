package auth

import (
	"crypto/tls"
	"fmt"
	"net/smtp"
	"strings"
)

// SMTPConfig 系统邮箱配置(存于 settings 表,管理员在系统管理里维护)。
type SMTPConfig struct {
	Host       string `json:"host"`
	Port       string `json:"port"`
	User       string `json:"user"`     // 发件邮箱账号
	Password   string `json:"password"` // 授权码/密码(读取时不回显)
	SenderName string `json:"sender_name"`
	UseTLS     bool   `json:"use_tls"`
}

func (s *Service) SMTP() SMTPConfig {
	return SMTPConfig{
		Host: s.GetSetting("smtp_host"), Port: s.GetSetting("smtp_port"),
		User: s.GetSetting("smtp_user"), Password: s.GetSetting("smtp_password"),
		SenderName: s.GetSetting("smtp_sender_name"), UseTLS: s.GetSetting("smtp_use_tls") == "true",
	}
}

func (s *Service) SaveSMTP(c SMTPConfig) error {
	pairs := map[string]string{
		"smtp_host": c.Host, "smtp_port": c.Port, "smtp_user": c.User,
		"smtp_sender_name": c.SenderName, "smtp_use_tls": boolStr(c.UseTLS),
	}
	if c.Password != "" { // 空则保留原密码(前端不回显)
		pairs["smtp_password"] = c.Password
	}
	for k, v := range pairs {
		if err := s.SetSetting(k, v); err != nil {
			return err
		}
	}
	return nil
}

func (s *Service) SMTPEnabled() bool {
	c := s.SMTP()
	return c.Host != "" && c.User != "" && c.Password != ""
}

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

// SendMail 发一封 HTML 邮件。
func (c SMTPConfig) Send(to, subject, htmlBody string) error {
	if c.Host == "" || c.User == "" {
		return fmt.Errorf("系统邮箱未配置(请管理员在系统管理里填写)")
	}
	from := c.User
	sender := c.SenderName
	if sender == "" {
		sender = "Sentinel"
	}
	msg := "From: " + sender + " <" + from + ">\r\n" +
		"To: " + to + "\r\n" +
		"Subject: " + subject + "\r\n" +
		"MIME-Version: 1.0\r\n" +
		"Content-Type: text/html; charset=UTF-8\r\n\r\n" + htmlBody
	addr := c.Host + ":" + c.Port
	auth := smtp.PlainAuth("", c.User, c.Password, c.Host)

	if c.UseTLS { // 隐式 TLS(端口465)
		conn, err := tls.Dial("tcp", addr, &tls.Config{ServerName: c.Host})
		if err != nil {
			return err
		}
		client, err := smtp.NewClient(conn, c.Host)
		if err != nil {
			return err
		}
		defer client.Close()
		if err := client.Auth(auth); err != nil {
			return err
		}
		if err := client.Mail(from); err != nil {
			return err
		}
		if err := client.Rcpt(to); err != nil {
			return err
		}
		w, err := client.Data()
		if err != nil {
			return err
		}
		if _, err := w.Write([]byte(msg)); err != nil {
			return err
		}
		_ = w.Close()
		return client.Quit()
	}
	// STARTTLS / 明文(端口587/25)
	return smtp.SendMail(addr, auth, from, []string{to}, []byte(msg))
}

func resetEmailHTML(link string) string {
	return strings.ReplaceAll(`<div style="font-family:sans-serif;max-width:520px;margin:0 auto">
<h2 style="color:#8a6d1f">Sentinel 密码找回</h2>
<p>你(或有人)申请了重置密码。点击下面按钮设置新密码(2 小时内有效):</p>
<p style="margin:24px 0"><a href="__LINK__" style="background:#c8a253;color:#1a140a;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:700">重置密码</a></p>
<p style="color:#888;font-size:12px">若不是你本人操作,忽略此邮件即可。链接:__LINK__</p>
<p style="color:#888;font-size:12px">Sentinel · 研究工具,非投资建议</p></div>`, "__LINK__", link)
}
