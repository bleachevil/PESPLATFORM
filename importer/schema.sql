CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pid TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  position TEXT NOT NULL DEFAULT 'CF',
  card_type TEXT NOT NULL DEFAULT 'Standard',
  mode TEXT NOT NULL DEFAULT 'dream-team',
  pack_name TEXT,
  pack_date TEXT,
  squad_number INTEGER,
  team_slug TEXT,
  image TEXT,
  overall INTEGER,
  max_overall INTEGER,
  level INTEGER DEFAULT 1,
  max_level INTEGER,
  height INTEGER,
  weight INTEGER,
  age INTEGER,
  foot TEXT,
  weak_foot_usage TEXT,
  weak_foot_accuracy TEXT,
  form TEXT,
  injury_resistance TEXT,
  nationality TEXT,
  region TEXT,
  club TEXT,
  league TEXT,
  source_url TEXT,
  att_style TEXT,
  def_style TEXT,
  skills TEXT,
  ai_styles TEXT,
  offensive_awareness INTEGER,
  ball_control INTEGER,
  dribbling INTEGER,
  tight_possession INTEGER,
  low_pass INTEGER,
  lofted_pass INTEGER,
  finishing INTEGER,
  heading INTEGER,
  set_piece_taking INTEGER,
  curl INTEGER,
  defensive_awareness INTEGER,
  tackling INTEGER,
  aggression INTEGER,
  defensive_engagement INTEGER,
  gk_awareness INTEGER,
  gk_catching INTEGER,
  gk_parrying INTEGER,
  gk_reflexes INTEGER,
  gk_reach INTEGER,
  speed INTEGER,
  acceleration INTEGER,
  kicking_power INTEGER,
  jumping INTEGER,
  physical_contact INTEGER,
  balance INTEGER,
  stamina INTEGER
);

CREATE INDEX IF NOT EXISTS idx_players_name ON players(name);
CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
CREATE INDEX IF NOT EXISTS idx_players_overall ON players(overall);
CREATE INDEX IF NOT EXISTS idx_players_slug ON players(slug);

CREATE TABLE IF NOT EXISTS teams (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  league TEXT,
  region TEXT
);

CREATE TABLE IF NOT EXISTS packs (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  released_on TEXT,
  kind TEXT DEFAULT 'Special Player List'
);

CREATE TABLE IF NOT EXISTS pack_players (
  pack_slug TEXT NOT NULL,
  player_pid TEXT NOT NULL,
  PRIMARY KEY (pack_slug, player_pid)
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
