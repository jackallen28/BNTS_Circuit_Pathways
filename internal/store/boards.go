package store

import (
	"context"
	"crypto/rand"
	"database/sql"
	"errors"
	"strings"
	"time"
)

// The school's ESP boards. A teacher sets each one up once (the teacher portal flashes it): it gets a label
// ("ESP-07"), its own WiFi name and password, and a code for its sticker. A student in one of that teacher's
// classes claims it with the code; ArduinoPath then puts that board's WiFi name and password in the student's
// code, and only uploads to that board (it checks the chip's own MAC address), so nobody else can use it or
// join its WiFi. Boards belong to the teacher and outlast classes: when a student leaves, their board is free.

const boardsSchema = `
CREATE TABLE IF NOT EXISTS boards (
  id         TEXT PRIMARY KEY,          -- random
  teacher    TEXT NOT NULL,             -- the teacher who set it up (a fingerprint of their code)
  label      TEXT NOT NULL,             -- e.g. ESP-07, written on the board
  kind       TEXT NOT NULL,             -- the board type: nodemcu, esp32...
  mac        TEXT NOT NULL DEFAULT '',  -- the chip's MAC address, read when it was flashed
  ssid       TEXT NOT NULL,             -- its own WiFi name
  password   TEXT NOT NULL,             -- its own WiFi password
  code       TEXT NOT NULL UNIQUE,      -- what a student types to claim it (on its sticker)
  student_id TEXT,                      -- who has it now (NULL: free)
  created_at INTEGER NOT NULL,
  flashed_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS boards_teacher ON boards(teacher);
CREATE UNIQUE INDEX IF NOT EXISTS boards_student ON boards(student_id) WHERE student_id IS NOT NULL;
`

// MaxBoardsPerTeacher is how many boards one teacher can set up.
const MaxBoardsPerTeacher = 200

// Board is one ESP board.
type Board struct {
	ID        string `json:"id"`
	Label     string `json:"label"`
	Kind      string `json:"kind"`
	MAC       string `json:"mac"`
	SSID      string `json:"ssid"`
	Password  string `json:"password"`
	Code      string `json:"code"`
	Student   string `json:"student,omitempty"` // the student's first names, for the teacher
	StudentID string `json:"-"`
	CreatedAt int64  `json:"created_at"`
	FlashedAt int64  `json:"flashed_at"`
}

// Errors about boards.
var (
	ErrBoardTaken = errors.New("board taken")
	ErrSameLabel  = errors.New("same label")
)

const (
	codeAlphabet = "23456789ABCDEFGHJKMNPQRSTVWXYZ" // no 0/O, 1/I/L: it is read off a sticker
	wifiAlphabet = "abcdefghjkmnpqrstuvwxyz23456789"
)

func randomFrom(alpha string, n int) string {
	b := make([]byte, n)
	rand.Read(b)
	for i := range b {
		b[i] = alpha[int(b[i])%len(alpha)]
	}
	return string(b)
}

// NormaliseBoardCode tidies a typed board code: upper case, no spaces or dashes, look-alikes fixed.
func NormaliseBoardCode(s string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(s) {
		switch r {
		case ' ', '-', '_', '\t':
			continue
		case 'O':
			r = '0'
		case 'I', 'L':
			r = '1'
		}
		b.WriteRune(r)
	}
	return b.String()
}

// ShowBoardCode is a code as it is printed: K7M2-QX9P.
func ShowBoardCode(c string) string {
	if len(c) == 8 {
		return c[:4] + "-" + c[4:]
	}
	return c
}

