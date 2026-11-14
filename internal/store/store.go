// Package store keeps classes on the school's Circuit Pathways server (the main Raspberry Pi), in one
// SQLite file. The only things kept about a student are their first name(s) and school, and their work
// (code, progress and settings) for the class. A class ends on the date its teacher picks, and the
// clean-up deletes it with everyone and everything in it. Teachers can delete sooner.
package store

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// Limits, the same as the first (Cloudflare) version of the classes.
const (
	MaxDays               = 400
	MaxItemsPerStudent    = 300
	MaxStudentsPerClass   = 200
	MaxClassesPerTeacher  = 60
	MaxTasksPerClass      = 40
	schemaVersion         = 3
	alphabet              = "0123456789ABCDEFGHJKMNPQRSTVWXYZ" // Crockford's base 32: no I, L, O or U
	day                   = 24 * time.Hour
	classCodeLen          = 10
	studentIDLen          = 32
	defaultClassLength    = 30 * day
	maxTaskNoteCharacters = 200
)

// Errors the server turns into friendly messages.
var (
	ErrNotFound      = errors.New("not found")
	ErrTooMany       = errors.New("too many")
	ErrClassFull     = errors.New("class full")
	ErrTooMuchWork   = errors.New("too much work")
	ErrBadEnd        = errors.New("bad end date")
	ErrBadTask       = errors.New("bad task")
	ErrCodeCollision = errors.New("couldn't make a new code")
)

// Store is the database.
type Store struct {
	db *sql.DB
}

const schema = `
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classes (
  code       TEXT PRIMARY KEY,          -- ABCDEFGHJK (shown as ABCDE-FGHJK)
  teacher    TEXT NOT NULL,             -- a one-way fingerprint of the teacher's code, never the code
  name       TEXT NOT NULL,             -- the teacher's label, e.g. "7B Thursday"
  school     TEXT NOT NULL,
  created_at INTEGER NOT NULL,          -- ms since 1970
  ends_at    INTEGER NOT NULL           -- after this the class and everything in it is deleted
);
CREATE INDEX IF NOT EXISTS classes_teacher ON classes(teacher);
CREATE INDEX IF NOT EXISTS classes_ends ON classes(ends_at);
CREATE TABLE IF NOT EXISTS students (
  id         TEXT PRIMARY KEY,          -- random
  class_code TEXT NOT NULL REFERENCES classes(code) ON DELETE CASCADE,
  names      TEXT NOT NULL,             -- JSON array of 1-4 first names
  school     TEXT NOT NULL,
  joined_at  INTEGER NOT NULL,
  seen_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS students_class ON students(class_code);
CREATE TABLE IF NOT EXISTS work (
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  app        TEXT NOT NULL,             -- arduinopath | pipath
  item       TEXT NOT NULL,             -- a project or activity id
  kind       TEXT NOT NULL,             -- sketch | progress | settings
  body       TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (student_id, app, item, kind)
);
CREATE TABLE IF NOT EXISTS tasks (        -- the work a teacher sets for a class
  class_code TEXT NOT NULL REFERENCES classes(code) ON DELETE CASCADE,
  app        TEXT NOT NULL,             -- arduinopath | pipath
  item       TEXT NOT NULL,             -- a project or activity id ("freeplay" for Free Play)
  note       TEXT NOT NULL DEFAULT '',  -- the teacher's words, e.g. "by Friday"
  position   INTEGER NOT NULL,
  set_at     INTEGER NOT NULL,
  PRIMARY KEY (class_code, app, item)
);
`

// Open opens (or makes) the database file. ":memory:" is a database for tests.
func Open(path string) (*Store, error) {
	dsn := "file:" + path + "?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=synchronous(FULL)&_pragma=secure_delete(1)"
	if path == ":memory:" {
		dsn = "file::memory:?_pragma=foreign_keys(1)"
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	if path == ":memory:" {
		db.SetMaxOpenConns(1) // every connection would be a different empty database
	}
	if _, err := db.Exec(schema + boardsSchema); err != nil {
		db.Close()
		return nil, fmt.Errorf("making the database: %w", err)
	}
	var v int
	_ = db.QueryRow("SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'schema'").Scan(&v)
	if v > schemaVersion {
		db.Close()
		return nil, fmt.Errorf("this database is from a newer Circuit Pathways (version %d)", v)
	}
	if _, err := db.Exec("INSERT INTO meta (key, value) VALUES ('schema', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", fmt.Sprint(schemaVersion)); err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db}, nil
}

