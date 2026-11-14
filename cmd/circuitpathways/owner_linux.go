package main

import (
	"os"
	"syscall"
)

// Everything Circuit Pathways writes (the database, secrets, certificate keys, backups) is for its own user only.
func init() { syscall.Umask(0o077) }

// becomeOwner: run as root (sudo circuitpathways teacher add ...), the commands first become the user who owns the
// data folder (the service's own user), so every file they make or change is still the service's to read.
func becomeOwner(dir string) error {
	if os.Getuid() != 0 {
		return nil
	}
	st, err := os.Stat(dir)
	if err != nil {
		return nil // (no data folder yet: nothing to match)
	}
	sys, ok := st.Sys().(*syscall.Stat_t)
	if !ok || sys.Uid == 0 {
		return nil
	}
	if err := syscall.Setgroups([]int{}); err != nil {
		return err
	}
	if err := syscall.Setgid(int(sys.Gid)); err != nil {
		return err
	}
	return syscall.Setuid(int(sys.Uid))
}
