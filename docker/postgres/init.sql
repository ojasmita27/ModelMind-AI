-- Runs ONCE, when the Postgres data volume is first created.
-- The main application database is created by POSTGRES_DB.
CREATE DATABASE modelmind_test;
CREATE DATABASE mlflow;  -- used from milestone M7 onward
