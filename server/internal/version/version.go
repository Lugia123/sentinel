// Package version — 版本号 = 分支版本 + commit 数(对齐 Tinia getVersion)。
// feature/vX.Y 分支 → vX.Y.<commit数>;其它分支 → dev-<短hash>。
package version

import (
	"os/exec"
	"regexp"
	"strings"
)

var branchRe = regexp.MustCompile(`^feature/(v\d+\.\d+)`)

// Injected 由编译时 ldflags 注入(生产二进制无 .git 时用):
//   go build -ldflags "-X sentinel/internal/version.Injected=v1.6.42|abc1234|feature/v1.6"
// 格式:version|commit|branch(| 分隔)。开发态本地有 git,留空即走 git 计算。
var Injected string

type Info struct {
	Version string `json:"version"`
	Branch  string `json:"branch"`
	Commit  string `json:"commit"`
}

// Compute 在指定 repo 目录(server 上级=项目根)算版本;有 ldflags 注入则优先用注入值。
func Compute(repoDir string) Info {
	if Injected != "" {
		p := strings.Split(Injected, "|")
		info := Info{Version: p[0]}
		if len(p) > 1 {
			info.Commit = p[1]
		}
		if len(p) > 2 {
			info.Branch = p[2]
		}
		return info
	}
	branch := git(repoDir, "rev-parse", "--abbrev-ref", "HEAD")
	commit := git(repoDir, "rev-parse", "--short=7", "HEAD")
	count := git(repoDir, "rev-list", "HEAD", "--count")
	return Info{Version: Format(branch, commit, count), Branch: branch, Commit: commit}
}

// Format 纯函数:feature/vX.Y + count → vX.Y.count;否则 dev-<commit>。(可测)
func Format(branch, commit, count string) string {
	if m := branchRe.FindStringSubmatch(branch); m != nil && count != "" {
		return m[1] + "." + count
	}
	return "dev-" + commit
}

func git(dir string, args ...string) string {
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}
