package server

import (
	"encoding/json"
	"strings"

	"circuitpathways/internal/content"
)

const permissionsPolicy = "serial=(self), usb=(self), camera=(), microphone=(), geolocation=(), interest-cohort=()"

// Files that rarely change (the vendored Python, Blockly and esptool, and the logos) are cached for a week, so a
// student's second visit, and especially a Raspberry Pi on slow WiFi, doesn't ask for 12 MB of Python again.
// Everything else stays "no-cache": the browser asks, and gets a quick "not changed" when it hasn't.
const vendorCacheControl = "public, max-age=604800"

var longCachedDirs = []string{"pipath/vendor/", "arduinopath/vendor/", "img/"}

// cacheControlFor is the Cache-Control header for a file in the site (path without a leading slash).
func cacheControlFor(file string) string {
	for _, d := range longCachedDirs {
		if strings.HasPrefix(file, d) {
			return vendorCacheControl
		}
	}
	return "no-cache"
}

// CatalogueJSON is ArduinoPath's catalogue, as /arduinopath/data/catalogue.json serves it.
func CatalogueJSON(c *content.Catalogue) ([]byte, error) {
	boards := make([]json.RawMessage, 0, len(c.Boards))
	for _, b := range c.Boards {
		boards = append(boards, b.Raw)
	}
	projects := make([]any, 0, len(c.Projects))
	for _, p := range c.Projects {
		projects = append(projects, p.ProjectSummary)
	}
	return json.Marshal(map[string]any{
		"tiers": c.Tiers, "parts": c.Parts, "kit": c.Kit, "boards": boards,
		"projects": projects, "errors": c.Errors, "curriculum": c.Curriculum,
	})
}

// HeadersFile is the same security headers this server sends, written as a Cloudflare _headers
// file, so a copy of the site served from Cloudflare's static assets behaves the same.
func HeadersFile(beta bool) string {
	var b strings.Builder
	b.WriteString("# Made by `circuitpathways -export`: the same headers the Go server sends (internal/server). Don't edit.\n")
	b.WriteString("/*\n")
	b.WriteString("  Content-Security-Policy: " + cspFor("/") + "\n")
	b.WriteString("  X-Content-Type-Options: nosniff\n  X-Frame-Options: SAMEORIGIN\n  Referrer-Policy: no-referrer\n")
	b.WriteString("  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Resource-Policy: same-origin\n")
	b.WriteString("  Permissions-Policy: " + permissionsPolicy + "\n  Strict-Transport-Security: max-age=31536000\n")
	b.WriteString("  Cache-Control: no-cache\n")
	if beta {
		b.WriteString("  X-Robots-Tag: noindex, nofollow\n")
	}
	for _, app := range []string{"/arduinopath/*", "/pipath/*"} {
		b.WriteString(app + "\n  ! Content-Security-Policy\n  Content-Security-Policy: " + cspFor(strings.TrimSuffix(app, "*")) + "\n")
		if app == "/pipath/*" {
			b.WriteString("  Cross-Origin-Embedder-Policy: require-corp\n")
		}
	}
	for _, d := range longCachedDirs {
		b.WriteString("/" + d + "*\n  ! Cache-Control\n  Cache-Control: " + vendorCacheControl + "\n")
	}
	return b.String()
}
