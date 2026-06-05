# Parket AI — Architecture Document

---

## Overview

Parket AI is a production-grade, four-tier microservice banking application that combines classic financial service patterns with AI-powered fraud detection. The system is designed for horizontal scalability, event-driven analytics, and secure multi-tenant operations.

---

## The Four Tiers

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1 — EDGE LAYER                      [Gateway :8000]       │
│  Request validation, routing, rate limiting, auth header mgmt   │
└────────────────────────────┬────────────────────────────────────┘
                             │ internal HTTP
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌──────────────────────┐
│ TIER 2 — CORE  BUSINESS SERVICES                        │
│                                                        │
│  Auth Service   Account Service   Transaction Service   │
│  :8001          :8002             :8003                │
│  bank_auth DB   bank_accounts DB  bank_transactions DB  │
└────────────────┴────────┬─────────┴──────────────────────┘
                          │ Kafka topics:
                          │   transaction.created
                          │   transaction.completed
                          ▼
┌──────────────────────────────────────────────────────────┐
│ TIER 3 — AI/ML LAYER              [Fraud Service :8004]  │
│  IsolationForest model, risk scoring 0–100               │
│  HTTP sync for high-value tx; Kafka for batch events     │
└────────────────────────────┬─────────────────────────────┘
                             │ Kafka: transaction.flagged
                             ▼
┌──────────────────────────────────────────────────────────┐
│ TIER 2b — EVENT-DRIVEN           [Notification :8005]   │
│  Kafka consumer, simulated email/SMS                     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ TIER 4 — DATA / INFRASTRUCTURE LAYER                     │
│  PostgreSQL  │  Redis  │  Kafka/ZK  │  MongoDB  │  PMM   │
└──────────────────────────────────────────────────────────┘
```

---

## Service Communication Patterns

### 1. Synchronous HTTP (gateway → upstream services)

```
Client → Gateway (JWT validated, rate limited)
         └─→ Auth Service        POST /api/v1/auth/login  → JWT token
         └─→ Account Service     GET  /api/v1/accounts    → account list
         └─→ Transaction Service POST /api/v1/transactions → transaction record
```

- Gateway validates JWT signature on every request
- Forwards `X-User-ID`, `X-User-Email`, `X-User-Roles` headers to upstream services
- Upstream services trust gateway-provided headers (not re-validating JWT)
- 5xx from upstream → gateway returns 502 with error detail
- Timeout: 30s per upstream

### 2. Synchronous HTTP (transaction → fraud for high-value)

```
Transaction Service → Fraud Service  POST /api/v1/fraud/analyze
                      (transactions > $5,000 only)
                      ← { risk_score: 73, recommendation: "block" }
```

### 3. Asynchronous Kafka events

```
Transaction Service publishes:
  topic: transaction.created  (on transaction initiation)
  topic: transaction.completed (on final commit)

Fraud Service subscribes:
  topic: transaction.created  (batch anomaly scoring)
  topic: transaction.flagged  (notification service reacts)

Notification Service subscribes:
  topic: transaction.completed
  topic: transaction.flagged  (alert customers)
```

---

## Data Flow Diagrams

### A. User Registration & Login

```
[Client]  POST /api/v1/auth/register
          Body: { email, password, roles }
               │
               ▼
          [Gateway]  (forwards, no JWT needed for register)
               │
               ▼
          [Auth Service]  bank_auth DB
               │  1. Hash password (bcrypt)
               │  2. Store User record
               │  3. Create refresh token
               └─→ Returns: { user_id, access_token, refresh_token }
```

### B. Transfer (double-entry bookkeeping)

```
[Client]  POST /api/v1/transactions/transfer
          Header: Authorization: Bearer <JWT>
          Body: { from_account, to_account, amount, idempotency_key }
               │
               ▼
          [Gateway] validates JWT, forwards to Transaction Service
               │
               ▼
          [Transaction Service]
               │
               ├─→ [Auth Service]  GET /api/v1/auth/users/{id}/roles (verify owner)
               │
               ├─→ [Account Service]  GET /api/v1/accounts/{id}/balance (row lock)
               │
               ├─→ [Fraud Service]  POST /api/v1/fraud/analyze
               │   (if amount > 5000)
               │
               ├─→ BEGIN TRANSACTION (double-entry)
               │   INSERT transaction (status=pending)
               │   INSERT transaction_entry (debit)
               │   INSERT transaction_entry (credit)
               │   UPDATE account SET balance (debit)
               │   UPDATE account SET balance (credit)
               │   UPDATE transaction SET status=completed
               └─→ COMMIT
               │
               ├─→ INSERT audit_log (MongoDB)
               │
               ├─→ PUBLISH transaction.created → Kafka
               │
               └─→ Returns: { transaction_id, status, entries }
