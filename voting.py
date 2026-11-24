"""Election storage and rules. SQLite locally, PostgreSQL for hosted use."""
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

N = 13

class ElectionError(Exception):
    pass


def digest(code):
    return hashlib.sha256(code.strip().encode('utf-8')).hexdigest()


def make_code():
    return secrets.token_urlsafe(24)


def tally(member_ids, ballots, priority):
    """Return complete Borda ranking. Ballots map voter ID to ordered candidate IDs."""
    member_ids = list(member_ids)
    ids = set(member_ids)
    if len(member_ids) != N or len(ids) != N or len(priority) != N or set(priority) != ids:
        raise ElectionError('Invalid election roster or tie priority.')
    if set(ballots) != ids:
        raise ElectionError('Final ranking requires all 13 ballots.')
    counts = {i: [0] * (N - 1) for i in member_ids}
    for voter, ranking in ballots.items():
        if len(ranking) != N - 1 or set(ranking) != ids - {voter}:
            raise ElectionError('Invalid ballot in storage.')
        for j, candidate in enumerate(ranking):
            counts[candidate][j] += 1
    points = {i: sum((N - 1 - j) * n for j, n in enumerate(counts[i])) for i in ids}
    order = {i: j for j, i in enumerate(priority)}
    ordered = sorted(member_ids, key=lambda i: (-points[i], *(-v for v in counts[i]), order[i]))
    return [{'position': k + 1, 'id': i, 'points': points[i], 'counts': counts[i],
             'priority': order[i] + 1} for k, i in enumerate(ordered)]


