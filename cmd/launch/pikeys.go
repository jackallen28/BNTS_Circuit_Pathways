package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"circuitpathways"
	"circuitpathways/internal/pilink"
)

// devPiKeySecret is the Pi key secret in -dev mode only: real sites set PI_KEY_SECRET.
const devPiKeySecret = "dev-pi-key-secret-do-not-use-in-production"

// piAppSource is the Pi app that goes inside every installer.
func piAppSource() ([]byte, error) {
	return fs.ReadFile(launch.Site(), "pipath/remote/circuitpathways_pi.py")
}

// refreshPiInstallers writes new installers (with the current Pi app inside) for Pis that already
// have keys, from the pi-keys.csv that makePiKeys wrote. The keys and IDs do not change, so running
// the new installer on a Pi updates it.
func refreshPiInstallers(csvPath, dir, server string) error {
	raw, err := os.ReadFile(csvPath)
	if err != nil {
		return err
	}
	src, err := piAppSource()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	rows := strings.Split(strings.TrimSpace(string(raw)), "\n")
	n := 0
	for _, row := range rows[1:] { // the first row is the column names
		f := strings.Split(strings.TrimSpace(row), ",")
		if len(f) < 4 {
			continue
		}
		script, err := pilink.Installer(server, f[2], src)
		if err != nil {
			return fmt.Errorf("%s: %w", f[1], err)
		}
		if err := os.WriteFile(filepath.Join(dir, f[3]), []byte(script), 0o700); err != nil {
			return err
		}
		n++
	}
	fmt.Printf("Wrote %d new installers in %s (same keys and IDs as before)\n", n, dir)
	return nil
}

// makePiKeys makes n Raspberry Pi keys and, for each Pi, an installer to run
// on it, plus a list of the IDs and keys for the teacher.
func makePiKeys(n int, dir, server string) error {
	secret := os.Getenv("PI_KEY_SECRET")
	if secret == "" {
		return fmt.Errorf("set PI_KEY_SECRET first: the same value the website uses")
	}
	keys, err := pilink.NewKeys(secret, nil)
	if err != nil {
		return err
	}
	src, err := piAppSource()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	var list, csv strings.Builder
	fmt.Fprintf(&list, "# Circuit Pathways Pi keys\n\nMade %s for %s\n\nKeep this file private: each key lets one Pi connect.\n\n", time.Now().Format("2 January 2006"), server)
	list.WriteString("| Label | Pi ID (students type this) | Installer file |\n|---|---|---|\n")
	csv.WriteString("label,id,key,installer\n")
	for i := 1; i <= n; i++ {
		id, key, err := keys.New()
		if err != nil {
			return err
		}
		script, err := pilink.Installer(server, key, src)
		if err != nil {
			return err
		}
		file := fmt.Sprintf("install-pi-%s.sh", pilink.DisplayID(id))
		if err := os.WriteFile(filepath.Join(dir, file), []byte(script), 0o700); err != nil {
			return err
		}
		fmt.Fprintf(&list, "| Pi %d | **%s** | `%s` |\n", i, pilink.DisplayID(id), file)
		fmt.Fprintf(&csv, "Pi %d,%s,%s,%s\n", i, pilink.DisplayID(id), key, file)
		fmt.Printf("Pi %d   ID %s   key %s\n", i, pilink.DisplayID(id), key)
	}
	list.WriteString("\n## Setting up a Pi\n\n1. Copy that Pi's installer file to the Pi (USB stick, or download it there).\n2. On the Pi, open a Terminal and run:  `sudo bash install-pi-XXXX-XXXX.sh`\n3. It installs Pi Link and starts it every time the Pi turns on. Stick the Pi's ID on the Pi.\n4. Students open PiPath, choose Run on: My Raspberry Pi, and type the ID. (Pi Link, the pin-switching page, uses the same ID.)\n5. To stop a Pi running students' programs: `sudo pilink run off` (pins still work).\n\nTo link a Pi to a different site later: `sudo pilink server https://your-site`.\n")
	if err := os.WriteFile(filepath.Join(dir, "PI-KEYS.md"), []byte(list.String()), 0o600); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(dir, "pi-keys.csv"), []byte(csv.String()), 0o600); err != nil {
		return err
	}
	fmt.Printf("\nWrote %d installers, PI-KEYS.md and pi-keys.csv in %s\n", n, dir)
	return nil
}