// Close closes the database.
func (s *Store) Close() error { return s.db.Close() }

// Ping checks the database answers.
func (s *Store) Ping(ctx context.Context) error { return s.db.PingContext(ctx) }

// Class is one class.
type Class struct {
	Code      string `json:"code"` // shown with a dash: ABCDE-FGHJK
	Name      string `json:"name"`
	School    string `json:"school"`
	CreatedAt int64  `json:"created_at"`
	EndsAt    int64  `json:"ends_at"`
	Students  *int   `json:"students,omitempty"`
	teacher   string
}

// Student is one student in a class, as the teacher sees them.
type Student struct {
	ID       string   `json:"id"`
	Names    []string `json:"names"`
	School   string   `json:"school"`
	JoinedAt int64    `json:"joined_at"`
	SeenAt   int64    `json:"seen_at"`
	Items    int      `json:"items"`
	LastWork *int64   `json:"last_work"`
}

// Work is one piece of a student's work.
type Work struct {
	App       string `json:"app"`
	Item      string `json:"item"`
	Kind      string `json:"kind"`
	Body      string `json:"body"`
	UpdatedAt int64  `json:"updated_at"`
}

// Task is a piece of work a teacher sets.
type Task struct {
	App   string `json:"app"`
	Item  string `json:"item"`
	Note  string `json:"note"`
	SetAt int64  `json:"set_at"`
}

// Member is a student with their class, for the student's own requests.
type Member struct {
	ID          string
	Names       []string
	School      string
	ClassCode   string
	ClassName   string
	ClassSchool string
	EndsAt      int64
}

// ShowCode puts the dash back: ABCDEFGHJK -> ABCDE-FGHJK.
func ShowCode(c string) string {
	if len(c) == classCodeLen {
		return c[:5] + "-" + c[5:]
	}
	return c
}

// NormaliseCode tidies a typed code: upper case, no spaces or dashes, look-alikes fixed.
func NormaliseCode(s string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(s) {
		switch r {
		case ' ', '-', '_', '\t':
			continue
		case 'I', 'L':
			r = '1'
		case 'O':
			r = '0'
		}
		b.WriteRune(r)
	}
	return b.String()
}

func randomCode() (string, error) {
	b := make([]byte, classCodeLen)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	for i := range b {
		b[i] = alphabet[b[i]&31]
	}
	return string(b), nil
}