```

### C. Fraud Service Model Training (startup)

```
[Fraud Service — on startup]
  │
  ├─→ Generate 10,000 synthetic transactions
  │   Features: amount, type, merchant_risk, hour, weekday
  │
  ├─→ Train IsolationForest(n_estimators=100, contamination=0.05)
  │
  ├─→ Persist model via joblib (in-memory, re-trained each startup)
  │
  └─→ Expose /api/v1/fraud/analyze  (synchronous, per-request scoring)
```

---

## Security Considerations

### Authentication & Authorization
- JWT (HS256) access tokens (15 min TTL) + refresh tokens (7 days)
- Tokens stored in Redis for fast validation and revocation
- RBAC roles: `customer`, `agent`, `admin`
- Gateway is the only JWT validation point; upstream services trust forwarded headers

### Secrets Management
- `jwt-secret`, `postgres-password`, `mongo-password`, `redis-password` stored in Kubernetes Secret `banking-secrets`
- In production, inject via external secrets manager (Vault, AWS Secrets Manager)
- Grafana password stored in `banking-secrets`

### Network Security
- NetworkPolicy restricts pods to intra-namespace communication only
- External access only via Ingress (gateway) or explicit NodePort/LoadBalancer
- No service exposes ports directly to the internet

### Container Security
- All containers run as non-root user (UID 1000)
- `readOnlyRootFilesystem: true` where possible
- All Linux capabilities dropped (`CAP_SYS_ADMIN`, etc.)
- `allowPrivilegeEscalation: false`

### Data at Rest
- PostgreSQL and MongoDB use PVC with storage encryption (cloud provider default)
- No secrets written to ConfigMaps

---

## Database Schema Overview

### bank_auth (PostgreSQL)
```
users
  id          UUID PK
  email       VARCHAR UNIQUE NOT NULL
  password    VARCHAR NOT NULL (bcrypt hash)
  roles       VARCHAR[] NOT NULL DEFAULT '{customer}'
  created_at  TIMESTAMP
  updated_at  TIMESTAMP

refresh_tokens
  id          UUID PK
  user_id     UUID FK → users.id
  token       VARCHAR UNIQUE NOT NULL
  expires_at  TIMESTAMP NOT NULL
  revoked     BOOLEAN DEFAULT false
```

### bank_accounts (PostgreSQL)
```
accounts
  id          UUID PK
  user_id     UUID NOT NULL (gateway-provided, not joined)
  account_type VARCHAR NOT NULL (checking/savings/loan)
  balance     DECIMAL(19,4) NOT NULL DEFAULT 0
  currency    VARCHAR(3) NOT NULL DEFAULT 'USD'
  status      VARCHAR NOT NULL DEFAULT 'active' (active/frozen/closed)
  created_at  TIMESTAMP
  updated_at  TIMESTAMP
```

### bank_transactions (PostgreSQL)
```
transactions
  id              UUID PK
  idempotency_key VARCHAR UNIQUE
  from_account_id UUID FK → accounts.id
  to_account_id   UUID FK → accounts.id
  amount          DECIMAL(19,4) NOT NULL
  currency        VARCHAR(3) NOT NULL
  type            VARCHAR NOT NULL (transfer/deposit/withdrawal)
  status          VARCHAR NOT NULL (pending/completed/failed)
  fraud_score     INTEGER
  created_at      TIMESTAMP
  updated_at      TIMESTAMP

transaction_entries
  id            UUID PK
  transaction_id UUID FK → transactions.id
  account_id    UUID FK → accounts.id
  entry_type    VARCHAR NOT NULL (debit/credit)
  amount        DECIMAL(19,4) NOT NULL
  created_at    TIMESTAMP
