# Parket AI Banking Application

Production-grade four-tier microservice AI banking platform with fraud detection.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                     │
│                  (Web, Mobile, Third-party)                         │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   TIER 1: EDGE LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              API Gateway (port 8000)                          │   │
│  │  • JWT validation  • Rate limiting  • Request routing        │   │
│  │  • Request ID propagation  • Header forwarding               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌─────────────────┐ ┌────────────────┐ ┌──────────────────────────┐
│  TIER 2: BUSINESS LAYER                                       │
│                                                              │
│  ┌─────────────────┐ ┌────────────────┐ ┌────────────────┐   │
│  │  Auth Service   │ │ Account Service│ │Transaction Svc │   │
│  │   (port 8001)   │ │   (port 8002)  │ │   (port 8003)  │   │
│  │  bank_auth DB   │ │bank_accounts DB│ │bank_trans DB   │   │
│  └─────────────────┘ └────────────────┘ └───────┬────────┘   │
│                                                  │             │
└──────────────────────────────────────────────────┼─────────────┘
                                                   │ Kafka events
                          ┌────────────────────────┤
                          ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 TIER 3: AI/ML LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │           Fraud Detection Service (port 8004)                │   │
│  │  • IsolationForest ML model  • Risk scoring 0–100            │   │
│  │  • Trained on synthetic transaction data at startup          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Kafka events
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│          TIER 2b: EVENT-DRIVEN LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │      Notification Service (port 8005)                        │   │
│  │  • Kafka consumer  • Email/SMS simulation                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              TIER 4: DATA / INFRA LAYER                             │
│                                                                      │
│  PostgreSQL (3 DBs)  │  Redis  │  Kafka  │  MongoDB  │  Prometheus  │
│  bank_auth           │  Cache  │  Events │  Audit    │  Grafana     │
│  bank_accounts       │  Rate   │         │  Logs     │              │
│  bank_transactions   │  Limit  │         │           │              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer              | Component                  | Technology                     |
|--------------------|----------------------------|--------------------------------|
| Edge               | API Gateway                | FastAPI + httpx                |
| Business           | Auth Service               | FastAPI + asyncpg + bcrypt     |
| Business           | Account Service            | FastAPI + SQLAlchemy 2.0       |
| Business           | Transaction Service        | FastAPI + Kafka + MongoDB      |
| AI/ML              | Fraud Detection            | FastAPI + scikit-learn         |
| Event-Driven       | Notification Service       | FastAPI + aiokafka             |
| Infrastructure     | Database                   | PostgreSQL 15                  |
| Infrastructure     | Cache / Sessions           | Redis 7                        |
| Infrastructure     | Message Broker             | Apache Kafka 7.5               |
| Infrastructure     | Audit Store                | MongoDB 6                      |
| Infrastructure     | Monitoring                 | Prometheus + Grafana           |
| Deployment         | Container                  | Docker + Docker Compose        |
| Deployment         | Orchestration              | Kubernetes + Helm 3            |
| CI/CD              | Pipeline                   | GitHub Actions                 |

---

## Getting Started

### Prerequisites
- Docker 24+ and Docker Compose v2
- Python 3.11+

### 1. Clone and start infrastructure
```bash
git clone https://github.com/<your-org>/parket-ai.git
cd parket-ai

# Start all infrastructure (PostgreSQL, Redis, Kafka, MongoDB, Prometheus, Grafana)
docker compose up -d

# Verify all containers are running
docker compose ps
```

### 2. Start all services
```bash
# Each service has its own terminal, or use docker-compose up from root
docker compose up --build
```

### 3. Verify health
```bash
curl http://localhost:8000/health   # Gateway
curl http://localhost:8001/health   # Auth
curl http://localhost:8002/health   # Account
curl http://localhost:8003/health   # Transaction
curl http://localhost:8004/health   # Fraud
curl http://localhost:8005/health   # Notification
```

---

## API Documentation (Swagger)

| Service             | Swagger URL                          |
|---------------------|--------------------------------------|
| Gateway             | `http://localhost:8000/docs`         |
| Auth Service        | `http://localhost:8001/docs`         |
| Account Service     | `http://localhost:8002/docs`         |
| Transaction Service | `http://localhost:8003/docs`         |
| Fraud Service       | `http://localhost:8004/docs`         |
| Notification Service| `http://localhost:8005/docs`         |

---

## Environment Variables Reference

| Variable                  | Service       | Default                              |
|---------------------------|---------------|--------------------------------------|
| `DATABASE_URL`            | auth, account, transaction | `postgresql://...`          |
| `MONGO_URL`               | transaction   | `mongodb://...`                      |
| `REDIS_URL`               | all services  | `redis://redis:6379`                 |
| `KAFKA_BOOTSTRAP_SERVERS` | transaction, fraud, notification | `kafka:29092`     |
| `JWT_SECRET`              | auth, gateway | (from secret)                        |
| `POSTGRES_PASSWORD`       | all services  | `bankpass`                           |
| `FRAUD_SERVICE_URL`       | transaction   | `http://fraud-service:8004`          |