// RandomID is 32 hex characters.
func RandomID() string {
	b := make([]byte, studentIDLen/2)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func ms(t time.Time) int64 { return t.UnixMilli() }

// EndsAt works out a class's end from either an exact time (ms) or a number of days.
func EndsAt(now time.Time, endsAt *int64, days *int) (int64, error) {
	n := ms(now)
	var ends int64
	switch {
	case endsAt != nil:
		ends = *endsAt
	case days != nil:
		if *days < 1 || *days > MaxDays {
			return 0, ErrBadEnd
		}
		ends = n + int64(*days)*int64(day/time.Millisecond)
	default:
		ends = n + int64(defaultClassLength/time.Millisecond)
	}
	if ends <= n || ends > n+int64(MaxDays)*int64(day/time.Millisecond) {
		return 0, ErrBadEnd
	}
	return ends, nil
}

// NewClass makes a class for a teacher.
func (s *Store) NewClass(ctx context.Context, teacher, name, school string, now time.Time, ends int64) (Class, error) {
	var n int
	if err := s.db.QueryRowContext(ctx, "SELECT count(*) FROM classes WHERE teacher = ? AND ends_at > ?", teacher, ms(now)).Scan(&n); err != nil {
		return Class{}, err
	}
	if n >= MaxClassesPerTeacher {
		return Class{}, ErrTooMany
	}
	for i := 0; i < 5; i++ {
		code, err := randomCode()
		if err != nil {
			return Class{}, err
		}
		res, err := s.db.ExecContext(ctx, "INSERT OR IGNORE INTO classes (code, teacher, name, school, created_at, ends_at) VALUES (?, ?, ?, ?, ?, ?)", code, teacher, name, school, ms(now), ends)
		if err != nil {
			return Class{}, err
		}
		if c, _ := res.RowsAffected(); c == 1 {
			zero := 0
			return Class{Code: ShowCode(code), Name: name, School: school, CreatedAt: ms(now), EndsAt: ends, Students: &zero}, nil
		}
	}
	return Class{}, ErrCodeCollision
}

func scanClass(row interface{ Scan(...any) error }) (Class, error) {
	var c Class
	err := row.Scan(&c.Code, &c.teacher, &c.Name, &c.School, &c.CreatedAt, &c.EndsAt)
	if errors.Is(err, sql.ErrNoRows) {
		return c, ErrNotFound
	}
	c.Code = ShowCode(c.Code)
	return c, err
}

// TeacherClasses are the classes a teacher has running, newest first, with how many students each has.
func (s *Store) TeacherClasses(ctx context.Context, teacher string, now time.Time) ([]Class, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT c.code, c.teacher, c.name, c.school, c.created_at, c.ends_at, (SELECT count(*) FROM students s WHERE s.class_code = c.code) FROM classes c WHERE c.teacher = ? AND c.ends_at > ? ORDER BY c.created_at DESC, c.code", teacher, ms(now))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Class{}
	for rows.Next() {
		var c Class
		var n int
		if err := rows.Scan(&c.Code, &c.teacher, &c.Name, &c.School, &c.CreatedAt, &c.EndsAt, &n); err != nil {
			return nil, err
		}
		c.Code = ShowCode(c.Code)
		c.Students = &n
		out = append(out, c)
	}
	return out, rows.Err()
}

// TeacherClass is one of the teacher's classes (ErrNotFound if it isn't theirs or has ended).
func (s *Store) TeacherClass(ctx context.Context, teacher, code string, now time.Time) (Class, error) {
	return scanClass(s.db.QueryRowContext(ctx, "SELECT code, teacher, name, school, created_at, ends_at FROM classes WHERE code = ? AND teacher = ? AND ends_at > ?", NormaliseCode(code), teacher, ms(now)))
}

// RunningClass is a class that hasn't ended, found by its code.
func (s *Store) RunningClass(ctx context.Context, code string, now time.Time) (Class, error) {
	c := NormaliseCode(code)
	if len(c) != classCodeLen {
		return Class{}, ErrNotFound
	}
	return scanClass(s.db.QueryRowContext(ctx, "SELECT code, teacher, name, school, created_at, ends_at FROM classes WHERE code = ? AND ends_at > ?", c, ms(now)))
}

// Students lists a class's students, in the order they joined.
func (s *Store) Students(ctx context.Context, code string) ([]Student, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT s.id, s.names, s.school, s.joined_at, s.seen_at,
	  (SELECT count(*) FROM work w WHERE w.student_id = s.id), (SELECT max(updated_at) FROM work w WHERE w.student_id = s.id)
	  FROM students s WHERE s.class_code = ? ORDER BY s.joined_at, s.rowid`, NormaliseCode(code))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Student{}
	for rows.Next() {
		var st Student
		var names string
		var last sql.NullInt64
		if err := rows.Scan(&st.ID, &names, &st.School, &st.JoinedAt, &st.SeenAt, &st.Items, &last); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(names), &st.Names); err != nil {
			return nil, err
		}
		if last.Valid {
			st.LastWork = &last.Int64
		}
		out = append(out, st)
	}
	return out, rows.Err()
}

// StudentWork is a student (first names and school) with all their work, for the teacher.
type StudentWork struct {
	ID     string   `json:"id"`
	Names  []string `json:"names"`
	School string   `json:"school"`
	Work   []Work   `json:"work"`
}

// ClassWork is every student in a class with their work.
func (s *Store) ClassWork(ctx context.Context, code string) ([]StudentWork, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT s.id, s.names, s.school, w.app, w.item, w.kind, w.body, w.updated_at
	  FROM students s LEFT JOIN work w ON w.student_id = s.id WHERE s.class_code = ? ORDER BY s.joined_at, s.rowid, w.app, w.item, w.kind`, NormaliseCode(code))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []StudentWork{}
	index := map[string]int{}
	for rows.Next() {
		var id, names, school string
		var app, item, kind, body sql.NullString
		var at sql.NullInt64
		if err := rows.Scan(&id, &names, &school, &app, &item, &kind, &body, &at); err != nil {
			return nil, err
		}
		i, ok := index[id]
		if !ok {
			sw := StudentWork{ID: id, School: school, Work: []Work{}}
			if err := json.Unmarshal([]byte(names), &sw.Names); err != nil {
				return nil, err
			}
			out = append(out, sw)
			i = len(out) - 1
			index[id] = i
		}
		if app.Valid {
			out[i].Work = append(out[i].Work, Work{App: app.String, Item: item.String, Kind: kind.String, Body: body.String, UpdatedAt: at.Int64})
		}
	}
	return out, rows.Err()
}

