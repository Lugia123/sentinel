// Package version — 版本号 = 分支版本 + commit 数(对齐 Tinia getVersion)。
// feature/vX.Y 分支 → vX.Y.<commit数>;其它分支 → dev-<短hash>。
package version

import (
	"os/exec"
	"regexp"
	"strings"
)

var branchRe = regexp.MustCompile(`^feature/(v\d+\.\d+)`)

type Info struct {
	Version string `json:"version"`
	Branch  string `json:"branch"`
	Commit  string `json:"commit"`
}

// Compute 在指定 repo 目录(server 上级=项目根)算版本。
func Compute(repoDir string) Info {
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
