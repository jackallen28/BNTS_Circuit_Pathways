-- Circuit Pathways classes. The only things about a student kept here are their first name(s) and
-- school, and their work (code and progress) for the class. Everything is deleted when the class ends.
CREATE TABLE classes (
  code       TEXT PRIMARY KEY,          -- ABCDEFGHJK (shown as ABCDE-FGHJK)
  teacher    TEXT NOT NULL,             -- a one-way fingerprint of the teacher's code, never the code
  name       TEXT NOT NULL,             -- the teacher's label, e.g. "7B Thursday"
  school     TEXT NOT NULL,
  created_at INTEGER NOT NULL,          -- ms since 1970
  ends_at    INTEGER NOT NULL           -- after this the class and everything in it is deleted
);
CREATE INDEX classes_teacher ON classes(teacher);
CREATE INDEX classes_ends ON classes(ends_at);

CREATE TABLE students (
  id         TEXT PRIMARY KEY,          -- random
  class_code TEXT NOT NULL REFERENCES classes(code) ON DELETE CASCADE,
  names      TEXT NOT NULL,             -- JSON array of 1-4 first names
  school     TEXT NOT NULL,
  joined_at  INTEGER NOT NULL,
  seen_at    INTEGER NOT NULL
);
CREATE INDEX students_class ON students(class_code);

CREATE TABLE work (
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  app        TEXT NOT NULL,             -- arduinopath | pipath
  item       TEXT NOT NULL,             -- a project or activity id
  kind       TEXT NOT NULL,             -- sketch | progress | settings
  body       TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (student_id, app, item, kind)
);