// SetEnd changes when a class ends.
func (s *Store) SetEnd(ctx context.Context, code string, ends int64) error {
	_, err := s.db.ExecContext(ctx, "UPDATE classes SET ends_at = ? WHERE code = ?", ends, NormaliseCode(code))
	return err
}

// DeleteClass deletes a class with its students, their work and its tasks.
func (s *Store) DeleteClass(ctx context.Context, code string) error {
	return s.tx(ctx, func(tx *sql.Tx) error {
		c := NormaliseCode(code)
		if err := releaseBoardsOf(ctx, tx, "class_code = ?", c); err != nil {
			return err
		}
		for _, q := range []string{
			"DELETE FROM work WHERE student_id IN (SELECT id FROM students WHERE class_code = ?)",
			"DELETE FROM students WHERE class_code = ?",
			"DELETE FROM tasks WHERE class_code = ?",
			"DELETE FROM classes WHERE code = ?",
		} {
			if _, err := tx.ExecContext(ctx, q, c); err != nil {
				return err
			}
		}
		return nil
	})
}

// RemoveStudent takes a student and their work off a class (the class must be the one given).
func (s *Store) RemoveStudent(ctx context.Context, code, id string) error {
	return s.tx(ctx, func(tx *sql.Tx) error {
		c := NormaliseCode(code)
		if err := releaseBoardsOf(ctx, tx, "id = ? AND class_code = ?", id, c); err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, "DELETE FROM work WHERE student_id = (SELECT id FROM students WHERE id = ? AND class_code = ?)", id, c); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, "DELETE FROM students WHERE id = ? AND class_code = ?", id, c)
		return err
	})
}

// Join adds a student to a class.
func (s *Store) Join(ctx context.Context, code string, names []string, school string, now time.Time) (string, error) {
	c := NormaliseCode(code)
	var n int
	if err := s.db.QueryRowContext(ctx, "SELECT count(*) FROM students WHERE class_code = ?", c).Scan(&n); err != nil {
		return "", err
	}
	if n >= MaxStudentsPerClass {
		return "", ErrClassFull
	}
	b, _ := json.Marshal(names)
	id := RandomID()
	_, err := s.db.ExecContext(ctx, "INSERT INTO students (id, class_code, names, school, joined_at, seen_at) VALUES (?, ?, ?, ?, ?, ?)", id, c, string(b), school, ms(now), ms(now))
	return id, err
}

