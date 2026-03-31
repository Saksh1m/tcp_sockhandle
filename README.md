# Secure Real-time Location Sharing (TCP + WebSockets + TLS)

This project implements a secure, concurrent real-time location sharing application where authenticated users stream live coordinates to a central server and authorized subscribers receive updates instantly over WebSockets (running on top of TCP, optionally secured with TLS).

## Features

- **TCP socket programming with advanced socket options**
  - `SO_REUSEADDR`
  - `SO_KEEPALIVE`
  - `SO_RCVBUF`
  - `TCP_NODELAY`
- **TLS-secured WebSocket server (`wss://`)**
- **Authentication + authorization**
  - PBKDF2 password hashing
  - Session tracking and tokenized active session IDs
- **Concurrent connection handling**
  - Async I/O concurrency model (`asyncio`) for high fan-in/fan-out WebSocket traffic
- **Persistent storage (SQLite)**
  - Location updates with timestamp and sequence metadata
  - Connection/session logs
  - Security/authorization events
- **Reliable connection management**
  - Graceful shutdown handling
  - Ping/pong keepalive tuning
  - Client cleanup on disconnect
- **Experimental socket option evaluator**
  - Compares latency/throughput/database write rate under different socket option configurations

---

## Architecture and End-to-End Workflow

### 1) TLS-secured TCP connection establishment
1. Client opens a TCP connection to the server.
2. Server accepts socket and applies configured options (`SO_REUSEADDR`, `SO_KEEPALIVE`, `SO_RCVBUF`, `TCP_NODELAY`).
3. If TLS certificate/key are configured, server performs TLS handshake and negotiates encrypted channel.

### 2) WebSocket handshake
1. Client issues HTTP Upgrade request (`Upgrade: websocket`).
2. Server validates handshake and upgrades protocol to WebSocket.
3. Both sides switch to frame-based full-duplex messaging over the same TCP stream.

### 3) Authentication and authorization workflow
1. First client message must be `auth`:
   ```json
   {"type": "auth", "username": "alice", "password": "***"}
   ```
2. Server verifies PBKDF2 hash from database.
3. On success:
   - Session row is created (with start timestamp and client address).
   - Connection is marked authenticated.
4. Unauthorized attempts are denied and logged.

### 4) Full-duplex real-time operation
- Publisher sends:
  ```json
  {
    "type": "location_update",
    "lat": 37.77,
    "lon": -122.42,
    "accuracy": 8.3,
    "seq": 101,
    "client_ts": "2026-03-31T04:00:00Z"
  }
  ```
- Server validates and persists each update with server timestamp.
- Server broadcasts authorized updates to subscribers with server metadata.
- Subscribers can adjust subscriptions dynamically via:
  ```json
  {"type": "subscribe", "users": ["alice", "bob"]}
  ```

### 5) Graceful termination
- Client can send `close` WebSocket frame.
- Server records end timestamp, closes session, cleans connection registry.
- Transport teardown follows TCP FIN/ACK sequence.

---

## Concurrency model justification

The server uses **single-process asynchronous event-loop concurrency (`asyncio`)** with lock-protected shared registries for connection/session state:

- **Why this model**
  - WebSocket traffic is network I/O-bound.
  - Async I/O avoids thread-per-connection overhead.
  - Good scalability for thousands of mostly idle/low-rate connections.
- **Data integrity strategy**
  - SQLite writes are serialized through an async lock (`Database._write_lock`) to avoid inconsistent concurrent writes.
  - Broadcast registry updates are protected by manager lock.
- **Latency/scalability tradeoff**
  - `TCP_NODELAY` lowers per-update latency for small messages.
  - Controlled queueing and ping timeouts prevent stalled connections from back-pressuring entire system.

---

## Security practices

- TLS (recommended in production) for confidentiality/integrity.
- Password hashing with PBKDF2 + per-user salt.
- Per-message authentication state enforcement.
- Authorization checks for subscription/broadcast scope.
- Input schema validation and bounds checks for coordinates.
- Security event logging for incident audits.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Optional: generate self-signed cert for local TLS test

```bash
openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
  -keyout key.pem -out cert.pem -subj "/CN=localhost"
```

---

## Run

### 1) Initialize DB + create users

```bash
python -m app.admin --db-file location.db create-user --username alice
python -m app.admin --db-file location.db create-user --username bob
```

You will be prompted for passwords (dynamic input, no hardcoded credentials).

### 2) Start server

```bash
python -m app.server \
  --host 0.0.0.0 \
  --port 8765 \
  --db-file location.db \
  --syslog-file server.log \
  --reuse-addr true \
  --keepalive true \
  --rcvbuf 262144 \
  --tcp-nodelay true
```

For TLS:

```bash
python -m app.server ... --tls-cert cert.pem --tls-key key.pem
```

### 3) Run interactive client

```bash
python -m app.client --url ws://127.0.0.1:8765 --username alice
```

The client prompts for password and live coordinate input interactively.

---

### 4) Use the web application

After starting the server, open your browser:

- `http://127.0.0.1:8765/`

The server now serves a built-in single-page web UI that:
- authenticates a user
- subscribes to other users
- sends manual location updates
- streams live GPS updates via browser geolocation
- displays inbound broadcasts in real time

---

## Experimental socket option evaluation

Run comparative benchmark across option sets:

```bash
python -m app.experiment --db-file experiment.db
```

The script reports:
- mean publish-to-receive latency
- throughput (updates/sec)
- database write throughput

Option profiles include combinations toggling `SO_KEEPALIVE`, `SO_RCVBUF`, and `TCP_NODELAY`.

---

## Robustness and abnormal conditions tested

- sudden disconnect during stream
- unauthorized login/subscription attempts
- malformed payloads and invalid coordinates
- high-frequency update burst
- backpressure handling under delayed consumer

Also documented in `tests/` for positive and negative scenarios.

---

## Notes on TCP states

Under repeated rapid reconnect/disconnect tests, short-lived sockets commonly enter:
- `TIME_WAIT` on the active closer side (normal safety delay)
- `CLOSE_WAIT` if peer closes but application delays final close

Server cleanup logic aims to minimize lingering `CLOSE_WAIT` by promptly finalizing connection teardown in `finally` blocks.