class Store:
    def __init__(self, url=''):
        self.url = url
        self.pg = bool(url)
        self.path = Path(__file__).resolve().parent / 'private_election.sqlite3'

    @contextmanager
    def db(self, write=False, setup=False):
        if self.pg:
            import psycopg
            conn = psycopg.connect(self.url, connect_timeout=10)
        else:
            conn = sqlite3.connect(self.path, timeout=15)
        try:
            if self.pg:
                if setup:
                    conn.execute('SELECT pg_advisory_xact_lock(713130031)')
                    conn.execute('CREATE SCHEMA IF NOT EXISTS community_vote')
                    conn.execute('REVOKE ALL ON SCHEMA community_vote FROM PUBLIC')
                conn.execute('SET LOCAL search_path TO community_vote')
            else:
                conn.execute('PRAGMA foreign_keys = ON')
                conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sql(self, conn, query, args=()):
        return conn.execute(query.replace('?', '%s') if self.pg else query, args)

    def initialized(self):
        with self.db() as c:
            if self.pg:
                exists = c.execute("SELECT to_regclass('community_vote.election_state')").fetchone()[0]
            else:
                exists = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='election_state'").fetchone()
            return bool(exists and self.sql(c, 'SELECT id FROM election_state WHERE id=1').fetchone())

    def setup(self, names, admins, voter_codes, admin_codes):
        names = [n.strip() for n in names]
        admins = [n.strip() for n in admins]
        if len(names) != N or len({n.casefold() for n in names}) != N or not all(names):
            raise ElectionError('Provide exactly 13 distinct, nonempty member names.')
        if len(admins) != 3 or len({n.casefold() for n in admins}) != 3 or not all(admins):
            raise ElectionError('Provide exactly 3 distinct, nonempty administrator names.')
        all_codes = voter_codes + admin_codes
        if len(voter_codes) != N or len(admin_codes) != 3 or len(set(all_codes)) != N + 3:
            raise ElectionError('Invalid access codes.')
        priority = list(range(1, N + 1))
        secrets.SystemRandom().shuffle(priority)
        with self.db(write=True, setup=True) as c:
            self.sql(c, 'CREATE TABLE IF NOT EXISTS election_state (id INTEGER PRIMARY KEY, priority TEXT NOT NULL)')
            self.sql(c, 'CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, code_hash TEXT NOT NULL UNIQUE)')
            self.sql(c, 'CREATE TABLE IF NOT EXISTS administrators (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, code_hash TEXT NOT NULL UNIQUE)')
            self.sql(c, 'CREATE TABLE IF NOT EXISTS ballots (voter_id INTEGER PRIMARY KEY REFERENCES members(id), ranking TEXT NOT NULL)')
            if self.sql(c, 'SELECT id FROM election_state WHERE id=1').fetchone():
                raise ElectionError('Election already initialized. No reset or overwrite allowed.')
            self.sql(c, 'INSERT INTO election_state VALUES (1,?)', (json.dumps(priority),))
            for i, (name, code) in enumerate(zip(names, voter_codes), 1):
                self.sql(c, 'INSERT INTO members VALUES (?,?,?)', (i, name, digest(code)))
            for i, (name, code) in enumerate(zip(admins, admin_codes), 1):
                self.sql(c, 'INSERT INTO administrators VALUES (?,?,?)', (i, name, digest(code)))
        return [names[i - 1] for i in priority]

    def _auth(self, c, role, code):
        if role not in ('member', 'admin') or not isinstance(code, str) or not code.strip() or len(code) > 256:
            raise ElectionError('Invalid access code.')
        table = 'members' if role == 'member' else 'administrators'
        row = self.sql(c, f'SELECT id,name FROM {table} WHERE code_hash=?', (digest(code),)).fetchone()
        if row is None:
            raise ElectionError('Invalid access code.')
        return row

    def login(self, role, code):
        with self.db() as c:
            return self._auth(c, role, code)

    def _roster(self, c):
        return dict(self.sql(c, 'SELECT id,name FROM members ORDER BY id').fetchall())

    def _priority(self, c):
        return json.loads(self.sql(c, 'SELECT priority FROM election_state WHERE id=1').fetchone()[0])

    def overview(self, role, code):
        with self.db() as c:
            user_id, name = self._auth(c, role, code)
            roster = self._roster(c)
            count = self.sql(c, 'SELECT COUNT(*) FROM ballots').fetchone()[0]
            submitted = role == 'member' and self.sql(c, 'SELECT 1 FROM ballots WHERE voter_id=?', (user_id,)).fetchone() is not None
            return {'id': user_id, 'name': name, 'roster': roster, 'count': count, 'submitted': submitted,
                    'priority': [roster[i] for i in self._priority(c)]}

    def submit(self, code, ranking):
        with self.db(write=True) as c:
            voter, _ = self._auth(c, 'member', code)
            # Serialize submissions (also prevents race conditions at finalization).
            self.sql(c, 'UPDATE election_state SET priority=priority WHERE id=1')
            if self.sql(c, 'SELECT 1 FROM ballots WHERE voter_id=?', (voter,)).fetchone():
                raise ElectionError('You have already submitted your ballot.')
            ids = set(self._roster(c))
            if len(ranking) != N - 1 or set(ranking) != ids - {voter}:
                raise ElectionError('Rank every other member exactly once; no self-voting.')
            self.sql(c, 'INSERT INTO ballots VALUES (?,?)', (voter, json.dumps(ranking)))

    def results(self, role, code):
        with self.db() as c:
            self._auth(c, role, code)
            roster = self._roster(c)
            # No identity-linked or aggregate interim results are returned.
            if self.sql(c, 'SELECT COUNT(*) FROM ballots').fetchone()[0] != N:
                raise ElectionError('Results are locked until all 13 members have voted.')
            ballots = {i: json.loads(r) for i, r in self.sql(c, 'SELECT voter_id,ranking FROM ballots').fetchall()}
            ranking = tally(roster, ballots, self._priority(c))
            return [dict(row, name=roster[row['id']]) for row in ranking]

    def audit(self, code):
        with self.db() as c:
            self._auth(c, 'admin', code)
            if self.sql(c, 'SELECT COUNT(*) FROM ballots').fetchone()[0] != N:
                raise ElectionError('Individual ballots are locked until all 13 members have voted.')
            roster = self._roster(c)
            ballots = self.sql(c, 'SELECT voter_id,ranking FROM ballots ORDER BY voter_id').fetchall()
            return [(roster[v], [roster[i] for i in json.loads(r)]) for v, r in ballots]
