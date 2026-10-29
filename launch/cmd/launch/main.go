// Command launch is the Circuit Pathways website: PiPath and ArduinoPath in
// the browser. See README.md for how to run it on Render.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"circuitpathways"
	"circuitpathways/internal/arduino"
	"circuitpathways/internal/classes"
	"circuitpathways/internal/content"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/server"
)

// Version is set at build time: -ldflags "-X main.Version=1.2.3".
var Version = "dev"

func main() {
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))
	addr := flag.String("addr", ":"+env("PORT", "8080"), "address to listen on")
	toolsDir := flag.String("tools", env("TOOLS_DIR", "/opt/circuitpathways"), "folder with the Arduino tools installed by -setup")
	setup := flag.Bool("setup", false, "install arduino-cli, the board cores and libraries into -tools, then stop (done when the image is built)")
	warm := flag.Bool("warm", false, "after -setup, compile once for every board so the first student isn't slow")
	dev := flag.Bool("dev", false, "development: random secrets, a teacher code of 'teacher-code-dev', no board tools needed")
	piKeys := flag.Int("pi-keys", 0, "make this many Raspberry Pi keys (and an installer for each Pi) with PI_KEY_SECRET, then stop")
	piOut := flag.String("pi-out", "pi-keys", "the folder -pi-keys writes into")
	piServer := flag.String("server", env("SITE_URL", pilink.PlaceholderServer), "the website address written into each Pi's installer (-pi-keys)")
	flag.Parse()

	if *piKeys > 0 {
		if err := makePiKeys(*piKeys, *piOut, *piServer); err != nil {
			fmt.Fprintln(os.Stderr, "Sorry:", err)
			os.Exit(1)
		}
		return
	}

	if *setup {
		if err := runSetup(*toolsDir, *warm, log); err != nil {
			log.Error("setup", "err", err)
			os.Exit(1)
		}
		return
	}

	secret := os.Getenv("CLASS_SECRET")
	teachers := os.Getenv("TEACHER_CODES")
	if *dev {
		if secret == "" {
			b := make([]byte, 16)
			rand.Read(b)
			secret = hex.EncodeToString(b)
		}
		if teachers == "" {
			teachers = "teacher-code-dev"
		}
	}
	signer, err := classes.New(secret)
	if err != nil {
		log.Error("set CLASS_SECRET to a long random text (at least 16 characters)", "err", err)
		os.Exit(1)
	}
	piSecret := os.Getenv("PI_KEY_SECRET")
	if *dev && piSecret == "" {
		piSecret = devPiKeySecret
	}
	var keys *pilink.Keys
	if piSecret != "" {
		if keys, err = pilink.NewKeys(piSecret, strings.FieldsFunc(os.Getenv("REVOKED_PI_IDS"), func(r rune) bool { return r == ',' || r == ' ' || r == '\n' })); err != nil {
			log.Error("set PI_KEY_SECRET to a long random text (at least 16 characters)", "err", err)
			os.Exit(1)
		}
	} else {
		log.Warn("PI_KEY_SECRET isn't set: Pi Link is switched off")
	}
	tc := classes.ParseTeacherCodes(teachers)
	if tc.Len() == 0 {
		log.Error("set TEACHER_CODES to one or more teacher codes (each at least 8 characters), separated by commas")
		os.Exit(1)
	}
	cat, problems := content.Load(launch.Content())
	if len(problems) > 0 {
		for _, p := range problems {
			log.Error("content problem", "problem", p.Error())
		}
		os.Exit(1)
	}
	cfg := server.Config{Site: launch.Site(), Catalogue: cat, Signer: signer, Teachers: tc, PiKeys: keys, Version: Version, Log: log}
	if tools, err := arduino.InstalledTools(*toolsDir, log); err == nil {
		cfg.Compiler = tools
	} else if *dev {
		log.Warn("no board tools: compiling for real boards is off", "err", err)
	} else {
		log.Error("no board tools: uploading to boards won't work", "err", err)
	}

	srv := &http.Server{
		Addr: *addr, Handler: server.New(cfg),
		ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second,
		WriteTimeout: 8 * time.Minute, IdleTimeout: 2 * time.Minute,
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		sc, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		srv.Shutdown(sc)
	}()
	log.Info("Circuit Pathways is ready", "addr", *addr, "version", Version, "compile", cfg.Compiler != nil, "teacher_codes", tc.Len())
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Error("server", "err", err)
		os.Exit(1)
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
	cat, problems := content.Load(launch.Content())
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
