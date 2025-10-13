# Redis Setup Guide for HydroChat Phase 18

## Overview

HydroChat Phase 18 implements **optional** Redis-backed conversation state management infrastructure for:
- **Persistent state** across server restarts (future)
- **Distributed deployments** with load balancing (future)
- **Shared conversation state** across multiple HydroChat instances (future)

**Current Status**: ✅ **Redis infrastructure complete** | ⚠️ **LangGraph checkpointing deferred**

Redis is **disabled by default** and the system operates in stateless mode. The full Redis checkpointing feature will be completed in a future iteration once LangGraph's async context manager requirements are fully implemented.

---

## Quick Setup (WSL Ubuntu - Recommended for Windows)

### Prerequisites
- Windows 10/11 with WSL 2 installed
- Ubuntu distribution in WSL (pre-installed on your system)

### Installation Steps

#### 1. Install Redis in WSL
```powershell
# Update package lists
wsl sudo apt-get update

# Install Redis server
wsl sudo apt-get install redis-server -y
```

#### 2. Start Redis Server
```powershell
# Start Redis service
wsl sudo service redis-server start

# Verify Redis is running (should respond with "PONG")
wsl redis-cli ping
```

#### 3. Enable Redis in HydroChat
Edit `.env` file in the project root and change:
```bash
USE_REDIS_STATE=true
```

#### 4. Restart HydroChat Backend
```powershell
cd backend; ..\.venv-win\Scripts\Activate.ps1; python scripts/run_server.py
```

Look for this log message:
```
[GRAPH] ✅ Using Redis state storage (RedisSaver) - Connection: localhost:6379
```

---

## Configuration Options

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_REDIS_STATE` | `false` | Enable/disable Redis state management |
| `REDIS_HOST` | `localhost` | Redis server hostname or IP address |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number (0-15) |
| `REDIS_PASSWORD` | *(empty)* | Redis password (if authentication enabled) |
| `REDIS_MAX_CONNECTIONS` | `50` | Maximum connections in pool |
| `REDIS_SOCKET_TIMEOUT` | `5` | Socket timeout in seconds |
| `REDIS_STATE_TTL` | `7200` | State expiration time (2 hours) |

### Example Configuration

**Development (local Redis)**:
```bash
USE_REDIS_STATE=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

**Production (secured Redis)**:
```bash
USE_REDIS_STATE=true
REDIS_HOST=redis.production.example.com
REDIS_PORT=6379
REDIS_DB=1
REDIS_PASSWORD=your_secure_password_here
REDIS_MAX_CONNECTIONS=100
REDIS_STATE_TTL=3600
```

---

## Redis Management Commands

### WSL Ubuntu Commands

```powershell
# Start Redis server
wsl sudo service redis-server start

# Stop Redis server
wsl sudo service redis-server stop

# Restart Redis server
wsl sudo service redis-server restart

# Check Redis status
wsl sudo service redis-server status

# Test connection
wsl redis-cli ping

# Connect to Redis CLI
wsl redis-cli

# Check Redis version
wsl redis-cli --version
```

### Redis CLI Commands

Once connected (`wsl redis-cli`), useful commands:

```redis
# Test connection
PING

# View all keys (caution in production!)
KEYS *

# Get specific key
GET conversation:123

# Delete all keys in current database (USE WITH CAUTION!)
FLUSHDB

# Get database info
INFO

# Monitor real-time commands
MONITOR

# Exit CLI
exit
```

---

## Troubleshooting

### Redis Not Starting

**Error**: `Failed to start redis-server.service`

**Solution**:
```powershell
# Check Redis status
wsl sudo service redis-server status

# View Redis logs
wsl sudo cat /var/log/redis/redis-server.log

# Try manual start
wsl redis-server
```

### Connection Refused

**Error**: `Could not connect to Redis at localhost:6379: Connection refused`

**Solution**:
```powershell
# 1. Verify Redis is running
wsl sudo service redis-server status

# 2. Start Redis if not running
wsl sudo service redis-server start

# 3. Test connection
wsl redis-cli ping

# 4. Check if port 6379 is in use
wsl sudo netstat -tulpn | grep 6379
```

### HydroChat Not Detecting Redis

**Symptoms**: Logs show `[GRAPH] 📝 Using stateless mode (no checkpointing)`

**Solutions**:

1. **Verify `.env` configuration**:
   ```bash
   USE_REDIS_STATE=true  # Must be lowercase 'true'
   ```

2. **Check Redis is running**:
   ```powershell
   wsl redis-cli ping  # Should respond with "PONG"
   ```

3. **Restart HydroChat backend**:
   ```powershell
   # Stop backend (Ctrl+C in server terminal)
   cd backend; ..\.venv-win\Scripts\Activate.ps1; python scripts/run_server.py
   ```

4. **Check logs for health check failures**:
   - Look for `[REDIS] ⚠️ Connection failed` messages
   - Verify Redis host/port/password are correct

### Permission Errors

**Error**: `Permission denied when starting Redis`

**Solution**:
```powershell
# Fix Redis directory permissions
wsl sudo chown redis:redis /var/lib/redis
wsl sudo chmod 750 /var/lib/redis
wsl sudo service redis-server restart
```

---

## Advanced Configuration

### Enable Redis Authentication

1. Edit Redis configuration:
   ```powershell
   wsl sudo nano /etc/redis/redis.conf
   ```

2. Find and uncomment/add:
   ```conf
   requirepass your_secure_password_here
   ```

3. Restart Redis:
   ```powershell
   wsl sudo service redis-server restart
   ```

4. Update HydroChat `.env`:
   ```bash
   REDIS_PASSWORD=your_secure_password_here
   ```