// Member is the student (and their class) for an id, if the class is still running.
func (s *Store) Member(ctx context.Context, id string, now time.Time) (Member, error) {
	var m Member
	var names string
	err := s.db.QueryRowContext(ctx, `SELECT s.id, s.names, s.school, s.class_code, c.name, c.school, c.ends_at
	  FROM students s JOIN classes c ON c.code = s.class_code WHERE s.id = ? AND c.ends_at > ?`, id, ms(now)).
		Scan(&m.ID, &names, &m.School, &m.ClassCode, &m.ClassName, &m.ClassSchool, &m.EndsAt)
	if errors.Is(err, sql.ErrNoRows) {
		return m, ErrNotFound
	}
	if err != nil {
		return m, err
	}
	return m, json.Unmarshal([]byte(names), &m.Names)
}

// Seen notes that a student used the class just now.
func (s *Store) Seen(ctx context.Context, id string, now time.Time) error {
	_, err := s.db.ExecContext(ctx, "UPDATE students SET seen_at = ? WHERE id = ?", ms(now), id)
	return err
}

// DeleteStudent takes a student off their class with all their work (the student asked).
func (s *Store) DeleteStudent(ctx context.Context, id string) error {
	return s.tx(ctx, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, "UPDATE boards SET student_id = NULL WHERE student_id = ?", id); err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, "DELETE FROM work WHERE student_id = ?", id); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, "DELETE FROM students WHERE id = ?", id)
		return err
	})
}

// MyWork is all of one student's work.
func (s *Store) MyWork(ctx context.Context, id string) ([]Work, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT app, item, kind, body, updated_at FROM work WHERE student_id = ? ORDER BY app, item, kind", id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Work{}
	for rows.Next() {
		var w Work
		if err := rows.Scan(&w.App, &w.Item, &w.Kind, &w.Body, &w.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, w)
	}
	return out, rows.Err()
}

// SaveWork saves pieces of a student's work. Newer work wins: an old copy from another device never
// replaces newer work.
func (s *Store) SaveWork(ctx context.Context, id string, items []Work, now time.Time) error {
	return s.tx(ctx, func(tx *sql.Tx) error {
		var n int
		if err := tx.QueryRowContext(ctx, "SELECT count(*) FROM work WHERE student_id = ?", id).Scan(&n); err != nil {
			return err
		}
		if n+len(items) > MaxItemsPerStudent {
			// only new items count: replacing work already saved is always fine
			fresh := 0
			for _, it := range items {
				var have int
				tx.QueryRowContext(ctx, "SELECT count(*) FROM work WHERE student_id = ? AND app = ? AND item = ? AND kind = ?", id, it.App, it.Item, it.Kind).Scan(&have)
				if have == 0 {
					fresh++
				}
			}
			if n+fresh > MaxItemsPerStudent {
				return ErrTooMuchWork
			}
		}
		for _, it := range items {
			if _, err := tx.ExecContext(ctx, `INSERT INTO work (student_id, app, item, kind, body, updated_at) VALUES (?, ?, ?, ?, ?, ?)
			  ON CONFLICT (student_id, app, item, kind) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
			  WHERE excluded.updated_at >= work.updated_at`, id, it.App, it.Item, it.Kind, it.Body, it.UpdatedAt); err != nil {
				return err
			}
		}
		_, err := tx.ExecContext(ctx, "UPDATE students SET seen_at = ? WHERE id = ?", ms(now), id)
		return err
	})
}

