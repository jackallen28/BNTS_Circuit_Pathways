// Package setup holds the installers: the school server's (shipped in the download, next to the program)
// and each student Pi's (made by the school server for its own address, and fetched with curl).
package setup

import (
	_ "embed"
	"errors"
	"regexp"
	"strings"
	"text/template"
)

//go:embed student-pi.sh.tmpl
var studentPiTemplate string

// ServerInstaller is install-server.sh, which goes in the download with the program.
//
//go:embed install-server.sh
var ServerInstaller []byte

var studentPi = template.Must(template.New("student-pi").Delims("<%", "%>").Parse(studentPiTemplate))

var safeURL = regexp.MustCompile(`^https?://[A-Za-z0-9.\-\[\]:]+$`)

// StudentPi is what a student Pi's installer needs to know.
type StudentPi struct {
	School string // the school server's https address, e.g. https://pathways.local
	HTTP   string // its plain address, for downloading the program, e.g. http://pathways.local
	SHA256 string // of the program
	Arch   string // arm64 or amd64
	CA     string // the school server's certificate authority (PEM)
}

// StudentPiScript writes the student Pi installer.
func StudentPiScript(d StudentPi) (string, error) {
	if !safeURL.MatchString(d.School) || !safeURL.MatchString(d.HTTP) {
		return "", errors.New("that server address can't be used in an installer")
	}
	if !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(d.SHA256) || (d.Arch != "arm64" && d.Arch != "amd64") {
		return "", errors.New("the program to install isn't right")
	}
	d.CA = strings.TrimSpace(d.CA)
	if !strings.HasPrefix(d.CA, "-----BEGIN CERTIFICATE-----") || strings.Contains(d.CA, "CA_END") {
		return "", errors.New("the certificate isn't right")
	}
	var b strings.Builder
	err := studentPi.Execute(&b, d)
	return b.String(), err
}
