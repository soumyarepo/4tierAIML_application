# Four-Tier Microservice AI Banking Application Plan

## Overview
Production-grade four-tier microservice banking app with AI-powered fraud detection, deployed via GitHub Actions to Kubernetes with Helm.

## Architecture

### Tier 1: Edge Layer – API Gateway
- **Service**: `gateway-service`
- **Tech**: FastAPI + httpx
- **Features**:
  - JWT signature validation
  - Request ID generation and propagation
  - Rate limiting via Redis
  - Route proxying to upstream services
  - Header forwarding (`X-User-ID`, `X-User-Email`, `X-User-Roles`)
  - Standardized error response format
- **Port**: 8000 (external)

### Tier 2: Business Layer – Core Banking Services

#### Auth Service
- **Service**: `auth-service`
- **Port**: 8001
- **DB**: PostgreSQL `bank_auth`
- **Features**:
  - Registration, login, refresh token
  - Role-based access control (customer, admin, agent)
  - bcrypt password hashing
  - JWT (HS256) access + refresh tokens
  - Admin user listing
- **Models**: User, RefreshToken

#### Account Service
- **Service**: `account-service`
- **Port**: 8002
- **DB**: PostgreSQL `bank_accounts`
- **Features**:
  - CRUD for checking/savings/loan accounts
  - Balance as `DECIMAL` (no floats in banking)
  - Account status (active, frozen, closed)
  - Currency handling
  - Ownership verification via gateway headers
- **Models**: Account

#### Transaction Service
- **Service**: `transaction-service`
- **Port**: 8003
- **DB**: PostgreSQL `bank_transactions`
- **Features**:
  - Transfers, deposits, withdrawals
  - Idempotency keys for safety
  - Double-entry bookkeeping (Transaction + TransactionEntry)
  - Saga-like flow: pending → completed/failed
  - Sufficient balance validation with row locking
  - Kafka event publishing (`transaction.created`, `transaction.completed`)
  - Audit logging to MongoDB
  - Fraud-service integration for high-value transactions
- **Models**: Transaction, TransactionEntry

### Tier 3: AI/ML Layer – Intelligence Services

#### Fraud Detection Service
- **Service**: `fraud-service`
- **Port**: 8004
- **Features**:
  - ML model (IsolationForest) trained on synthetic transaction data
  - Feature extraction: amount, transaction type, merchant risk, hour/weekday
  - Model training on startup with synthetic data
  - `POST /api/v1/fraud/analyze` prediction endpoint
  - Risk score 0–100
  - Model metrics (Prometheus)

### Tier 4: Data/Infrastructure Layer

#### Redis
- Caching, sessions, rate limiting, idempotency keys

#### PostgreSQL
- Service Name: `bank-postgres`
- Three logical databases: `bank_auth`, `bank_accounts`, `bank_transactions`

#### Kafka
- Event streaming between transaction and fraud/notification services
- Topics: `transaction.created`, `transaction.completed`, `transaction.flagged`

#### MongoDB
- Audit logs from transaction service

#### Prometheus + Grafana (monitoring)
- Standard metrics and dashboards

### Tier 2b: Event-Driven Service

#### Notification Service
- **Service**: `notification-service`
- **Port**: 8005
- Kafka consumer for notification events
- Simulated email/SMS (logs to structured logger)

## Tech Stack
- Python 3.11
- FastAPI (async), Pydantic v2, SQLAlchemy 2.0 (async)
- asyncpg, aioredis, aiokafka, motor
- httpx, bcrypt, PyJWT, structlog, prometheus-client
- scikit-learn, numpy, joblib
- Docker, docker-compose
- Helm 3, Kubernetes (nginx-ingress)
- GitHub Actions CI/CD

## Chunking Plan

### Chunk 1: Shared Library + Infrastructure
- `shared/` package: config, database, middleware, metrics, exceptions, auth, logging, kafka helpers
- `docker-compose.yml`: PostgreSQL, Redis, Kafka, Zookeeper, MongoDB, Prometheus
- Files: 4-6 Python modules + docker-compose

### Chunk 2: Tier 1 (Gateway Service)
- `services/gateway/`: Dockerfile, app/main.py with proxy + rate limiting + JWT validation
- Files: main.py, Dockerfile, requirements.txt

### Chunk 3: Tier 2 Part A (Auth Service)
- `services/auth-service/`: Full auth with register, login, refresh, RBAC, admin
- Files: main.py, models.py, schemas.py, dependencies.py, Dockerfile, requirements.txt

### Chunk 4: Tier 2 Part B (Account + Transaction Services)
- `services/account-service/`: CRUD, balances
- `services/transaction-service/`: Saga, idempotency, Kafka, MongoDB audit, double-entry
- Files: 8-10 Python files + Dockerfiles

### Chunk 5: Tier 3 + Tier 2 Notification (AI + Event Consumer)
- `services/fraud-service/`: Synthetic data generation, model training, inference API
- `services/notification-service/`: Kafka consumer, simulated notifications
- Files: fraud model training, inference, notification consumer

### Chunk 6: Kubernetes + Helm + CI/CD
- `.github/workflows/ci-cd.yml`: Multi-service build/push + Helm deploy
- `helm/banking-app/`: Chart, values, templates
- Files: values.yaml, templates/, CI/CD YAML

## Acceptance Criteria
1. `docker-compose up` starts all services and infrastructure
2. Gateway routes requests correctly with auth proxy
3. Auth service generates valid JWT tokens
4. Account service manages accounts and balances safely
5. Transaction service processes transfers with double-entry bookkeeping
6. Fraud service scores transactions and trains a model
7. Kafka events flow between transaction and notification services
8. GitHub Actions builds all Docker images on push
9. Helm chart templates valid Kubernetes manifests

## Build Order Dependencies
Chunk 1 → Chunks 2, 3 (parallel) → Chunk 4 → Chunk 5 → Chunk 6
