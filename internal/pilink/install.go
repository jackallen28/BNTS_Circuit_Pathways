package pilink

import (
	_ "embed"
	"errors"
	"strings"
	"text/template"
)

//go:embed install.sh.tmpl
var installTemplate string

var tmpl = template.Must(template.New("install").Delims("<%", "%>").Parse(installTemplate))

// PlaceholderServer is the website address written into the Pi app's source
// (and replaced when the app is handed out).
const PlaceholderServer = "http://localhost:8080"

// Installer writes the shell script a Pi runs once (with sudo) to install Pi
// Link and start it at every boot. With a key, the script is for that one Pi;
// with no key, the script takes the key as its first argument. app is the
// source of circuitpathways_pi.py.
func Installer(server, key string, app []byte) (string, error) {
	if !strings.HasPrefix(server, "https://") && !strings.HasPrefix(server, "http://") {
		return "", errors.New("the website address must start with https:// or http://")
	}
	if strings.ContainsAny(server, " \t\r\n\"'\\$`") {
		return "", errors.New("the website address has characters that aren't allowed")
	}
	src := strings.ReplaceAll(string(app), PlaceholderServer, strings.TrimRight(server, "/"))
	if strings.Contains(src, "\nPYTHON_APP_END\n") {
		return "", errors.New("the Pi app can't contain the installer's end marker")
	}
	data := struct{ Server, Key, ID, IDFile, App string }{Server: strings.TrimRight(server, "/"), App: strings.TrimRight(src, "\n")}
	if key != "" {
		parts := strings.Split(key, "-")
		if len(parts) != 3 || len(parts[1]) != idLen {
			return "", errors.New("that isn't a Pi key")
		}
		data.Key, data.ID, data.IDFile = key, DisplayID(parts[1]), parts[1][:4]+"-"+parts[1][4:]
	}
	var b strings.Builder
	if err := tmpl.Execute(&b, data); err != nil {
		return "", err
	}
	return b.String(), nil
}