---

## Local Development Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install shared library
pip install -r src/shared/requirements.txt

# Install per-service dependencies
for svc in gateway auth-service account-service transaction-service fraud-service notification-service; do
  pip install -r services/$svc/requirements.txt
done

# Start infrastructure only
docker compose up -d postgres redis kafka zookeeper mongo prometheus grafana

# Run a single service (example: gateway)
cd services/gateway && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Kubernetes Deployment

### Prerequisites
- Kubernetes 1.28+
- Helm 3.14+
- `kubectl` configured with cluster access
- NGINX Ingress Controller installed

### Install the Helm chart

```bash
# Add the chart repo (or use local path)
helm repo add banking-app ./helm/banking-app

# Install with default values
helm install banking-app ./helm/banking-app \
  --namespace banking \
  --create-namespace

# Install with custom image tag (from CI/CD)
helm upgrade --install banking-app ./helm/banking-app \
  --namespace banking \
  --create-namespace \
  --set image.tag=$GITHUB_SHA \
  --wait --timeout 10m

# Dry-run to validate templates
helm template banking-app ./helm/banking-app

# Lint the chart
helm lint ./helm/banking-app

# Run Helm tests
helm test banking-app --namespace banking
```

### Configure secrets

```bash
# Create a kubeconfig secret for GitHub Actions (see .github/workflows/ci-cd.yml comments)
kubectl create secret generic kubeconfig-secret \
  --from-file=config=$HOME/.kube/config \
  --namespace banking

# Create JWT secret
kubectl create secret generic banking-secrets \
  --from-literal=jwt-secret=$(openssl rand -base64 32) \
  --from-literal=postgres-password=bankpass \
  --from-literal=mongo-password=bankpass \
  --from-literal=redis-password=bankpass \
  --namespace banking
```

---

## GitHub Actions CI/CD Pipeline

The pipeline at `.github/workflows/ci-cd.yml` runs:

1. **`lint-and-test`** — Python syntax check, ruff lint, mypy type check
2. **`build-and-push`** — Multi-arch Docker build and push to GHCR (matrix over 6 services)
3. **`package-helm`** — Helm lint, template validation, chart packaging
4. **`deploy`** — Helm upgrade install to Kubernetes (main branch only or manual dispatch)

### Secrets required in GitHub repo

| Secret Name           | Description                                    |
|-----------------------|------------------------------------------------|
| `GITHUB_TOKEN`        | Automatically provided by GitHub Actions       |
| `KUBECONFIG_CONTENT`  | Base64-encoded kubeconfig for the target cluster (add manually) |

---

## Monitoring (Prometheus + Grafana)

- **Prometheus**: `http://localhost:9090`
- **Grafana**: `http://localhost:3000` (admin / admin)

### Accessing metrics

All services expose Prometheus metrics at `/metrics`:
- `http_requests_total` — Request counter by service, method, status
- `http_request_duration_seconds` — Request latency histogram
- `fraud_model_predictions_total` — Fraud check counter
- `fraud_risk_score` — Current risk score gauge

---

## AI/ML Fraud Detection

The Fraud Detection Service uses an **IsolationForest** anomaly detection model:

1. **Training**: On startup, generates 10,000 synthetic transactions with features:
   - `amount` (log-scaled)
   - `transaction_type` (encoded)
   - `merchant_risk_score`
   - `hour_of_day`
   - `day_of_week`

2. **Prediction**: Scores incoming transactions 0–100
   - `0–30`: Low risk — auto-approved
   - `31–70`: Medium risk — flagged for review
   - `71–100`: High risk — transaction blocked

3. **Integration**: Transaction service calls fraud service via HTTP for high-value transactions (> $5,000) and via Kafka event subscription.

---

## Production Checklist

- [ ] Generate strong random values for all secrets (`jwt-secret`, `postgres-password`, etc.)
- [ ] Configure `imagePullSecrets` in values.yaml for GHCR private images
- [ ] Set `image.tag` to the specific Docker SHA (not `latest`) in production
- [ ] Configure TLS certificates for the Ingress
- [ ] Set resource limits appropriately for production workloads
- [ ] Configure Prometheus remote_write to a long-term storage backend
- [ ] Set `disableUsersForm: true` in Grafana production config
- [ ] Configure Kafka replication factor > 1 for durability
- [ ] Enable PostgreSQL connection pooling (PgBouncer or Odyssey)
- [ ] Set up alerts for HPA failures and PodCrashLoopBackoff
- [ ] Configure backup strategy for PostgreSQL and MongoDB
- [ ] Review and tune NetworkPolicy rules for least-privilege networking