// NewBoard sets up a board for a teacher, with its own WiFi name, password and code.
func (s *Store) NewBoard(ctx context.Context, teacher, label, kind string, now time.Time) (Board, error) {
	var n int
	if err := s.db.QueryRowContext(ctx, "SELECT count(*) FROM boards WHERE teacher = ?", teacher).Scan(&n); err != nil {
		return Board{}, err
	}
	if n >= MaxBoardsPerTeacher {
		return Board{}, ErrTooMany
	}
	var same int
	s.db.QueryRowContext(ctx, "SELECT count(*) FROM boards WHERE teacher = ? AND lower(label) = lower(?)", teacher, label).Scan(&same)
	if same > 0 {
		return Board{}, ErrSameLabel
	}
	tag := strings.ToUpper(randomFrom(codeAlphabet, 4))
	b := Board{
		ID: RandomID(), Label: label, Kind: kind,
		// a WiFi name students recognise, and that is different for every board
		SSID:      "CP-" + wifiSafe(label) + "-" + tag,
		Password:  randomFrom(wifiAlphabet, 10),
		CreatedAt: now.UnixMilli(),
	}
	for i := 0; i < 5; i++ {
		b.Code = randomFrom(codeAlphabet, 8)
		res, err := s.db.ExecContext(ctx, `INSERT OR IGNORE INTO boards (id, teacher, label, kind, ssid, password, code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			b.ID, teacher, b.Label, b.Kind, b.SSID, b.Password, b.Code, b.CreatedAt)
		if err != nil {
			return Board{}, err
		}
		if c, _ := res.RowsAffected(); c == 1 {
			b.Code = ShowBoardCode(b.Code)
			return b, nil
		}
	}
	return Board{}, ErrCodeCollision
}

// wifiSafe keeps the letters and digits of a label, for the WiFi name.
func wifiSafe(label string) string {
	var b strings.Builder
	for _, r := range label {
		if (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		}
		if b.Len() >= 12 {
			break
		}
	}
	if b.Len() == 0 {
		return "ESP"
	}
	return b.String()
}

const boardCols = `b.id, b.label, b.kind, b.mac, b.ssid, b.password, b.code, coalesce(b.student_id, ''), b.created_at, b.flashed_at,
  coalesce((SELECT s.names FROM students s WHERE s.id = b.student_id), '')`

func scanBoard(row interface{ Scan(...any) error }) (Board, error) {
	var b Board
	var names string
	err := row.Scan(&b.ID, &b.Label, &b.Kind, &b.MAC, &b.SSID, &b.Password, &b.Code, &b.StudentID, &b.CreatedAt, &b.FlashedAt, &names)
	if errors.Is(err, sql.ErrNoRows) {
		return b, ErrNotFound
	}
	b.Code = ShowBoardCode(b.Code)
	if names != "" {
		b.Student = joinJSONNames(names)
	}
	return b, err
}

// TeacherBoards are a teacher's boards, in label order, with who has each one.
func (s *Store) TeacherBoards(ctx context.Context, teacher string) ([]Board, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT "+boardCols+" FROM boards b WHERE b.teacher = ? ORDER BY b.label COLLATE NOCASE, b.created_at", teacher)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Board{}
	for rows.Next() {
		b, err := scanBoard(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, b)
	}
	return out, rows.Err()
}

// TeacherBoard is one of the teacher's boards.
func (s *Store) TeacherBoard(ctx context.Context, teacher, id string) (Board, error) {
	return scanBoard(s.db.QueryRowContext(ctx, "SELECT "+boardCols+" FROM boards b WHERE b.id = ? AND b.teacher = ?", id, teacher))
}

// BoardFlashed records the chip's MAC address once the teacher portal has flashed the board.
func (s *Store) BoardFlashed(ctx context.Context, teacher, id, mac string, now time.Time) error {
	res, err := s.db.ExecContext(ctx, "UPDATE boards SET mac = ?, flashed_at = ? WHERE id = ? AND teacher = ?", mac, now.UnixMilli(), id, teacher)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrNotFound
	}
	return nil
}

// ReleaseBoard frees a board (its student no longer has it).
func (s *Store) ReleaseBoard(ctx context.Context, teacher, id string) error {
	_, err := s.db.ExecContext(ctx, "UPDATE boards SET student_id = NULL WHERE id = ? AND teacher = ?", id, teacher)
	return err
}

// DeleteBoard forgets a board.
func (s *Store) DeleteBoard(ctx context.Context, teacher, id string) error {
	_, err := s.db.ExecContext(ctx, "DELETE FROM boards WHERE id = ? AND teacher = ?", id, teacher)
	return err
}

// ClaimBoard gives a board to a student: the board must belong to their class's teacher and be free (or theirs).
// A student has one board: claiming another gives back the one they had.
func (s *Store) ClaimBoard(ctx context.Context, studentID, classCode, code string) (Board, error) {
	var teacher string
	if err := s.db.QueryRowContext(ctx, "SELECT teacher FROM classes WHERE code = ?", NormaliseCode(classCode)).Scan(&teacher); err != nil {
		return Board{}, ErrNotFound
	}
	c := NormaliseBoardCode(code)
	var id string
	var holder sql.NullString
	err := s.db.QueryRowContext(ctx, "SELECT id, student_id FROM boards WHERE code = ? AND teacher = ?", c, teacher).Scan(&id, &holder)
	if errors.Is(err, sql.ErrNoRows) {
		return Board{}, ErrNotFound
	}
	if err != nil {
		return Board{}, err
	}
	if holder.Valid && holder.String != studentID {
		return Board{}, ErrBoardTaken
	}
	err = s.tx(ctx, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, "UPDATE boards SET student_id = NULL WHERE student_id = ?", studentID); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, "UPDATE boards SET student_id = ? WHERE id = ?", studentID, id)
		return err
	})
	if err != nil {
		return Board{}, err
	}
	return s.StudentBoard(ctx, studentID)
}

// StudentBoard is the board a student has (ErrNotFound: none).
func (s *Store) StudentBoard(ctx context.Context, studentID string) (Board, error) {
	return scanBoard(s.db.QueryRowContext(ctx, "SELECT "+boardCols+" FROM boards b WHERE b.student_id = ?", studentID))
}

// GiveBackBoard frees the student's board.
func (s *Store) GiveBackBoard(ctx context.Context, studentID string) error {
	_, err := s.db.ExecContext(ctx, "UPDATE boards SET student_id = NULL WHERE student_id = ?", studentID)
	return err
}

// releaseBoardsOf frees the boards of students who are about to be deleted (inside a transaction).
func releaseBoardsOf(ctx context.Context, tx *sql.Tx, where string, args ...any) error {
	_, err := tx.ExecContext(ctx, "UPDATE boards SET student_id = NULL WHERE student_id IN (SELECT id FROM students WHERE "+where+")", args...)
	return err
}