```

### MongoDB (bank_transactions audit)
```
audit_logs collection
  { _id, service, action, user_id, payload, created_at }
```

---

## Kafka Topics

| Topic                    | Publisher               | Subscriber            | Key Content               |
|--------------------------|-------------------------|-----------------------|---------------------------|
| `transaction.created`    | Transaction Service     | Fraud Service         | transaction_id            |
| `transaction.completed`  | Transaction Service     | Notification Service  | transaction_id, user_id   |
| `transaction.flagged`    | Fraud Service           | Notification Service  | transaction_id, risk_score|

---

## Scaling Strategy

### Microservices (HPA)
All 6 services have HorizontalPodAutoscalers:
- Scale from 2 → 10 replicas
- Trigger: CPU > 70% (or memory > 80%)
- Uses Kubernetes V2 HPA API

### Databases (manual scale)
- PostgreSQL: StatefulSet with PVC (10Gi, ReadWriteOnce)
- MongoDB: StatefulSet with PVC (5Gi, ReadWriteOnce)
- Kafka: StatefulSet with 3 replicas, per-broker PVC (10Gi each)
- Redis: single Deployment (stateful for caching, no persistence required)

### Prometheus
- Single replica with 15-day retention
- ConfigMap-driven scrape configuration targeting all pods with `prometheus.io/scrape: "true"` annotation

---

## Deployment Topology

```
                    ┌─────────────────────────────────────────┐
                    │           Kubernetes Cluster             │
                    │                                          │
  GitHub Actions    │  Namespace: banking                      │
  (CI/CD)           │                                          │
        │           │  ┌──────────┐  ┌──────────────────┐     │
        │           │  │ Ingress  │  │  nginx-ingress   │     │
        │           │  │ (gateway)│──│  Controller      │     │
        │           │  └────┬─────┘  └──────────────────┘     │
        ▼           │       │                                 │
  docker build      │       │ ClusterIP                       │
  docker push GHCR  │       ▼                                 │
                    │  ┌─────────┐                           │
                    │  │ Gateway │ (HPA 2–10)                │
                    │  └────┬────┘                           │
                    │       │ internal HTTP                   │
                    │  ┌────┴────┐                           │
                    │  │  Auth   │ (HPA)                      │
                    │  │Account  │ (HPA)                      │
                    │  │Transact.│ (HPA)                      │
                    │  │ Fraud   │ (HPA)                      │
                    │  │Notif.   │ (HPA)                      │
                    │  └─────────┘                           │
                    │       │                                 │
                    │   ┌───┴───┐  ┌──────────────┐          │
                    │   │ Kafka │  │  PostgreSQL  │          │
                    │   │Zookeep│  │   MongoDB    │          │
                    │   │ Redis │  │ Prometheus   │          │
                    │   └───────┘  │  Grafana     │          │
                    │              └──────────────┘          │
                    └─────────────────────────────────────────┘
```

---

## Tech Stack Decisions

| Decision           | Choice                          | Rationale                              |
|--------------------|---------------------------------|----------------------------------------|
| API Framework      | FastAPI (async)                 | Native async, Pydantic v2, auto-docs   |
| Auth Tokens        | JWT (HS256)                     | Stateless, fast validation             |
| Password Hashing   | bcrypt                          | Industry standard, adaptive cost       |
| DB Driver          | asyncpg (PostgreSQL)            | Non-blocking connection pool           |
| ORM                | SQLAlchemy 2.0 async            | Type-safe, async first                 |
| Cache/Sessions     | Redis 7                         | Sub-ms latency for rate limiting       |
| Message Broker     | Kafka 7.5                       | Durable, ordered, replay capability    |
| Audit Logs         | MongoDB (motor async)           | Flexible schema, time-series friendly  |
| ML Model           | IsolationForest (sklearn)       | Unsupervised, no labeled data needed   |
| Container          | Docker multi-arch (amd64/arm64) | GitHub Actions matrix build            |
| Orchestration      | Kubernetes + Helm 3             | Standard prod platform                 |
| Ingress            | NGINX Ingress Controller         | Mature, rate limiting at ingress level |
| Monitoring         | Prometheus + Grafana            | CNCF standard, rich query language     |