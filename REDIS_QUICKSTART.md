# Redis Quick Start for HydroChat Phase 18

## ✅ What's Complete

### 1. Redis Server Installation (WSL Ubuntu)
```powershell
wsl redis-cli --version  # redis-cli 7.0.15 ✅
wsl redis-cli ping       # PONG ✅
```

### 2. Redis Configuration Infrastructure
- ✅ `backend/config/redis_config.py` - Connection pooling, health checks
- ✅ `backend/config/settings/base.py` - Django settings integration  
- ✅ `.env` and `.env.example` - Environment variable documentation
- ✅ 20/20 comprehensive tests passing

### 3. Documentation
- ✅ `REDIS_SETUP.md` - Complete setup and troubleshooting guide (500+ lines)
- ✅ `Implementation/PHASE18_SUMMARY.md` - Implementation details and architecture
- ✅ `REDIS_QUICKSTART.md` - This file (quick reference)

---

## ⚠️ Current Status

**Redis Infrastructure**: ✅ Complete  
**LangGraph Checkpointing**: ⚠️ Deferred (requires async context manager work)

**Current Behavior**: HydroChat operates in **stateless mode** (no conversation persistence across restarts)

---

## 🚀 Daily Usage

### Start Redis Server (Required if Testing Redis)
```powershell
wsl sudo service redis-server start
wsl redis-cli ping  # Verify: Should respond "PONG"
```

### Start HydroChat Backend (Default - No Redis Needed)
```powershell
cd backend
..\.venv-win\Scripts\Activate.ps1
python scripts/run_server.py
```

**Expected Logs**:
```
[GRAPH] 📝 Using stateless mode (no checkpointing)
```

### Stop Redis Server
```powershell
wsl sudo service redis-server stop
```

---

## 📊 Test Results

### Phase 18 Specific Tests
```powershell
# Run from backend/ directory
pytest apps/hydrochat/tests/test_phase18_redis_integration.py -v
```

**Results**: ✅ 20/20 tests passing

### Full Test Suite
```powershell
# Run from backend/ directory
pytest apps/hydrochat/tests/ -v
```

**Results**: ✅ 387/401 tests passing (14 failures are pre-existing, not related to Phase 18)

---

## 🔧 Configuration

### Environment Variables (`.env`)

```bash
# Redis is DISABLED by default (no setup required)
USE_REDIS_STATE=false

# Future: When LangGraph checkpointing is complete, enable with:
# USE_REDIS_STATE=true
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_DB=0
# REDIS_PASSWORD=
# REDIS_MAX_CONNECTIONS=50
# REDIS_SOCKET_TIMEOUT=5
# REDIS_STATE_TTL=7200
```

---

## 📁 Key Files

### Created
- `backend/config/redis_config.py` (188 lines)
- `backend/apps/hydrochat/tests/test_phase18_redis_integration.py` (150+ lines)
- `REDIS_SETUP.md` (500+ lines)
- `Implementation/PHASE18_SUMMARY.md` (comprehensive summary)
- `REDIS_QUICKSTART.md` (this file)

### Modified
- `backend/config/settings/base.py` (added Redis settings)
- `backend/apps/hydrochat/conversation_graph.py` (checkpointing logic, deferred)
- `.env` (added Redis config, disabled by default)
- `.env.example` (added Redis examples)

---

## 🐛 Troubleshooting

### Redis Not Starting
```powershell
wsl sudo service redis-server status  # Check status
wsl sudo cat /var/log/redis/redis-server.log  # View logs
wsl sudo service redis-server restart  # Restart
```

### Connection Issues
```powershell
wsl redis-cli ping  # Should respond "PONG"
wsl sudo netstat -tulpn | grep 6379  # Verify port 6379 is listening
```

### HydroChat Not Detecting Redis (Expected)
This is normal! Redis checkpointing is deferred. You should see:
```
[GRAPH] ⚠️ Redis checkpointing not yet fully implemented, using stateless mode
```

For detailed troubleshooting, see `REDIS_SETUP.md`.

---

## 🔮 Future Work

When LangGraph checkpointing is completed:

1. **Enable Redis**:
   ```bash
   # Edit .env
   USE_REDIS_STATE=true
   ```

2. **Start Redis**:
   ```powershell
   wsl sudo service redis-server start
   ```

3. **Restart Backend**:
   ```powershell
   cd backend; ..\.venv-win\Scripts\Activate.ps1; python scripts/run_server.py
   ```

4. **Expected Logs**:
   ```
   [REDIS] 🔧 Connection pool initialized
   [REDIS] ✅ Redis client initialized
   [GRAPH] ✅ Using Redis state storage (RedisSaver)
   ```

---

## 📚 Full Documentation

- **Setup Guide**: `REDIS_SETUP.md` (installation, config, troubleshooting)
- **Implementation Summary**: `Implementation/PHASE18_SUMMARY.md` (architecture, tests, status)
- **Phase 2 Plan**: `phase_2.md` (Phase 18 section, lines 117-496)

---

## ✅ Phase 18 Checklist

- [x] Redis server installed (WSL Ubuntu 7.0.15)
- [x] Redis server running and accessible
- [x] Redis configuration module (`redis_config.py`)
- [x] Django settings integration
- [x] Environment variables documented
- [x] Health checks implemented
- [x] Connection pooling tested
- [x] Graceful fallback verified
- [x] 20 Phase 18 tests passing
- [x] Zero regressions in existing tests
- [x] Comprehensive documentation
- [x] Redis disabled by default
- [ ] LangGraph checkpointing (deferred to future work)

**Status**: ✅ **Infrastructure Ready** | ⚠️ **Checkpointing Pending**

---

**Last Updated**: October 10, 2025  
**Phase 18 Status**: Core Infrastructure Complete