// Tasks is the work set for a class, in the teacher's order.
func (s *Store) Tasks(ctx context.Context, code string) ([]Task, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT app, item, note, set_at FROM tasks WHERE class_code = ? ORDER BY position, set_at", NormaliseCode(code))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Task{}
	for rows.Next() {
		var t Task
		if err := rows.Scan(&t.App, &t.Item, &t.Note, &t.SetAt); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

// SetTasks replaces the work set for a class. A task that was already set keeps the time it was first set.
func (s *Store) SetTasks(ctx context.Context, code string, tasks []Task, now time.Time) error {
	if len(tasks) > MaxTasksPerClass {
		return ErrBadTask
	}
	c := NormaliseCode(code)
	return s.tx(ctx, func(tx *sql.Tx) error {
		old := map[string]int64{}
		rows, err := tx.QueryContext(ctx, "SELECT app, item, set_at FROM tasks WHERE class_code = ?", c)
		if err != nil {
			return err
		}
		for rows.Next() {
			var app, item string
			var at int64
			if err := rows.Scan(&app, &item, &at); err != nil {
				rows.Close()
				return err
			}
			old[app+"/"+item] = at
		}
		rows.Close()
		if _, err := tx.ExecContext(ctx, "DELETE FROM tasks WHERE class_code = ?", c); err != nil {
			return err
		}
		seen := map[string]bool{}
		for i, t := range tasks {
			k := t.App + "/" + t.Item
			if seen[k] {
				continue
			}
			seen[k] = true
			at, ok := old[k]
			if !ok {
				at = ms(now)
			}
			if _, err := tx.ExecContext(ctx, "INSERT INTO tasks (class_code, app, item, note, position, set_at) VALUES (?, ?, ?, ?, ?, ?)", c, t.App, t.Item, t.Note, i, at); err != nil {
				return err
			}
		}
		return nil
	})
}

// CleanUp deletes classes that have ended, with their students, work and tasks. It returns how many.
func (s *Store) CleanUp(ctx context.Context, now time.Time) (int, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT code FROM classes WHERE ends_at <= ?", ms(now))
	if err != nil {
		return 0, err
	}
	var ended []string
	for rows.Next() {
		var c string
		if err := rows.Scan(&c); err != nil {
			rows.Close()
			return 0, err
		}
		ended = append(ended, c)
	}
	rows.Close()
	for _, c := range ended {
		if err := s.DeleteClass(ctx, c); err != nil {
			return 0, err
		}
	}
	return len(ended), nil
}

// Wipe deletes every class, student, piece of work and task (the end of a program).
func (s *Store) Wipe(ctx context.Context) error {
	return s.tx(ctx, func(tx *sql.Tx) error {
		for _, q := range []string{"UPDATE boards SET student_id = NULL", "DELETE FROM work", "DELETE FROM students", "DELETE FROM tasks", "DELETE FROM classes"} {
			if _, err := tx.ExecContext(ctx, q); err != nil {
				return err
			}
		}
		return nil
	})
}

// Compact rewrites the file so deleted work can't be read back from it.
func (s *Store) Compact(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, "VACUUM")
	if err == nil {
		_, err = s.db.ExecContext(ctx, "PRAGMA wal_checkpoint(TRUNCATE)")
	}
	return err
}

// Backup writes a copy of the whole database to a new file (for the teacher's own backups).
func (s *Store) Backup(ctx context.Context, path string) error {
	_, err := s.db.ExecContext(ctx, "VACUUM INTO ?", path)
	return err
}

// Counts are totals for the server's status page (no names).
type Counts struct {
	Classes  int `json:"classes"`
	Students int `json:"students"`
	Work     int `json:"work"`
}

// Totals counts what is kept.
func (s *Store) Totals(ctx context.Context) (Counts, error) {
	var c Counts
	err := s.db.QueryRowContext(ctx, "SELECT (SELECT count(*) FROM classes), (SELECT count(*) FROM students), (SELECT count(*) FROM work)").Scan(&c.Classes, &c.Students, &c.Work)
	return c, err
}

func (s *Store) tx(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		tx.Rollback()
		return err
	}
	return tx.Commit()
}

// TaskNoteOK says whether a teacher's note on a task is short enough.
func TaskNoteOK(s string) bool {
	return len([]rune(s)) <= maxTaskNoteCharacters && !strings.ContainsAny(s, "<>\x00")
}

// joinJSONNames turns a JSON list of first names into "Mia and Sam".
func joinJSONNames(raw string) string {
	var names []string
	if json.Unmarshal([]byte(raw), &names) != nil || len(names) == 0 {
		return ""
	}
	if len(names) == 1 {
		return names[0]
	}
	return strings.Join(names[:len(names)-1], ", ") + " and " + names[len(names)-1]
}
