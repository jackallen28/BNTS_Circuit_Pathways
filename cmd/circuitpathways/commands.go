package main

import (
	"bufio"
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"circuitpathways/internal/auth"
	"circuitpathways/internal/pilink"
	"circuitpathways/internal/store"
	"circuitpathways/internal/tlsca"
)

const commandHelp = `circuitpathways looks after the school server. Commands (run them with sudo on the server Pi):

  teacher add ["label"]       make a new teacher code (prints it). A label such as "Ms Lee" helps you tell them apart.
  teacher add CODE ["label"]  add a code you choose (8 to 64 characters, no spaces)
  teacher list                the teacher codes
  teacher remove CODE|label   take a code off (that teacher's classes can no longer be opened)
  status                      how many classes, students and pieces of work are kept
  backup [FILE]               copy everything (classes, names, work) into the data folder's backups/ (or FILE)
  wipe                        delete every class, student and piece of work (the end of a program)
  certificate                 make the https certificate if needed, and print its fingerprint
  pi-key                      (a student Pi) this Pi's own Pi Link key
  pi-installer -server URL -key KEY   (a student Pi) the Pi Link installer
  pi-app -server URL          (a student Pi) the Pi Link app, for that address
  self-update -from school|github ...  update to the school server's version (a student Pi) or the newest release

Each takes -data DIR (default ` + defaultData + `).`

func command(name string, args []string) error {
	if name == "self-update" {
		return updateCommand(args)
	}
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	data := fs.String("data", env("CIRCUITPATHWAYS_DATA", defaultData), "the data folder")
	serverURL := fs.String("server", "", "pi-installer: the site the Pi links to")
	key := fs.String("key", "", "pi-installer: the Pi's key")
	// flags may come before or after the words
	var words []string
	for len(args) > 0 {
		if err := fs.Parse(args); err != nil {
			return err
		}
		args = fs.Args()
		if len(args) > 0 {
			words = append(words, args[0])
			args = args[1:]
		}
	}
	codes := filepath.Join(*data, "teacher-codes.txt")
	if name != "pi-key" && name != "pi-installer" && name != "pi-app" {
		if err := becomeOwner(*data); err != nil {
			return fmt.Errorf("couldn't act as the owner of %s: %w", *data, err)
		}
	}
	switch name {
	case "help", "-h", "--help":
		fmt.Println(commandHelp)
		return nil
	case "teacher", "teachers":
		if len(words) == 0 {
			words = []string{"list"}
		}
		switch words[0] {
		case "add":
			code, label := "", ""
			rest := words[1:]
			if len(rest) == 2 {
				code, label = rest[0], rest[1]
			} else if len(rest) == 1 {
				if len(rest[0]) >= auth.MinCode && !strings.Contains(rest[0], " ") && strings.ContainsAny(rest[0], "0123456789-_") {
					code = rest[0]
				} else {
					label = rest[0]
				}
			}
			c, err := auth.AddCode(codes, code, label)
			if err != nil {
				return err
			}
			fmt.Println(c)
			return nil
		case "list":
			list, err := auth.ReadCodes(codes)
			if err != nil && !errors.Is(err, os.ErrNotExist) {
				return err
			}
			for _, e := range list {
				if e.Label != "" {
					fmt.Printf("%s   (%s)\n", e.Code, e.Label)
				} else {
					fmt.Println(e.Code)
				}
			}
			return nil
		case "remove":
			if len(words) != 2 {
				return errors.New("usage: circuitpathways teacher remove CODE (or its label)")
			}
			n, err := auth.RemoveCode(codes, words[1])
			if err != nil {
				return err
			}
			if n == 0 {
				return errors.New("no teacher code like that was found (circuitpathways teacher list shows them)")
			}
			fmt.Printf("Removed %d teacher code(s).\n", n)
			return nil
		}
		return errors.New("usage: circuitpathways teacher add|list|remove")
	case "status":
		st, err := store.Open(filepath.Join(*data, "pathways.db"))
		if err != nil {
			return err
		}
		defer st.Close()
		c, err := st.Totals(context.Background())
		if err != nil {
			return err
		}
		list, _ := auth.ReadCodes(codes)
		fmt.Printf("Classes: %d   Students: %d   Pieces of work: %d   Teacher codes: %d\nData folder: %s\n", c.Classes, c.Students, c.Work, len(list), *data)
		return nil
	case "backup":
		if len(words) > 1 {
			return errors.New("usage: circuitpathways backup [FILE]")
		}
		file := filepath.Join(*data, "backups", "pathways-"+time.Now().Format("2006-01-02-1504")+".db")
		if len(words) == 1 {
			file = words[0]
		}
		if _, err := os.Stat(file); err == nil {
			return errors.New(file + " already exists: pick a new file name")
		}
		if err := os.MkdirAll(filepath.Dir(file), 0o700); err != nil {
			return err
		}
		st, err := store.Open(filepath.Join(*data, "pathways.db"))
		if err != nil {
			return err
		}
		defer st.Close()
		if err := st.Backup(context.Background(), file); err != nil {
			return err
		}
		os.Chmod(file, 0o600)
		fmt.Printf("Saved a copy in %s\nIt holds students' first names and work: keep it private, and delete it when it's no longer needed.\nTo copy it to a USB stick:  sudo cp %s /media/$USER/YOUR-STICK/\n", file, file)
		return nil
	case "wipe":
		fmt.Print("This deletes EVERY class, every student's name and all their work on this server.\nType WIPE to go ahead: ")
		line, _ := bufio.NewReader(os.Stdin).ReadString('\n')
		if strings.TrimSpace(line) != "WIPE" {
			return errors.New("nothing was deleted")
		}
		st, err := store.Open(filepath.Join(*data, "pathways.db"))
		if err != nil {
			return err
		}
		defer st.Close()
		ctx := context.Background()
		if err := st.Wipe(ctx); err != nil {
			return err
		}
		if err := st.Compact(ctx); err != nil {
			return err
		}
		fmt.Println("Everything has been deleted. Teacher codes are kept.")
		return nil
	case "certificate":
		a, err := tlsca.Open(filepath.Join(*data, "tls"), tlsca.LocalNames())
		if err != nil {
			return err
		}
		fmt.Println(a.Fingerprint())
		return nil
	case "pi-key":
		k, err := thisPiKey(*data)
		if err != nil {
			return err
		}
		fmt.Println(k)
		return nil
	case "pi-app":
		if *serverURL == "" {
			return errors.New("usage: circuitpathways pi-app -server http://localhost:8080")
		}
		src, err := piAppSource()
		if err != nil {
			return err
		}
		fmt.Print(strings.ReplaceAll(string(src), pilink.PlaceholderServer, strings.TrimRight(*serverURL, "/")))
		return nil
	case "pi-installer":
		if *serverURL == "" || *key == "" {
			return errors.New("usage: circuitpathways pi-installer -server http://localhost:8080 -key CPK1-...")
		}
		s, err := piInstaller(*serverURL, *key)
		if err != nil {
			return err
		}
		fmt.Print(s)
		return nil
	}
	return fmt.Errorf("there's no command %q.\n\n%s", name, commandHelp)
}
