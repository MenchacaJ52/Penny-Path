-- One-time PostgreSQL setup for PennyPath. Run as the postgres superuser:
--
--   psql -U postgres -f scripts/setup_postgres.sql
--
-- Creates a dedicated login role `pennypath` and two databases it owns:
-- `pennypath` for the app and `pennypath_test` for the test suite. psql then
-- asks you to set the role's password (typing is hidden, and it is sent to the
-- server already encrypted). Tables are created by the app itself.
-- Safe to re-run: existing objects are kept, and the password is updated.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE pennypath LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pennypath') \gexec

SELECT 'CREATE DATABASE pennypath OWNER pennypath'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pennypath') \gexec
SELECT 'CREATE DATABASE pennypath_test OWNER pennypath'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pennypath_test') \gexec

\echo
\echo 'Choose a password for the "pennypath" database user (your typing is hidden):'
\password pennypath

\echo
\echo 'Done. Now set DATABASE_URL (replace <password> with the one you just chose):'
\echo '  postgresql://pennypath:<password>@localhost:5432/pennypath'
