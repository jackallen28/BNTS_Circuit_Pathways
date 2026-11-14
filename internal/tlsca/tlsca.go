// Package tlsca gives the school server its own https certificate. Browsers only let a page upload to a
// board (Web Serial) and run Python that waits for input (shared memory) on a secure address, so the
// server needs https even on the school's own network, where no public certificate can be had.
//
// The server makes its own small certificate authority once (kept in its data folder), and from it a
// certificate for its names and addresses, made again by itself when they change or it gets old. A
// laptop trusts the server by installing the authority's certificate once (the /trust page explains
// how); the authority can only vouch for this server's own names and addresses (a name constraint).
package tlsca

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"time"
)

const (
	caYears    = 20
	leafDays   = 397 // browsers accept up to 398 days
	renewDays  = 30
	caCertFile = "ca.crt"
	caKeyFile  = "ca.key"
	leafCert   = "server.crt"
	leafKey    = "server.key"
)

// Authority is the school server's own certificate authority and its current certificate.
type Authority struct {
	dir    string
	ca     *x509.Certificate
	caKey  *ecdsa.PrivateKey
	caPEM  []byte
	names  func() ([]string, []net.IP)
	mu     sync.Mutex
	leaf   *tls.Certificate
	leafOf string
	now    func() time.Time
}

// Open loads the authority from dir, making it the first time. names says which names and addresses
// the certificate is for (asked again whenever a certificate is handed out, so a new address is noticed).
func Open(dir string, names func() ([]string, []net.IP)) (*Authority, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	a := &Authority{dir: dir, names: names, now: time.Now}
	if err := a.loadCA(); err != nil {
		return nil, err
	}
	if _, err := a.certificate(); err != nil {
		return nil, err
	}
	return a, nil
}

// CAPEM is the authority's certificate, for laptops (and student Pis) to trust.
func (a *Authority) CAPEM() []byte { return a.caPEM }

// Fingerprint is the authority's SHA-256 fingerprint, in the form browsers and operating systems show.
func (a *Authority) Fingerprint() string {
	sum := sha256.Sum256(a.ca.Raw)
	h := strings.ToUpper(hex.EncodeToString(sum[:]))
	var parts []string
	for i := 0; i < len(h); i += 2 {
		parts = append(parts, h[i:i+2])
	}
	return strings.Join(parts, ":")
}

// TLSConfig is for the https listener.
func (a *Authority) TLSConfig() *tls.Config {
	return &tls.Config{
		MinVersion: tls.VersionTLS12,
		GetCertificate: func(*tls.ClientHelloInfo) (*tls.Certificate, error) {
			return a.certificate()
		},
	}
}

func readPEM(path, kind string) ([]byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	blk, _ := pem.Decode(b)
	if blk == nil || blk.Type != kind {
		return nil, fmt.Errorf("%s isn't a %s", path, kind)
	}
	return blk.Bytes, nil
}

func writePEM(path, kind string, der []byte, mode os.FileMode) error {
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, pem.EncodeToMemory(&pem.Block{Type: kind, Bytes: der}), mode); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func (a *Authority) loadCA() error {
	certDER, err1 := readPEM(filepath.Join(a.dir, caCertFile), "CERTIFICATE")
	keyDER, err2 := readPEM(filepath.Join(a.dir, caKeyFile), "EC PRIVATE KEY")
	if err1 == nil && err2 == nil {
		ca, err := x509.ParseCertificate(certDER)
		if err != nil {
			return err
		}
		key, err := x509.ParseECPrivateKey(keyDER)
		if err != nil {
			return err
		}
		a.ca, a.caKey = ca, key
		a.caPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})
		return nil
	}
	if !errors.Is(err1, os.ErrNotExist) && err1 != nil {
		return err1
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	now := a.now()
	host, _ := os.Hostname()
	tmpl := &x509.Certificate{
		SerialNumber:          serial(),
		Subject:               pkix.Name{CommonName: "Circuit Pathways school server (" + host + ")", Organization: []string{"Circuit Pathways"}},
		NotBefore:             now.Add(-time.Hour),
		NotAfter:              now.AddDate(caYears, 0, 0),
		IsCA:                  true,
		BasicConstraintsValid: true,
		MaxPathLenZero:        true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		// It may only vouch for names on the school's own network: .local names, plain names and private
		// addresses. (So installing it can't help anyone pretend to be a real website.)
		PermittedDNSDomainsCritical: true,
		PermittedDNSDomains:         []string{".local", ".lan", ".internal", ".home.arpa", "localhost"},
		PermittedIPRanges:           privateRanges(),
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		return err
	}
	keyDER, err = x509.MarshalECPrivateKey(key)
	if err != nil {
		return err
	}
	if err := writePEM(filepath.Join(a.dir, caKeyFile), "EC PRIVATE KEY", keyDER, 0o600); err != nil {
		return err
	}
	if err := writePEM(filepath.Join(a.dir, caCertFile), "CERTIFICATE", der, 0o644); err != nil {
		return err
	}
	return a.loadCA()
}

