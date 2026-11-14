package store

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"
	"time"
)

func TestTheDatabaseKeepsItsWorkAndRefusesANewerVersion(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "pathways.db")
	s, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	c, err := s.NewClass(ctx, "teacher1", "7B", "Eltham High", now, now.Add(48*time.Hour).UnixMilli())
	if err != nil {
		t.Fatal(err)
	}
	id, _ := s.Join(ctx, c.Code, []string{"Mia"}, "Eltham High", now)
	s.SaveWork(ctx, id, []Work{{App: "pipath", Item: "s1_hello", Kind: "sketch", Body: "print(1)", UpdatedAt: 5}}, now)
	s.Close()

	// opened again (a restart): everything is still there
	s, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if w, _ := s.MyWork(ctx, id); len(w) != 1 || w[0].Body != "print(1)" {
		t.Fatalf("after a restart: %v", w)
	}
	// a backup has it too
	bk := filepath.Join(t.TempDir(), "backup.db")
	if err := s.Backup(ctx, bk); err != nil {
		t.Fatal(err)
	}
	b, err := Open(bk)
	if err != nil {
		t.Fatal(err)
	}
	if w, _ := b.MyWork(ctx, id); len(w) != 1 {
		t.Fatal("the backup is missing work")
	}
	b.Close()
	// wipe: nothing left, and the file is compacted
	if err := s.Wipe(ctx); err != nil {
		t.Fatal(err)
	}
	if err := s.Compact(ctx); err != nil {
		t.Fatal(err)
	}
	if n, _ := s.Totals(ctx); n.Classes+n.Students+n.Work != 0 {
		t.Fatalf("after a wipe: %+v", n)
	}
	s.Close()

	// a database from a newer Circuit Pathways isn't opened (so it is never damaged by an older one)
	db, _ := sql.Open("sqlite", "file:"+path)
	db.Exec("UPDATE meta SET value = '99' WHERE key = 'schema'")
	db.Close()
	if _, err := Open(path); err == nil {
		t.Fatal("opened a database from a newer version")
	}
}

func TestEndDatesAreChecked(t *testing.T) {
	now := time.Now()
	days := func(n int) *int { return &n }
	at := func(d time.Duration) *int64 { v := now.Add(d).UnixMilli(); return &v }
	if _, err := EndsAt(now, nil, days(0)); err == nil {
		t.Error("0 days")
	}
	if _, err := EndsAt(now, nil, days(MaxDays+1)); err == nil {
		t.Error("too many days")
	}
	if _, err := EndsAt(now, at(-time.Hour), nil); err == nil {
		t.Error("in the past")
	}
	if e, err := EndsAt(now, nil, nil); err != nil || e <= now.UnixMilli() {
		t.Error("the default length")
	}
	if NormaliseCode(" abcde-fghi1 ") != "ABCDEFGH11" || ShowCode("ABCDEFGHJK") != "ABCDE-FGHJK" {
		t.Error("codes")
	}
}
