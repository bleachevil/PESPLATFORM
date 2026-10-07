CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL DEFAULT '',
  google_sub TEXT UNIQUE,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leagues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  organizer_id INTEGER,
  start_on TEXT,
  end_on TEXT,
  timezone TEXT DEFAULT 'America/New_York',
  max_teams INTEGER DEFAULT 16,
  weeks INTEGER DEFAULT 6,
  starting_budget INTEGER DEFAULT 1000,
  status TEXT DEFAULT 'open',
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS league_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  starts_at TEXT NOT NULL,
  ends_at TEXT NOT NULL,
  max_releases INTEGER DEFAULT 0,
  max_signings INTEGER DEFAULT 0,
  max_transfers INTEGER DEFAULT 0,
  max_loans INTEGER DEFAULT 0,
  refund_pct INTEGER DEFAULT 50,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manager_teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  budget INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (league_id, user_id)
);

CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  team_id INTEGER NOT NULL,
  player_pid TEXT NOT NULL,
  fee INTEGER NOT NULL,
  release_clause INTEGER,
  kind TEXT NOT NULL DEFAULT 'signed',
  status TEXT NOT NULL DEFAULT 'active',
  signed_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_held
  ON contracts(league_id, player_pid)
  WHERE status IN ('active', 'sea');

CREATE TABLE IF NOT EXISTS sea_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  player_pid TEXT NOT NULL,
  from_team_id INTEGER,
  price INTEGER NOT NULL,
  listed_at TEXT NOT NULL,
  UNIQUE (league_id, player_pid)
);

CREATE TABLE IF NOT EXISTS transfer_offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  player_pid TEXT NOT NULL,
  from_team_id INTEGER NOT NULL,
  to_team_id INTEGER NOT NULL,
  fee INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'transfer',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS window_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  window_id INTEGER NOT NULL,
  team_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS league_officers (
  league_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL DEFAULT 'officer',
  granted_at TEXT NOT NULL,
  PRIMARY KEY (league_id, user_id)
);

CREATE TABLE IF NOT EXISTS join_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  team_name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'request',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by INTEGER
);

CREATE TABLE IF NOT EXISTS competitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id INTEGER NOT NULL,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  level INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL,
  UNIQUE (league_id, slug)
);

CREATE TABLE IF NOT EXISTS competition_teams (
  competition_id INTEGER NOT NULL,
  team_id INTEGER NOT NULL,
  PRIMARY KEY (competition_id, team_id)
);

CREATE TABLE IF NOT EXISTS fixtures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  competition_id INTEGER NOT NULL,
  home_team_id INTEGER NOT NULL,
  away_team_id INTEGER NOT NULL,
  kickoff TEXT,
  week_no INTEGER,
  home_goals INTEGER,
  away_goals INTEGER,
  status TEXT NOT NULL DEFAULT 'scheduled',
  recorded_by INTEGER,
  recorded_at TEXT
);
