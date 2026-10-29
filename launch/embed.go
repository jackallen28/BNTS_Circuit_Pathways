// Package launch holds the website and the content that are built into the
// server, so the hosted site is one file.
package launch

import (
	"embed"
	"io/fs"
)

//go:embed all:site
var siteFiles embed.FS

//go:embed content
var contentFiles embed.FS

// Site is the website (the site folder).
func Site() fs.FS { return sub(siteFiles, "site") }

// Content is ArduinoPath's projects, boards and other data (the content folder).
func Content() fs.FS { return sub(contentFiles, "content") }

func sub(f embed.FS, dir string) fs.FS {
	s, err := fs.Sub(f, dir)
	if err != nil {
		panic(err)
	}
	return s
}
