// Command circuitpathways is Circuit Pathways: PiPath and ArduinoPath in the browser, served by the school's
// own Raspberry Pi. The same program is the school server (the main Pi: the site, classes and the compiler
// for every computer on the network) and runs on each student Pi (the site and Pi Link on the Pi itself,
// working offline, with classes passed on to the school server). See docs/server.md.
//
//	circuitpathways -dev                                   try it on this computer: http://localhost:8080
//	circuitpathways -mode school -data DIR -http :80 -https :443
//	circuitpathways -mode student-pi -school https://pathways.local -school-ca FILE -data DIR
//	circuitpathways teacher add|list|remove ...            the school's teacher codes
//	circuitpathways status | backup FILE | wipe | certificate | pi-key | pi-installer
//	circuitpathways -setup [-warm] -tools DIR              install the board tools (needs the internet)
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"circuitpathways"
	"circuitpathways/internal/arduino"
	"circuitpathways/internal/auth"
	"circuitpathways/internal/content"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/server"
	"circuitpathways/internal/store"
	"circuitpathways/internal/tlsca"
)

// Version and Commit are set at build time: -ldflags "-X main.Version=1.2.3 -X main.Commit=abc1234".
var (
	Version = "dev"
	Commit  = ""
)

const defaultData = "/var/lib/circuitpathways"

func main() {
	if len(os.Args) > 1 && !strings.HasPrefix(os.Args[1], "-") {
		if err := command(os.Args[1], os.Args[2:]); err != nil {
			fmt.Fprintln(os.Stderr, "Sorry:", err)
			os.Exit(1)
		}
		return
	}
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))
	mode := flag.String("mode", server.ModeSchool, "school (the main Pi) or student-pi (a student's Pi)")
	addr := flag.String("addr", ":"+env("PORT", "8080"), "address to listen on (plain http: -dev, a student Pi, or a school server with no -http/-https)")
	httpAddr := flag.String("http", "", "school server: the plain http address (e.g. :80): the trust page, the student Pi installer, and the site")
	httpsAddr := flag.String("https", "", "school server: the https address (e.g. :443), with the server's own certificate")
	dataDir := flag.String("data", env("CIRCUITPATHWAYS_DATA", defaultData), "where classes, secrets and certificates are kept")
	toolsDir := flag.String("tools", env("TOOLS_DIR", "/opt/circuitpathways"), "folder with the Arduino tools installed by -setup")
	setup := flag.Bool("setup", false, "install arduino-cli, the board cores and libraries into -tools, then stop")
	warm := flag.Bool("warm", false, "after -setup, compile once for every board so the first student isn't slow")
	dev := flag.Bool("dev", false, "try it on this computer: a fresh data folder, the teacher code 'teacher-code-dev', no board tools needed")
	schoolURL := flag.String("school", "", "student Pi: the school server's address, e.g. https://pathways.local")
	schoolCA := flag.String("school-ca", "", "student Pi: the school server's certificate authority (from its installer)")
	schoolName := flag.String("school-name", env("SCHOOL", "Banyule Nillumbik Tech School"), "the school's name, filled in for new classes")
	piLink := flag.Bool("pi-link", false, "school server: also relay Pi Link (normally each student Pi has its own)")
	flag.Parse()

	if *setup {
		if err := runSetup(*toolsDir, *warm, log); err != nil {
			log.Error("setup", "err", err)
			os.Exit(1)
		}
		return
	}
	if err := serve(log, options{
		mode: *mode, dev: *dev, addr: *addr, httpAddr: *httpAddr, httpsAddr: *httpsAddr, data: *dataDir, tools: *toolsDir,
		school: *schoolURL, schoolCA: *schoolCA, schoolName: *schoolName, piLink: *piLink,
	}); err != nil {
		log.Error("Circuit Pathways couldn't start", "err", err)
		os.Exit(1)
	}
}

type options struct {
	mode, addr, httpAddr, httpsAddr, data, tools, school, schoolCA, schoolName string
	dev, piLink                                                                bool
}

