"""Local workload ledger. Only confirmed result submission creates a count."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING = timezone(timedelta(hours=8))


class PendingEvaluation(ValueError):
    pass


class Store:
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS people(name TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS evaluations(
                    id TEXT PRIMARY KEY, robot TEXT NOT NULL, person TEXT NOT NULL,
                    created_at TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'recording', intent TEXT,
                    confirmed_at TEXT, beijing_date TEXT, discard_reason TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_robot
                    ON evaluations(robot) WHERE closed=0;
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY, evaluation_id TEXT NOT NULL,
                    kind TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL);
            ''')
            if 'discard_reason' not in {r[1] for r in db.execute('PRAGMA table_info(evaluations)')}:
                db.execute('ALTER TABLE evaluations ADD COLUMN discard_reason TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def now(self):
        return self.clock().astimezone(timezone.utc).isoformat()

    def people(self):
        with self.connect() as db:
            return [r[0] for r in db.execute('SELECT name FROM people ORDER BY name')]

    def add_person(self, name):
        name = str(name).strip()
        if not name:
            raise ValueError('Please select or enter your name')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO people VALUES(?)', (name,))
        return name

    def get(self, eid):
        with self.connect() as db:
            r = db.execute('SELECT * FROM evaluations WHERE id=?', (eid,)).fetchone()
            return dict(r) if r else None

    def pending(self, robot=None):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                'SELECT * FROM evaluations WHERE closed=0' + (' AND robot=?' if robot else ''),
                (robot,) if robot else ())]

    def register(self, eid, robot, person):
        person = self.add_person(person)
        try:
            with self.connect() as db:
                existing = db.execute('SELECT robot,person FROM evaluations WHERE id=?', (eid,)).fetchone()
                if existing:
                    if tuple(existing) != (robot, person):
                        raise ValueError('The evaluation owner is already recorded')
                    return
                db.execute('INSERT INTO evaluations(id,robot,person,created_at) VALUES(?,?,?,?)',
                           (eid, robot, person, self.now()))
        except sqlite3.IntegrityError as e:
            raise PendingEvaluation('Submit or discard the pending A/B evaluation first') from e

    def state(self, eid, state):
        with self.connect() as db:
            db.execute('UPDATE evaluations SET state=? WHERE id=? AND closed=0', (state, eid))

    def intent(self, eid, payload):
        value = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.connect() as db:
            row = db.execute('SELECT closed,intent FROM evaluations WHERE id=?', (eid,)).fetchone()
            if not row:  # historical records retain their existing flow, without workload import
                return
            if row['closed']:
                raise ValueError('This evaluation is already closed')
            db.execute("UPDATE evaluations SET intent=?,state='submitting' WHERE id=?", (value, eid))
            db.execute('INSERT INTO events(evaluation_id,kind,at,detail) VALUES(?,?,?,?)',
                       (eid, 'submission_intent', self.now(), value))

    def confirm(self, eid, payload, source='result_response'):
        """One transaction, unique evaluation ID; uploads cannot call this path."""
        now = self.clock().astimezone(timezone.utc)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM evaluations WHERE id=?', (eid,)).fetchone()
            if not row or row['confirmed_at']:
                return False
            if row['closed'] or not row['intent'] or json.loads(row['intent']) != payload:
                raise ValueError('Submission confirmation does not match the saved result')
            db.execute("UPDATE evaluations SET state='submitted',closed=1,confirmed_at=?,beijing_date=? WHERE id=?",
                       (now.isoformat(), now.astimezone(BEIJING).date().isoformat(), eid))
            db.execute('INSERT INTO events(evaluation_id,kind,at,detail) VALUES(?,?,?,?)',
                       (eid, 'submission_confirmed', now.isoformat(), source))
            return True

    def discard(self, eid):
        with self.connect() as db:
            db.execute("UPDATE evaluations SET closed=1,state='discarded' WHERE id=? AND confirmed_at IS NULL", (eid,))

    def discard_intent(self, eid, reason):
        if not reason.strip():
            raise ValueError('A reason is required to discard')
        with self.connect() as db:
            db.execute("UPDATE evaluations SET discard_reason=?,state='discarding' WHERE id=? AND closed=0", (reason, eid))

    def confirmed(self, date=None):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM evaluations WHERE confirmed_at IS NOT NULL' +
                (' AND beijing_date=?' if date else '') + ' ORDER BY confirmed_at DESC', (date,) if date else ())]

    def stats(self, date=None):
        with self.connect() as db:
            rows = db.execute('SELECT beijing_date AS date,person,robot,COUNT(*) AS count FROM evaluations '
                              'WHERE confirmed_at IS NOT NULL' + (' AND beijing_date=?' if date else '') +
                              ' GROUP BY beijing_date,person,robot ORDER BY beijing_date DESC,person,robot',
                              (date,) if date else ())
            return {'timezone': 'Asia/Shanghai', 'rows': [dict(r) for r in rows],
                    'people': self.people(), 'scope': 'local'}
