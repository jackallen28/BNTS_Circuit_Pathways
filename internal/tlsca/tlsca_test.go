package tlsca

import (
	"crypto/x509"
	"net"
	"testing"
	"time"
)

func TestTheCertificateIsForTheServerAndChangesWithItsAddress(t *testing.T) {
	dir := t.TempDir()
	ip := net.ParseIP("192.168.1.20")
	names := func() ([]string, []net.IP) {
		return []string{"localhost", "pathways.local", "pathways", "evil.example.com"}, []net.IP{ip, net.ParseIP("8.8.8.8")}
	}
	a, err := Open(dir, names)
	if err != nil {
		t.Fatal(err)
	}
	c, err := a.certificate()
	if err != nil {
		t.Fatal(err)
	}
	if got := c.Leaf.DNSNames; len(got) != 2 || got[0] != "localhost" || got[1] != "pathways.local" {
		t.Fatalf("names: %v (only local names may be in it)", got)
	}
	if len(c.Leaf.IPAddresses) != 1 || !c.Leaf.IPAddresses[0].Equal(ip) {
		t.Fatalf("addresses: %v (only private ones)", c.Leaf.IPAddresses)
	}
	pool := x509.NewCertPool()
	pool.AppendCertsFromPEM(a.CAPEM())
	for _, host := range []string{"pathways.local", "192.168.1.20", "localhost"} {
		if _, err := c.Leaf.Verify(x509.VerifyOptions{Roots: pool, DNSName: host}); err != nil {
			t.Errorf("%s: %v", host, err)
		}
	}

	// the authority can't vouch for a real website, even if someone stole its key
	bad := *c.Leaf
	if _, err := bad.Verify(x509.VerifyOptions{Roots: pool, DNSName: "evil.example.com"}); err == nil {
		t.Fatal("verified a name that isn't the server's")
	}

	// opening again keeps the same authority and certificate
	b, err := Open(dir, names)
	if err != nil {
		t.Fatal(err)
	}
	if b.Fingerprint() != a.Fingerprint() {
		t.Fatal("the authority changed")
	}
	c2, _ := b.certificate()
	if c2.Leaf.SerialNumber.Cmp(c.Leaf.SerialNumber) != 0 {
		t.Fatal("made a new certificate for no reason")
	}

	// a new address: a new certificate from the same authority
	ip = net.ParseIP("10.0.0.5")
	c3, _ := b.certificate()
	if !c3.Leaf.IPAddresses[0].Equal(ip) {
		t.Fatal("didn't notice the new address")
	}
	if _, err := c3.Leaf.Verify(x509.VerifyOptions{Roots: pool, DNSName: "10.0.0.5"}); err != nil {
		t.Fatal(err)
	}

	// and an old one is made again before it runs out
	b.now = func() time.Time { return time.Now().AddDate(0, 0, leafDays-10) }
	c4, _ := b.certificate()
	if c4.Leaf.SerialNumber.Cmp(c3.Leaf.SerialNumber) == 0 {
		t.Fatal("didn't renew")
	}
}
