#!/bin/bash
set -e

echo "Creating databases: bank_auth, bank_accounts, bank_transactions"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE bank_auth;
    CREATE DATABASE bank_accounts;
    CREATE DATABASE bank_transactions;
EOSQL

echo "Databases created successfully."