func privateRanges() []*net.IPNet {
	var out []*net.IPNet
	for _, c := range []string{"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "127.0.0.0/8", "100.64.0.0/10", "fc00::/7", "fe80::/10", "::1/128"} {
		_, n, _ := net.ParseCIDR(c)
		out = append(out, n)
	}
	return out
}

func serial() *big.Int {
	n, _ := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 120))
	return n.Add(n, big.NewInt(1))
}

// allowedName: a name the authority may vouch for (see PermittedDNSDomains).
func allowedName(n string) bool {
	if n == "localhost" {
		return true
	}
	for _, d := range []string{".local", ".lan", ".internal", ".home.arpa"} {
		if strings.HasSuffix(n, d) {
			return true
		}
	}
	return false
}

func allowedIP(ip net.IP) bool {
	for _, n := range privateRanges() {
		if n.Contains(ip) {
			return true
		}
	}
	return false
}

func (a *Authority) want() ([]string, []net.IP, string) {
	names, ips := a.names()
	var dns []string
	for _, n := range names {
		n = strings.ToLower(strings.TrimSuffix(n, "."))
		if allowedName(n) && !slices.Contains(dns, n) {
			dns = append(dns, n)
		}
	}
	var addrs []net.IP
	for _, ip := range ips {
		if allowedIP(ip) && !slices.ContainsFunc(addrs, ip.Equal) {
			addrs = append(addrs, ip)
		}
	}
	slices.Sort(dns)
	slices.SortFunc(addrs, func(x, y net.IP) int { return bytes.Compare(x.To16(), y.To16()) })
	key := strings.Join(dns, ",")
	for _, ip := range addrs {
		key += "," + ip.String()
	}
	return dns, addrs, key
}

func (a *Authority) certificate() (*tls.Certificate, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	dns, ips, key := a.want()
	now := a.now()
	if a.leaf != nil && a.leafOf == key && now.Before(a.leaf.Leaf.NotAfter.AddDate(0, 0, -renewDays)) {
		return a.leaf, nil
	}
	// the one on disk, if it is still right
	if c, err := tls.LoadX509KeyPair(filepath.Join(a.dir, leafCert), filepath.Join(a.dir, leafKey)); err == nil && c.Leaf != nil {
		if sameNames(c.Leaf, dns, ips) && now.Before(c.Leaf.NotAfter.AddDate(0, 0, -renewDays)) && c.Leaf.CheckSignatureFrom(a.ca) == nil {
			a.leaf, a.leafOf = &c, key
			return a.leaf, nil
		}
	}
	k, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, err
	}
	cn := "localhost"
	if len(dns) > 0 {
		cn = dns[0]
	}
	tmpl := &x509.Certificate{
		SerialNumber: serial(),
		Subject:      pkix.Name{CommonName: cn, Organization: []string{"Circuit Pathways"}},
		NotBefore:    now.Add(-time.Hour),
		NotAfter:     now.AddDate(0, 0, leafDays),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     dns,
		IPAddresses:  ips,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, a.ca, &k.PublicKey, a.caKey)
	if err != nil {
		return nil, err
	}
	kDER, err := x509.MarshalECPrivateKey(k)
	if err != nil {
		return nil, err
	}
	if err := writePEM(filepath.Join(a.dir, leafKey), "EC PRIVATE KEY", kDER, 0o600); err != nil {
		return nil, err
	}
	if err := writePEM(filepath.Join(a.dir, leafCert), "CERTIFICATE", der, 0o644); err != nil {
		return nil, err
	}
	leaf, err := x509.ParseCertificate(der)
	if err != nil {
		return nil, err
	}
	a.leaf = &tls.Certificate{Certificate: [][]byte{der, a.ca.Raw}, PrivateKey: k, Leaf: leaf}
	a.leafOf = key
	return a.leaf, nil
}

func sameNames(c *x509.Certificate, dns []string, ips []net.IP) bool {
	have := slices.Clone(c.DNSNames)
	slices.Sort(have)
	if !slices.Equal(have, dns) || len(c.IPAddresses) != len(ips) {
		return false
	}
	for _, ip := range ips {
		if !slices.ContainsFunc(c.IPAddresses, ip.Equal) {
			return false
		}
	}
	return true
}

// LocalNames are this computer's names and its addresses on the network: host.local,
// localhost, any extra names given, and every address on an interface that is up.
func LocalNames(extra ...string) func() ([]string, []net.IP) {
	return func() ([]string, []net.IP) {
		names := append([]string{"localhost"}, extra...)
		if h, err := os.Hostname(); err == nil && h != "" {
			h = strings.ToLower(strings.Split(h, ".")[0])
			names = append(names, h+".local") // (a bare name such as "pathways" can't be vouched for)
		}
		var ips []net.IP
		ifs, _ := net.Interfaces()
		for _, i := range ifs {
			if i.Flags&net.FlagUp == 0 {
				continue
			}
			addrs, _ := i.Addrs()
			for _, ad := range addrs {
				if n, ok := ad.(*net.IPNet); ok && !n.IP.IsLinkLocalUnicast() {
					ips = append(ips, n.IP)
				}
			}
		}
		return names, ips
	}
}