func serve(log *slog.Logger, o options) error {
	if o.dev {
		if o.data == defaultData || o.data == "" {
			d, err := os.MkdirTemp("", "circuitpathways-dev-")
			if err != nil {
				return err
			}
			o.data = d
		}
		o.piLink = true
	}
	cat, problems := content.Load(circuitpathways.Content())
	if len(problems) > 0 {
		for _, p := range problems {
			log.Error("content problem", "problem", p.Error())
		}
		return errors.New("the projects and lessons have problems")
	}
	if err := os.MkdirAll(o.data, 0o700); err != nil {
		return fmt.Errorf("the data folder %s: %w", o.data, err)
	}
	cfg := server.Config{Site: circuitpathways.Site(), Catalogue: cat, Version: Version, Commit: Commit, Log: log, Mode: o.mode, School: o.schoolName}
	if host, err := os.Hostname(); err == nil {
		cfg.Name = strings.ToLower(strings.Split(host, ".")[0]) + ".local"
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	switch o.mode {
	case server.ModeSchool:
		st, err := store.Open(filepath.Join(o.data, "pathways.db"))
		if err != nil {
			return err
		}
		defer st.Close()
		secret, err := secretIn(o.data, "secret")
		if err != nil {
			return err
		}
		if cfg.Auth, err = auth.New(secret); err != nil {
			return err
		}
		extra := os.Getenv("TEACHER_CODES")
		if o.dev {
			extra += ",teacher-code-dev"
		}
		cfg.Teachers = auth.NewTeachers(filepath.Join(o.data, "teacher-codes.txt"), extra)
		if cfg.Teachers.Len() == 0 {
			log.Warn("there are no teacher codes yet: add one with  sudo circuitpathways teacher add \"Your name\"")
		}
		cfg.Store = st
		go cleanEveryDay(ctx, st, log)
	case server.ModeStudentPi:
		if o.school == "" {
			return errors.New("a student Pi needs -school, the school server's address (e.g. https://pathways.local)")
		}
		up, err := server.NewUpstream(o.school, o.schoolCA, log)
		if err != nil {
			return err
		}
		cfg.Upstream = up
		go up.Watch(ctx, 20*time.Second)
		o.piLink = true
	default:
		return fmt.Errorf("-mode must be %s or %s", server.ModeSchool, server.ModeStudentPi)
	}

	if o.piLink {
		piSecret := devPiKeySecret
		if !o.dev {
			var err error
			if piSecret, err = secretIn(o.data, "pi-key-secret"); err != nil {
				return err
			}
		}
		keys, err := pilink.NewKeys(piSecret, strings.FieldsFunc(os.Getenv("REVOKED_PI_IDS"), func(r rune) bool { return r == ',' || r == ' ' }))
		if err != nil {
			return err
		}
		cfg.PiKeys = keys
	}
	if tools, err := arduino.InstalledTools(o.tools, log); err == nil {
		cfg.Compiler = tools
	} else if o.mode == server.ModeSchool && !o.dev {
		log.Warn("no board tools: uploading to boards won't work until they are installed (circuitpathways -setup -warm)", "err", err)
	}

	var authority *tlsca.Authority
	if o.mode == server.ModeSchool && o.httpsAddr != "" {
		var err error
		if authority, err = tlsca.Open(filepath.Join(o.data, "tls"), tlsca.LocalNames()); err != nil {
			return fmt.Errorf("the https certificate: %w", err)
		}
		cfg.TLS = true
		if exe, err := os.Executable(); err == nil {
			_, port, _ := net.SplitHostPort(o.httpsAddr)
			cfg.Install = &server.Installer{Program: exe, CAPEM: authority.CAPEM(), HTTPSPort: port, Version: strings.TrimSpace(Version + " " + Commit)}
		}
	}

	h := server.New(cfg)
	var servers []*http.Server
	listen := func(addr string, secure bool) {
		srv := &http.Server{
			Addr: addr, Handler: h,
			ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second,
			WriteTimeout: 8 * time.Minute, IdleTimeout: 2 * time.Minute,
		}
		if secure {
			srv.TLSConfig = authority.TLSConfig()
		}
		servers = append(servers, srv)
	}
	switch {
	case o.mode == server.ModeSchool && (o.httpAddr != "" || o.httpsAddr != ""):
		if o.httpAddr != "" {
			listen(o.httpAddr, false)
		}
		if o.httpsAddr != "" {
			listen(o.httpsAddr, true)
		}
	default:
		listen(o.addr, false)
	}

	errs := make(chan error, len(servers))
	for _, srv := range servers {
		go func(srv *http.Server) {
			var err error
			if srv.TLSConfig != nil {
				err = srv.ListenAndServeTLS("", "")
			} else {
				err = srv.ListenAndServe()
			}
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				errs <- fmt.Errorf("%s: %w", srv.Addr, err)
			}
		}(srv)
	}
	addrs := []string{}
	for _, srv := range servers {
		addrs = append(addrs, srv.Addr)
	}
	log.Info("Circuit Pathways is ready", "mode", o.mode, "listening", strings.Join(addrs, " "), "version", Version, "compile", cfg.Compiler != nil,
		"teacher_codes", teacherCount(cfg), "data", o.data)
	select {
	case <-ctx.Done():
	case err := <-errs:
		return err
	}
	sc, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	for _, srv := range servers {
		srv.Shutdown(sc)
	}
	return nil
}

func teacherCount(cfg server.Config) int {
	if cfg.Teachers == nil {
		return 0
	}
	return cfg.Teachers.Len()
}

// cleanEveryDay deletes classes that have ended (with their students and work), now and then every few hours.
func cleanEveryDay(ctx context.Context, st *store.Store, log *slog.Logger) {
	t := time.NewTicker(3 * time.Hour)
	defer t.Stop()
	for {
		if n, err := st.CleanUp(ctx, time.Now()); err != nil {
			log.Error("clean-up", "err", err)
		} else if n > 0 {
			log.Info("deleted classes that have ended", "classes", n)
			st.Compact(ctx)
		}
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func runSetup(dir string, warm bool, log *slog.Logger) error {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Minute)
	defer cancel()
	e := &arduino.Env{Dir: dir, Log: log}
	if err := e.Setup(ctx); err != nil {
		return err
	}
	if !warm {
		return nil
	}
	cat, problems := content.Load(circuitpathways.Content())
	if len(problems) > 0 {
		return fmt.Errorf("content: %s", problems[0].Error())
	}
	tools, err := arduino.InstalledTools(dir, log)
	if err != nil {
		return err
	}
	for _, b := range cat.Boards {
		start := time.Now()
		res, _, err := tools.Compile(ctx, "void setup() {}\nvoid loop() {}\n", b.FQBN, b.BuildProperties)
		if err != nil || !res.OK {
			return fmt.Errorf("warm-up compile for %s failed: %v %s", b.ID, err, res.Output)
		}
		log.Info("warmed", "board", b.ID, "took", time.Since(start).Round(time.Second))
	}
	return nil
}
