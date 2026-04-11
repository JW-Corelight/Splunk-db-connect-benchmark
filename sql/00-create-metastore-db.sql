-- Create metastore database for Hive Metastore
-- Must run before hive-metastore schemaInit
SELECT 'CREATE DATABASE metastore'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metastore')\gexec
