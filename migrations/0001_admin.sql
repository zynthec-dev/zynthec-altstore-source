CREATE TABLE IF NOT EXISTS admin_config (
  id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT NOT NULL,
  password_hash TEXT NOT NULL, revision INTEGER NOT NULL, github_token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
  hash TEXT PRIMARY KEY, revision INTEGER NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_attempts (
  key TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY(key,window)
);
