package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"

	"circuitpathways"
	"circuitpathways/internal/content"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/server"
)

// exportSite writes everything a static host needs (the Cloudflare Worker's assets): the site, ArduinoPath's
// catalogue and projects as JSON files, the generic Pi installer, and a _headers file with this
// server's security headers. The folder is emptied first.
func exportSite(dir string, beta bool) error {
	cat, problems := content.Load(circuitpathways.Content())
	if len(problems) > 0 {
		return fmt.Errorf("content problem: %v", problems[0])
	}
	if err := os.RemoveAll(dir); err != nil {
		return err
	}
	site := circuitpathways.Site()
	write := func(rel string, data []byte) error {
		p := filepath.Join(dir, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			return err
		}
		return os.WriteFile(p, data, 0o644)
	}
	n := 0
	err := fs.WalkDir(site, ".", func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		b, err := fs.ReadFile(site, p)
		if err != nil {
			return err
		}
		n++
		return write(p, b)
	})
	if err != nil {
		return err
	}
	catJSON, err := server.CatalogueJSON(cat)
	if err != nil {
		return err
	}
	if err := write("arduinopath/data/catalogue.json", catJSON); err != nil {
		return err
	}
	for _, p := range cat.Projects {
		if err := write("arduinopath/data/projects/"+p.ID+".json", p.Raw); err != nil {
			return err
		}
	}
	app, err := fs.ReadFile(site, "pipath/remote/circuitpathways_pi.py")
	if err != nil {
		return err
	}
	inst, err := pilink.Installer(pilink.PlaceholderServer, "", app) // the Worker fills in its own address
	if err != nil {
		return err
	}
	if err := write("pipath/remote/install.sh", []byte(inst)); err != nil {
		return err
	}
	if err := write("_headers", []byte(server.HeadersFile(beta))); err != nil {
		return err
	}
	fmt.Printf("Wrote %d site files, %d projects, install.sh and _headers to %s\n", n, len(cat.Projects), dir)
	return nil
}
