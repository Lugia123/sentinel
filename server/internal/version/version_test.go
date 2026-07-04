package version

import "testing"

func TestFormat(t *testing.T) {
	cases := []struct{ branch, commit, count, want string }{
		{"feature/v1.1", "abc1234", "35", "v1.1.35"},
		{"feature/v1.1", "abc1234", "1", "v1.1.1"},
		{"feature/v2.0", "deadbee", "100", "v2.0.100"},
		{"main", "abc1234", "5", "dev-abc1234"},          // 非 feature 分支
		{"feature/v1.1", "abc1234", "", "dev-abc1234"},   // 无 count
	}
	for _, c := range cases {
		if got := Format(c.branch, c.commit, c.count); got != c.want {
			t.Errorf("Format(%q,%q,%q)=%q, want %q", c.branch, c.commit, c.count, got, c.want)
		}
	}
}
