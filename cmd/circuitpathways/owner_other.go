//go:build !linux

package main

func becomeOwner(dir string) error { return nil }