### Configure Redis Persistence

Edit `/etc/redis/redis.conf` to enable data persistence:

**Append-Only File (AOF) - Recommended**:
```conf
appendonly yes
appendfsync everysec
```

**RDB Snapshots**:
```conf
save 900 1      # Save after 900 seconds if at least 1 key changed
save 300 10     # Save after 300 seconds if at least 10 keys changed
save 60 10000   # Save after 60 seconds if at least 10000 keys changed
```

### Auto-Start Redis on WSL Boot

Add to your PowerShell profile (`$PROFILE`):

```powershell
# Auto-start Redis when opening PowerShell
if ((wsl sudo service redis-server status) -notlike "*running*") {
    wsl sudo service redis-server start
    Write-Host "✅ Redis started automatically" -ForegroundColor Green
}
```

---

## Alternative Installation Methods

### Option 1: Docker (Production-Ready)

**Advantages**: Isolated, portable, easy updates

```powershell
# Start Redis container
docker run -d --name hydrochat-redis -p 6379:6379 redis:7-alpine

# Verify
docker ps | findstr redis
redis-cli ping

# Stop
docker stop hydrochat-redis

# Remove
docker rm hydrochat-redis
```

**With persistence**:
```powershell
docker run -d --name hydrochat-redis \
  -p 6379:6379 \
  -v redis-data:/data \
  redis:7-alpine redis-server --appendonly yes
```

### Option 2: Windows Native (Memurai)

**Memurai** is Redis for Windows (commercial but has free tier)

1. Download: https://www.memurai.com/get-memurai
2. Install using MSI installer
3. Memurai runs as Windows Service
4. Default port: `6379` (same as Redis)
5. Update HydroChat `.env` with `REDIS_HOST=localhost`

---

## Testing Redis Integration

### Basic Health Check

```powershell
# From project root
..\.venv-win\Scripts\Activate.ps1; cd backend; python -c "from config.redis_config import RedisConfig; print('✅ Redis available' if RedisConfig.health_check() else '❌ Redis unavailable')"
```

### Run Phase 18 Test Suite

```powershell
# Activate venv and run tests
..\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase18_redis_integration.py -v
```

Expected output:
```
test_redis_disabled_by_default PASSED
test_redis_enabled_via_env PASSED
test_get_config_from_env PASSED
test_health_check_when_available PASSED
test_graph_uses_redis_saver_when_enabled PASSED
test_graceful_fallback_to_memory_when_redis_unavailable PASSED
...
==================== 20 passed in 2.34s ====================
```

### Full Integration Test

```powershell
# Run all tests to ensure Redis doesn't break existing functionality
..\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/ -v
```

---

## Monitoring Redis State

### Check Stored Conversations

```powershell
# Connect to Redis CLI
wsl redis-cli

# List all keys
KEYS *

# View specific conversation checkpoint
# (LangGraph stores checkpoints with thread_id)
GET <thread_id>

# Count total keys
DBSIZE

# Monitor live commands
MONITOR
```

### Memory Usage

```redis
# In redis-cli
INFO memory
```

Key metrics:
- `used_memory_human`: Current memory usage
- `used_memory_peak_human`: Peak memory usage
- `maxmemory`: Maximum memory limit

---

## Production Deployment Checklist

- [ ] Redis server installed and running
- [ ] Redis authentication enabled (`requirepass`)
- [ ] Redis persistence configured (AOF recommended)
- [ ] Firewall rules configured (restrict port 6379)
- [ ] `USE_REDIS_STATE=true` in production `.env`
- [ ] Connection pooling configured (`REDIS_MAX_CONNECTIONS`)
- [ ] TTL appropriate for workload (`REDIS_STATE_TTL`)
- [ ] Monitoring configured (health checks, memory alerts)
- [ ] Backup strategy for Redis data (if persistence enabled)
- [ ] Redis server secured (no public internet access)
- [ ] HydroChat logs monitored for Redis warnings

---

## FAQ

### Q: Is Redis required for HydroChat?
**A**: No. Redis is **optional**. HydroChat works perfectly in stateless mode without Redis.

### Q: What happens if Redis crashes during a conversation?
**A**: HydroChat automatically detects the failure and falls back to stateless mode. The current conversation may lose state, but new messages will work.

### Q: Can I migrate from in-memory to Redis?
**A**: Yes, but state is not automatically migrated. New conversations will use Redis. Existing in-memory states are session-specific.

### Q: How much memory does Redis use?
**A**: Depends on conversation count and complexity. Typical conversation state: ~5-10KB. With TTL=2h and moderate load, expect <100MB usage.

### Q: Can I use Redis Cloud or AWS ElastiCache?
**A**: Yes! Set `REDIS_HOST` to your cloud Redis endpoint and configure `REDIS_PASSWORD`.

### Q: Does Redis improve HydroChat performance?
**A**: Not directly. Redis enables distributed deployments and state persistence. For single-server setups, in-memory mode is faster.

---

## Support

For Redis-related issues:
1. Check this documentation first
2. Review HydroChat logs: `backend/logs/`
3. Check Redis logs: `wsl sudo cat /var/log/redis/redis-server.log`
4. Verify configuration: `.env` file settings
5. Test Redis connection: `wsl redis-cli ping`

For Phase 18 implementation details, see:
- `phase_2.md` - Phase 18 specification
- `Implementation/PHASE18_SUMMARY.md` - Implementation summary
- `backend/config/redis_config.py` - Configuration code
- `backend/apps/hydrochat/conversation_graph.py` - LangGraph integration

---

**Last Updated**: Phase 18 Implementation (October 2025)

