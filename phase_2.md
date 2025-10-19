# HydroChat Phase 2.0 - Critical Implementation Gaps

Source Spec: `HydroChat.md` (authoritative). Based on Grok feedback analysis comparing phase.md implementation against original specification. Post-Phase 13 status: 80.13% coverage, 217 tests passing.

**Note**: For code review improvements and refactoring changes, see [`code_review.md`](code_review.md).

Legend:
- D = Deliverables (artifacts produced)
- EC = Exit Criteria (verifiable conditions to advance)
- DEP = Dependencies (must be satisfied before starting)
- RISK = Key risks / mitigations

---
## Phase 14 – Gemini API Integration & LLM Fallback (HydroChat.md §2, §15)
D:
- `gemini_client.py` with: `classify_intent_fallback(message, context, conversation_summary)`
- Environment config: `GEMINI_API_KEY` loading with validation in `config.py` per §16
- Integration in `classify_intent_node`: call LLM when regex returns UNKNOWN per §15
- Prompt engineering: structured prompts for intent classification with examples of all 7 Intent enum values
- Response parsing: extract Intent enum from Gemini response with strict JSON schema validation
- Field extraction fallback: LLM-based field extraction when regex patterns fail (NRIC, name, contact, DOB)
- Usage tracking: API call metrics, cost monitoring, rate limit handling
- Model specification: Use `gemini-2.5-flash` as specified in §2 for speed optimization
EC:
- Test: ambiguous message "help me with that patient thing" -> routes to appropriate intent via LLM
- Test: API key missing -> graceful degradation to UNKNOWN intent with proper logging
- Test: Gemini API error -> fallback to UNKNOWN with exponential backoff retry
- Test: LLM field extraction handles natural language variations ("patient John with contact nine one two three...")
- Test: Cost tracking increments properly for successful/failed LLM calls
DEP: Phase 13 completion
RISK: API rate limits – implement exponential backoff per §17; API costs – add usage tracking; Prompt injection – sanitize user input; LLM hallucination – validate responses against Intent enum strictly.

### Phase 14 Implementation Status (2025-10-19)

**✅ COMPLETED:**
- ✅ `gemini_client.py` with official `google-genai` SDK (V2 implementation)
- ✅ `classify_intent_fallback()` - LLM intent classification when regex returns UNKNOWN
- ✅ `extract_fields_fallback()` - LLM field extraction (NRIC, names, contact, DOB)
- ✅ Environment config: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_MAX_INPUT_LENGTH` via `.env`
- ✅ Prompt engineering: Structured prompts with all 7 Intent enum examples
- ✅ Response parsing: JSON extraction with markdown support
- ✅ Usage tracking: Token counting, cost calculation via `response.usage_metadata`
- ✅ Prompt injection prevention: Input sanitization and validation
- ✅ Model: `gemini-2.0-flash-exp` (official SDK)
- ✅ All 28 LLM integration tests passing

**Integration Status**:
- ✅ Integrated in `conversation_graph.py` (imports GeminiClient)
- ✅ Used by `intent_classifier.py` for fallback classification
- ✅ Metrics tracking via `agent_stats.py`

**Key Features**:
- Exponential backoff on API errors (3 retries max)
- Rate limit handling with proper error messages
- Configurable input length limit (default: 1000 chars)
- Thread-safe singleton pattern
- Comprehensive error logging

**References**:
- Implementation: `backend/apps/hydrochat/gemini_client.py`
- Tests: `backend/apps/hydrochat/tests/test_phase14_llm_integration.py` (28/28 passing)
- Configuration: `backend/config/settings/base.py` lines 124-128

---

## Phase 15 – Missing Core Nodes Implementation (HydroChat.md §24, §27)
D:
- `ingest_user_message_node` (Node 1 per §24): Message preprocessing, validation, sanitization before classification
- `summarize_history_node` (Node 15 per §24): Conversation summarization when `recent_messages` at capacity (5 items) per §27
- `finalize_response_node` (Node 16 per §24): Final response formatting, PII masking validation, consistent styling per §25
- Updated `conversation_graph.py` routing: entry point through ingest_user_message, exit through finalize_response per §24.1
- State field addition: `history_summary` (string) for maintaining conversation context beyond 5 messages per §8
- Integration with LangGraph StateGraph: proper node registration and conditional routing
- Response formatting templates implementation per §25 (creation success, update success, deletion success, etc.)
EC:
- Test: Long conversation (>5 turns) maintains context through summary generation
- Test: All responses pass through finalize_response for consistent formatting and PII masking
- Test: ingest_user_message sanitizes malicious input and validates message length
- Test: Summarization uses Gemini API to create coherent conversation history
- Integration test: Complete flow ingest -> classify -> execute -> finalize with all 16 nodes
- Test: Response templates match §25 specifications exactly
DEP: Phase 14 (Gemini integration needed for summarization per §27)
RISK: Summarization quality – test with edge cases and malformed conversations; Performance impact – add timing metrics; Node routing complexity – validate all 16 nodes in routing map.

## Phase 16 – Centralized Routing Map & Graph Validation (HydroChat.md §24.1)
D:
- `routing_map.py` constant: Complete routing matrix per HydroChat.md §24.1 with all 16 nodes and conditional tokens
- Graph validation: State transition validation preventing invalid routes and hallucination per §26
- Route enforcement: Assertion checks in each node ensuring only valid next steps per routing table
- Documentation: Visual graph diagram showing all 16 nodes and connections with Mermaid/GraphViz
- Debug utilities: Graph state inspection, route tracing for debugging, state transition logging
- Token validation: Ensure only allowed tokens from §24.1 table are returned by conditional nodes
- Routing map constants: AMBIGUOUS_PRESENT, RESOLVED, NEED_MORE_FIELDS, FIELDS_COMPLETE, etc. per §24.1
EC:
- Test: Invalid state transition raises assertion error with clear diagnostic
- Test: All 16 nodes referenced in routing map with valid connections matching §24.1 table
- Test: Graph traversal validation catches orphaned nodes and unreachable states
- Test: Token validation prevents hallucinated routing decisions
- Documentation: README section with complete graph visualization
- Test: Route enforcement catches developer errors in node implementations
DEP: Phase 15 (all nodes must exist before mapping)
RISK: Route explosion – keep map simple and data-driven; Maintenance burden – auto-generate validation from routing constants; Token drift – enforce token enum usage.

## Phase 17 – Enhanced Metrics & Performance Monitoring (HydroChat.md §29, §22)
D:
- **Gemini SDK Migration**: Migrate from manual `httpx` calls to official `google-genai` SDK (`google.genai.Client`) for accurate token counting and cost tracking
  - Replace `gemini_client.py` httpx implementation with official SDK `client.models.generate_content()`
  - Use `client.models.count_tokens()` for accurate token counting per official SDK docs
  - Extract real token usage from API response metadata instead of estimates
  - Update `GeminiUsageMetrics` to track actual tokens from `response.usage_metadata` field
- Extended `MetricsLogger`: LLM API call tracking with **accurate token counts**, conversation flow timing, response latency monitoring
- **Performance benchmarks**: Response time tracking decorator with <2s threshold enforcement per §2 synchronous mode (excluding network)
  - Add `@track_response_time` decorator for conversation graph entry points
  - Capture start/end timestamps for each conversation turn
  - Log warnings when response time exceeds 2s threshold
- Conversation analytics: Intent classification accuracy, user satisfaction indicators, error rate tracking
- Alert thresholds: Error rate >20% warnings, excessive retry detection, performance degradation alerts
- **Dashboard data preparation**: JSON export endpoint (`/api/hydrochat/metrics/export/`) for external monitoring per §29
  - Developer-only endpoint using existing `generate_stats_summary()` 
  - Returns comprehensive metrics in JSON format for dashboard consumption
- Agent stats command: Developer-only access restrictions per §29 (not exposed to end-clinician)
- Logging taxonomy enhancement: Performance timing logs, LLM interaction logs per §22
- **Metrics retention policy**: In-memory retention with TTL (max 1000 entries, 24h expiration, hourly cleanup)
  - Configurable via `METRICS_MAX_ENTRIES` and `METRICS_TTL_HOURS` settings
  - Manual cleanup task for expired entries
  - Note: Persistent storage deferred to Phase 18 (Redis)
EC:
- Test: Performance benchmark decorator tracks and warns on >2s response time (mocked network delays)
- Test: Gemini SDK migration provides **accurate token counts** from API responses (not estimates)
- Test: Token counting uses `client.models.count_tokens()` and validates against actual API usage
- Test: LLM API metrics track successful/failed/retried calls with **real cost calculations** based on actual token usage
- Test: Response time decorator captures timing for all conversation turns with proper logging
- Test: Conversation analytics export includes accuracy percentages and error rates via JSON endpoint
- Test: Agent stats command shows new metrics categories (token usage, response times) with proper access control
- Test: Alert thresholds trigger warnings at configured levels (error rate >20%, retry count >5)
- Test: Metrics retention policy correctly expires entries after 24h and enforces 1000-entry cap
- Test: JSON export endpoint returns complete stats structure for dashboard integration
- Integration: Stats command restricted to developer-only context per §29
- Validation: Compare httpx baseline metrics vs SDK metrics to ensure parity after migration
DEP: 
- Phases 14-15 (LLM integration needed for API metrics, all nodes needed for flow timing)
- Python package: `google-genai>=1.41.0` (already in requirements.txt, line 110)
- Ensure `GEMINI_API_KEY` configured in environment per §16
RISK: 
- **SDK Migration**: Breaking changes from httpx → official SDK; Mitigation: Comprehensive test suite validates parity, maintain backward compatibility in metrics structure
- **Token Tracking Accuracy**: SDK response structure may vary; Mitigation: Parse `response.usage_metadata.total_token_count` field with fallback to zero if missing
- Metric storage explosion – implement retention policy with configurable TTL
- Performance overhead – batch metric updates, use lightweight timing decorators
- Alert fatigue – tune thresholds carefully based on production data
- **Cost Tracking Precision**: Token-to-cost conversion uses fixed rates; Mitigation: Document rate assumptions, make configurable per model

### Phase 17 Implementation Status (2025-10-19)

**✅ COMPLETED:**
1. **Gemini SDK Migration (V1 → V2)**:
   - ✅ Migrated from manual `httpx` to official `google-genai` SDK
   - ✅ Deleted old `gemini_client.py` (V1 httpx implementation)
   - ✅ Renamed `gemini_client_v2.py` → `gemini_client.py`
   - ✅ Updated all imports across 5 files (conversation_graph, intent_classifier, agent_stats, views, tests)
   - ✅ All 28 LLM integration tests updated and passing
   - ✅ Accurate token tracking from `response.usage_metadata` (prompt + completion tokens)
   - ✅ Cost calculation using real token counts (not estimates)
   - ✅ Model: `gemini-2.0-flash-exp` (SDK default)

2. **Metrics Retention Policy**:
   - ✅ Implemented in-memory retention with configurable TTL
   - ✅ `MetricsStore` class with max_entries and ttl_hours parameters
   - ✅ Automatic cleanup of expired entries
   - ✅ Configurable via `METRICS_MAX_ENTRIES` and `METRICS_TTL_HOURS`
   - ✅ All 27 metrics retention tests passing

3. **Configuration Management**:
   - ✅ Added `GEMINI_MAX_INPUT_LENGTH` configuration (default: 1000 chars)
   - ✅ Configurable via `.env` file and Django settings
   - ✅ Better error messages with actual values (performance.py, metrics_store.py)

4. **Metrics Export Endpoint**:
   - ✅ `/api/hydrochat/metrics/export/` JSON endpoint implemented
   - ✅ Developer-only access (staff/superuser)
   - ✅ Returns LLM metrics, performance stats, retention policy info
   - ✅ Fixed conversation store access to use proper API

**🔄 IN PROGRESS / TODO:**
1. **Performance Benchmarks**:
   - ⏳ `@track_response_time` decorator (not yet implemented)
   - ⏳ <2s threshold enforcement and warnings
   - ⏳ Response latency monitoring

2. **Conversation Analytics**:
   - ⏳ Intent classification accuracy tracking
   - ⏳ Error rate monitoring with >20% threshold alerts
   - ⏳ User satisfaction indicators

3. **Extended MetricsLogger**:
   - ⏳ Conversation flow timing (beyond current metrics)
   - ⏳ Per-turn performance tracking

**Key Files Modified**:
- `backend/apps/hydrochat/gemini_client.py` (V2 SDK implementation)
- `backend/apps/hydrochat/performance.py` (metrics with retention)
- `backend/apps/hydrochat/metrics_store.py` (storage with TTL)
- `backend/apps/hydrochat/views.py` (metrics export endpoint)
- `backend/config/settings/base.py` (Gemini configuration)
- `.env` and `.env.example` (configuration parameters)

**Tests Status**:
- ✅ 28/28 LLM integration tests passing (`test_phase14_llm_integration.py`)
- ✅ 27/27 metrics retention tests passing (`test_phase17_metrics_retention.py`)
- ✅ 2/2 metrics export tests passing (`test_phase17_sdk_migration.py`)

**Next Steps for Phase 17 Completion**:
1. Implement `@track_response_time` decorator
2. Add conversation analytics tracking
3. Implement alert threshold logic (error rate >20%)
4. Complete performance benchmark tests
5. Document metrics dashboard integration guide

**References**:
- SDK Migration Details: [`code_review.md`](code_review.md#gemini-client-sdk-migration-v1--v2-2025-10-19)
- Test Files: `backend/apps/hydrochat/tests/test_phase17_*.py`
- Configuration: `backend/config/settings/base.py` lines 124-128

---

## Phase 18 – Advanced State Management (Redis Option) (HydroChat.md §2 Future)

### Implementation Overview
Implement **optional** Redis-backed conversation state management as an alternative to in-memory storage, enabling distributed HydroChat deployments with persistent conversation state across server restarts and load-balanced instances.

### D: Deliverables

#### 1. Redis Configuration Module (`backend/config/redis_config.py`)
**Purpose**: Centralized Redis connection management with health checks and failover
**Key Components**:
```python
class RedisConfig:
    """Redis configuration with connection pooling"""
    # Environment variables
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    USE_REDIS_STATE = os.getenv("USE_REDIS_STATE", "false").lower() == "true"
    
    @classmethod
    def get_client(cls) -> Redis:
        """Get or create Redis client with connection pool"""
        # Lazy initialization with health check
        # Connection pool with configurable max connections
        # Proper error handling for connection failures
    
    @classmethod
    def health_check(cls) -> bool:
        """Perform Redis health check with ping"""
        # Return True if Redis available, False otherwise
        # Log warnings on failure for monitoring
```

**Features**:
- Connection pooling (default: 50 max connections)
- Health check interval (default: 30 seconds)
- Configurable timeouts (socket_timeout: 5s, connect_timeout: 5s)
- Decode responses to strings (decode_responses=True)
- Graceful error handling with proper logging

#### 2. Redis State Store (`backend/apps/hydrochat/redis_state_store.py`)
**Purpose**: Redis-backed implementation of ConversationStateStore interface
**Key Components**:
```python
class RedisStateStore:
    """Redis-backed conversation state storage"""
    
    def __init__(self, redis_client: Redis, ttl_seconds: int = 7200):
        self.redis = redis_client
        self.ttl = ttl_seconds  # 2 hours default
    
    def save_state(self, conversation_id: str, state: ConversationState):
        """Save conversation state to Redis with TTL"""
        # Serialize state with custom encoder
        # Store with conversation_id as key
        # Set TTL for automatic expiration
    
    def load_state(self, conversation_id: str) -> ConversationState:
        """Load conversation state from Redis"""
        # Retrieve JSON from Redis
        # Deserialize with custom decoder
        # Return ConversationState object
    
    def delete_state(self, conversation_id: str):
        """Delete conversation state"""
        # Remove key from Redis
    
    def exists(self, conversation_id: str) -> bool:
        """Check if conversation exists"""
        # Check Redis key existence
```

**Interface Compatibility**: Same methods as `ConversationStateStore` for drop-in replacement

#### 3. State Serialization Handler (`backend/apps/hydrochat/serialization.py`)
**Purpose**: Custom JSON encoder/decoder for complex Python objects
**Critical for**:
- `deque` with maxlen preservation
- `Enum` values (Intent, RoutingToken, etc.)
- `datetime` objects
- Nested Pydantic models

**Implementation**:
```python
class StateEncoder(json.JSONEncoder):
    """Custom JSON encoder for conversation state"""
    def default(self, obj):
        if isinstance(obj, deque):
            return {
                "__type__": "deque",
                "items": list(obj),
                "maxlen": obj.maxlen
            }
        elif isinstance(obj, Enum):
            return {
                "__type__": "enum",
                "value": obj.value,
                "class": obj.__class__.__name__
            }
        elif isinstance(obj, datetime):
            return {
                "__type__": "datetime",
                "isoformat": obj.isoformat()
            }
        return super().default(obj)

def state_decoder(dct):
    """Custom JSON decoder for conversation state"""
    if "__type__" in dct:
        if dct["__type__"] == "deque":
            return deque(dct["items"], maxlen=dct["maxlen"])
        elif dct["__type__"] == "enum":
            enum_class = globals()[dct["class"]]
            return enum_class(dct["value"])
        elif dct["__type__"] == "datetime":
            return datetime.fromisoformat(dct["isoformat"])
    return dct
```

#### 4. LangGraph Redis Integration (`conversation_graph.py` enhancement)
**Purpose**: Integrate LangGraph checkpoint system with Redis
**Implementation**:
```python
from langgraph.checkpoint.redis import RedisSaver

def compile_conversation_graph(use_redis: bool = False):
    """Compile conversation graph with optional Redis checkpointing"""
    graph_builder = StateGraph(ConversationState)
    # ... add nodes and edges ...
    
    if use_redis and RedisConfig.USE_REDIS_STATE:
        # Use Redis-backed checkpointing
        redis_saver = RedisSaver.from_conn_string(
            f"redis://{RedisConfig.REDIS_HOST}:{RedisConfig.REDIS_PORT}"
        )
        return graph_builder.compile(checkpointer=redis_saver)
    else:
        # Use in-memory checkpointing
        from langgraph.checkpoint.memory import MemorySaver
        return graph_builder.compile(checkpointer=MemorySaver())
```

**Benefits**:
- Automatic state persistence across server restarts
- State sharing across load-balanced instances
- Built-in checkpoint management
- Thread-safe operations

#### 5. Failover Logic (`backend/apps/hydrochat/state_manager.py`)
**Purpose**: Graceful fallback when Redis unavailable
**Implementation Pattern**:
```python
class StateManager:
    """Manages conversation state with failover support"""
    
    def __init__(self):
        self.use_redis = RedisConfig.USE_REDIS_STATE
        self.redis_available = False
        
        if self.use_redis:
            try:
                self.redis_available = RedisConfig.health_check()
                if self.redis_available:
                    self.store = RedisStateStore(RedisConfig.get_client())
                    logger.info("✅ Using Redis state storage")
                else:
                    logger.warning("⚠️ Redis unavailable, using in-memory fallback")
                    self.store = InMemoryStateStore()
            except Exception as e:
                logger.error(f"❌ Redis initialization failed: {e}")
                self.store = InMemoryStateStore()
        else:
            self.store = InMemoryStateStore()
            logger.info("📝 Using in-memory state storage")
```

#### 6. Configuration Management
**Environment Variables** (add to `backend/.env`):
```bash
# Redis State Management (Phase 18)
USE_REDIS_STATE=false  # Toggle Redis usage
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Optional password
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5
REDIS_HEALTH_CHECK_INTERVAL=30
REDIS_STATE_TTL=7200  # 2 hours in seconds
```

**Django Settings Integration** (`backend/config/settings/base.py`):
```python
# Redis Configuration
REDIS_ENABLED = os.getenv('USE_REDIS_STATE', 'false').lower() == 'true'
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
REDIS_STATE_TTL = int(os.getenv('REDIS_STATE_TTL', '7200'))
```

#### 7. Migration Utilities (`backend/apps/hydrochat/state_migration.py`)
**Purpose**: Tools for migrating state between storage backends
**Commands**:
```python
def export_in_memory_to_redis():
    """Export all in-memory conversations to Redis"""
    # Iterate through in-memory store
    # Serialize and save to Redis with TTL
    
def import_redis_to_in_memory():
    """Import Redis conversations to in-memory (testing/debugging)"""
    # Scan Redis keys matching conversation pattern
    # Load and store in memory
    
def clear_expired_redis_states():
    """Cleanup utility for expired conversation states"""
    # Manual TTL enforcement if needed
```

### EC: Exit Criteria

#### Functional Tests:
1. **Redis Operations Parity**:
   ```python
   def test_redis_store_operations():
       # save_state, load_state, delete_state, exists
       # Assert same behavior as in-memory store
   ```

2. **Graceful Fallback**:
   ```python
   def test_redis_unavailable_fallback():
       # Mock Redis connection failure
       # Verify fallback to in-memory
       # Check proper warning logging
   ```

3. **State Serialization Round-Trip**:
   ```python
   def test_state_serialization_integrity():
       # Create state with deque, enums, datetime
       # Serialize to JSON
       # Deserialize back
       # Assert all fields preserved exactly
   ```

4. **Connection Pooling**:
   ```python
   def test_connection_pool_efficiency():
       # Concurrent save/load operations (50 threads)
       # Verify connection reuse
       # Check pool stats
   ```

#### Performance Tests:
5. **Concurrent Load Test**:
   ```python
   def test_100_concurrent_conversations():
       # 100 parallel conversation threads
       # Each saves/loads state to/from Redis
       # Assert <2s response time maintained
       # Monitor memory and connection usage
   ```

6. **TTL and Expiration**:
   ```python
   def test_ttl_expiration():
       # Save state with TTL=5 seconds
       # Verify state exists immediately
       # Wait 6 seconds
       # Verify state expired and removed
   ```

#### Integration Tests:
7. **LangGraph Checkpoint Integration**:
   ```python
   def test_langgraph_redis_checkpointing():
       # Compile graph with Redis checkpointer
       # Run multi-step conversation
       # Verify checkpoints saved to Redis
       # Resume conversation from checkpoint
   ```

8. **State Migration**:
   ```python
   def test_state_export_import():
       # Create in-memory states
       # Export to Redis
       # Clear in-memory
       # Import from Redis
       # Verify state integrity
   ```

### DEP: Dependencies
- **Phase 16 completion**: Stable state management and routing needed before Redis integration
- **Redis server installation**: Docker, WSL, or Windows binary
- **Python packages**: `redis>=6.4.0`, `langgraph-checkpoint-redis>=0.1.2`

### RISK: Risk Mitigation Strategies

#### 1. **Redis Dependency Risk**
**Risk**: Application becomes dependent on external Redis server
**Mitigation**:
- Make Redis **optional** with environment variable toggle
- Implement robust fallback to in-memory storage
- Health checks with automatic failover
- Clear documentation for Redis setup/troubleshooting

#### 2. **Serialization Bugs Risk**
**Risk**: Complex objects (deque, enums) may not serialize correctly
**Mitigation**:
- Custom JSON encoder/decoder with comprehensive type handling
- Round-trip serialization tests for all state field types
- Validation after deserialization
- Error logging for serialization failures

#### 3. **Connection Failure Risk**
**Risk**: Redis connection drops during conversation
**Mitigation**:
- Connection pooling with automatic reconnection
- Circuit breaker pattern for repeated failures
- Graceful degradation to in-memory mid-conversation
- Retry logic with exponential backoff

#### 4. **Performance Degradation Risk**
**Risk**: Redis network latency impacts response times
**Mitigation**:
- Local Redis deployment (same server/network)
- Connection pooling for reduced overhead
- Performance benchmarking (<2s requirement)
- Monitoring and alerting for slow operations

#### 5. **Data Loss Risk**
**Risk**: Redis memory-only storage loses data on crash
**Mitigation**:
- Configure Redis persistence (AOF or RDB)
- Appropriate TTL values (default 2 hours)
- Conversation state not critical (can restart conversation)
- Backup important data to primary database

### Implementation Sequence

1. **Setup Phase** (Day 1):
   - Install Redis server (Docker recommended)
   - Add environment variables
   - Test Redis connection

2. **Core Implementation** (Day 2-3):
   - Implement `RedisConfig` class
   - Create `StateEncoder`/`state_decoder`
   - Build `RedisStateStore` with interface compatibility

3. **Integration Phase** (Day 4):
   - LangGraph checkpoint integration
   - Failover logic implementation
   - State migration utilities

4. **Testing Phase** (Day 5-6):
   - Unit tests for serialization
   - Integration tests with Redis
   - Concurrency and load testing
   - Performance benchmarking

5. **Documentation Phase** (Day 7):
   - Redis setup guide
   - Configuration documentation
   - Troubleshooting guide
   - Migration procedures

### Success Metrics
- ✅ All tests passing (unit, integration, load)
- ✅ <2s response time maintained with Redis
- ✅ Graceful fallback verified
- ✅ 100 concurrent conversations handled
- ✅ State serialization 100% accurate
- ✅ Zero data loss in round-trip tests
- ✅ Documentation complete and clear

## Phase 19 – Advanced Scan Results & STL Security (HydroChat.md §19.2, §21)
D:
- Enhanced scan filtering: Date range, volume thresholds, scan status filters in `get_scan_results_node` per §19.2
- STL security: Temporary URL generation with expiration timestamps for secure downloads
- Download audit: Log all STL downloads with user, timestamp, scan ID for compliance per §21
- Batch operations: Multiple scan selection and bulk STL download confirmation workflows
- Search functionality: Scan result search by metadata, patient details beyond basic pagination
- Soft cap implementation: `SCAN_BUFFER_CAP` (e.g. 500) with `scan_buffer_truncated` state flag per §19.2
- Advanced pagination: Beyond current 10-item display limit with user-configurable page sizes
- Depth map enhancements: Conditional display only on explicit user request per §19
EC:
- Test: Date filter "scans from last month" correctly filters results with proper date parsing
- Test: Temporary STL URLs expire after configured time (default 1 hour) with proper 403/404 responses
- Test: Audit log captures all STL download attempts with proper metadata and PII masking
- Test: Scan buffer cap works correctly with truncation warnings to user
- Test: Batch STL confirmation handles multiple selections with proper confirmation workflows
- Security test: Expired STL URLs return appropriate error responses without leaking information
DEP: Phase 15 (finalize_response needed for consistent formatting)
RISK: URL generation complexity – use signed URLs with proper validation; Audit storage – implement log rotation; Buffer management – test memory usage with large scan sets.

## Phase 20 – Frontend Error Boundaries & Accessibility (HydroChat.md §31.17)
D:
- React Native Error Boundary: `ConversationErrorBoundary.js` component wrapping HydroChatScreen per §31.17
- Accessibility audit: WCAG 2.1 compliance verification for all HydroChat components per §31 requirements
- Screen reader support: Proper semantic markup, focus management, announcement handling for conversation flow
- Error recovery: User-friendly error messages with retry options, conversation state recovery mechanisms
- Offline handling: Graceful degradation when API unavailable with proper user messaging
- Frontend non-goals validation: Test boundaries per §31.17 (no streaming, no markdown rendering, no local intent guessing)
- Conversation refresh integration: Enhanced patient list refresh mechanism after agent CRUD operations
- Performance optimization: Lazy loading, memoization for large conversation histories
EC:
- Test: Error boundary catches and displays user-friendly error messages without crashing app
- Test: Screen reader navigation works properly through conversation flow with proper announcements
- Test: Offline state shows appropriate messaging and retry options with proper UX patterns
- Test: Frontend non-goals properly enforced (no local processing, no unsupported features)
- Accessibility audit: Automated testing with @testing-library/react-native-a11y achieving WCAG 2.1 AA compliance
- Test: Conversation state recovery works after app crashes or network failures
DEP: Phase 12 completion (frontend infrastructure established)
RISK: Accessibility complexity – focus on critical path first; Error boundary scope – avoid over-catching legitimate errors; Performance – test with large conversation histories.

---
## Testing Strategy Requirements

### Backend Testing (pytest)
**Location**: `backend/apps/hydrochat/tests/`
**Coverage Target**: Maintain >80% (currently 80.13%)

**Required Test Categories**:
1. **LLM Integration Tests** (Phase 14):
   - Mock Gemini API responses for intent classification with all 7 Intent enum values
   - Test API error handling and fallback behavior with rate limiting scenarios
   - Verify prompt construction matches §15 requirements and response parsing handles malformed JSON
   - Cost/usage tracking validation with API call metrics per §29
   - Test prompt injection prevention and input sanitization
   - Verify `gemini-2.5-flash` model specification compliance per §2

2. **Node Implementation Tests** (Phase 15):
   - Each new node function with mocked dependencies following §24 node inventory
   - Graph routing validation with all 16 nodes per §24.1 routing table
   - Conversation summary generation and context preservation per §27
   - Response finalization formatting consistency per §25 templates
   - Test `history_summary` state field integration with `recent_messages` deque
   - Validate all response templates match §25 specifications exactly

3. **Performance & Load Tests** (Phases 16-17):
   - **Response time benchmarking** with timing assertions (<2s per §2) using decorators
   - **Token counting accuracy** validation using official SDK `client.models.count_tokens()`
   - **Cost calculation tests** comparing estimated vs actual token usage from API responses
   - **Metrics retention policy** tests (1000-entry cap, 24h TTL, hourly cleanup)
   - **JSON export endpoint** validation for dashboard data structure
   - Concurrent conversation isolation (expand from current 10 to 50 threads)
   - Memory usage monitoring during extended conversations with leak detection
   - Metrics collection accuracy under load with proper retention policies
   - Graph routing performance with all 16 nodes under concurrent load
   - LLM API performance impact measurement and optimization
   - **SDK migration validation** comparing httpx baseline vs official SDK metrics

4. **State Management Tests** (Phase 18):
   - Redis state store round-trip serialization with complex objects (deque, enums, datetime)
   - Failover behavior when Redis unavailable with proper fallback mechanisms
   - State migration between storage backends with data integrity validation
   - Connection pooling and health checks under concurrent load
   - TTL and LRU eviction policies in Redis context matching in-memory behavior
   - Backward compatibility with existing ConversationStateStore interface

5. **Security & Compliance Tests** (Phase 19):
   - STL temporary URL generation and expiration with proper cryptographic signing
   - Audit logging completeness and PII masking per §21 requirements
   - Access control for download endpoints with proper authorization checks
   - Data retention policy enforcement with configurable cleanup schedules
   - Scan buffer cap testing with memory usage validation
   - Security boundary testing for expired URLs and unauthorized access

6. **Frontend Integration Tests** (Phase 20):
   - Error boundary component testing with various error scenarios
   - Accessibility compliance testing with WCAG 2.1 AA standards
   - Screen reader compatibility with proper semantic markup
   - Offline handling and network failure recovery
   - Frontend non-goals boundary testing per §31.17 (no streaming, no local processing)
   - Conversation state recovery after app crashes or network interruptions

**Test Execution**:
```powershell
# Full test suite with coverage
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest --cov=apps.hydrochat --cov-report=html --cov-report=term -v

# Individual phase testing
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase14_llm_integration.py -v
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase15_missing_nodes.py -v
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase16_routing_validation.py -v

# Performance benchmarking (Phase 17)
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase17_performance.py -v --benchmark
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase17_sdk_migration.py -v
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase17_metrics_retention.py -v

# Concurrency testing (50 threads)
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_concurrency_enhanced.py -v

# Security and compliance testing
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase19_security.py -v
```

### Frontend Testing (Jest)
**Location**: `frontend/src/__tests__/`
**Coverage Target**: Maintain current high coverage (91%+ for screens)

**Required Test Categories**:
1. **Error Boundary Tests** (Phase 20):
   - Component error catching and display with various error types
   - State recovery after errors with conversation continuity
   - User retry functionality with proper error context
   - Offline error handling with network failure simulation
   - Frontend non-goals boundary testing per §31.17

2. **Accessibility Tests** (Phase 20):
   - Screen reader compatibility with proper semantic markup
   - Focus management and navigation through conversation flow
   - WCAG 2.1 AA compliance validation with automated tools
   - Color contrast and text sizing for visual accessibility
   - Keyboard navigation support for motor accessibility

3. **Integration Tests** (Phases 14-19):
   - End-to-end conversation flows with new LLM features
   - Advanced scan result filtering and display with pagination
   - Enhanced error messaging and recovery workflows
   - Performance monitoring integration with metrics display
   - Conversation state persistence across app lifecycle events
   - Patient list refresh mechanism after agent CRUD operations

**Test Execution**:
```powershell
# Full frontend test suite with coverage
cd frontend; npx jest --coverage --watchAll=false

# Specific feature testing
cd frontend; npx jest src/__tests__/components/ConversationErrorBoundary.test.js
cd frontend; npx jest src/__tests__/accessibility/ --watchAll=false

# Integration testing for new features
cd frontend; npx jest src/__tests__/integration/phase14-20/ --watchAll=false

# Accessibility compliance testing
cd frontend; npx jest src/__tests__/accessibility/wcag-compliance.test.js

# Performance testing for large conversations
cd frontend; npx jest src/__tests__/performance/conversation-performance.test.js

# Optimized test scripts (to be created)
cd frontend/test; .\run-phase14-20-tests.ps1
```

---
## Cross-Phase Governance (Updated per HydroChat.md §30)
- Every new external behavior requires HydroChat.md update BEFORE code implementation per §30 change control
- LLM integration requires API key management documentation and cost tracking per §29
- New nodes must be added to routing map per §24.1 before implementation to prevent orphaned states
- Security features require penetration testing before deployment per §19.2 and §21 audit requirements
- Performance benchmarks must pass (<2s response time per §2) before phase advancement
- All 16 nodes from §24 must be implemented and validated before considering Phase 2.0 complete
- PII masking validation per §9 and §21 must be tested in every phase touching user data
- Cancellation handling per §28 must work correctly across all new conversation flows
- Response formatting must follow templates in §25 exactly to prevent user confusion

---
## Specification Cross-Reference Validation
**Critical HydroChat.md sections addressed in Phase 2.0**:
- §2: Technology Stack (Gemini integration) ✓ Phase 14
- §8: State Management Schema (`history_summary` field) ✓ Phase 15  
- §9: Security & Auth (PII masking) ✓ All phases
- §15: Intent Classification (LLM fallback) ✓ Phase 14
- §19.2: Advanced STL Features ✓ Phase 19
- §21: NRIC Validation & Masking ✓ All phases
- §22: Logging Taxonomy ✓ Phase 17
- §24: Graph Node Inventory (all 16 nodes) ✓ Phases 15-16
- §24.1: Routing Logic ✓ Phase 16
- §25: Response Formatting Templates ✓ Phase 15
- §26: Safeguards Against Hallucination ✓ Phases 14-16
- §27: History Summarization Strategy ✓ Phase 15
- §28: Cancellation Handling ✓ All phases
- §29: Metrics & Diagnostics ✓ Phase 17
- §30: Change Control Procedure ✓ Governance
- §31.17: Frontend Error Handling ✓ Phase 20

---
## Progress Tracking (Phases 14-20)
| Phase | Status | Notes |
|-------|--------|-------|
| 14 | **PARTIAL** ✅ | Gemini client implemented with SDK - LLM fallback classification functional, 28/28 tests passing |
| 15 | TODO | Missing nodes: ingest_user_message, summarize_history, finalize_response |
| 16 | TODO | Centralized routing map, graph validation, documentation |
| 17 | **PARTIAL** ✅ | **SDK Migration ✅**, Metrics Retention ✅, Export Endpoint ✅ — Still need: performance decorators, analytics tracking, alert thresholds |
| 18 | TODO | Redis state management option with fallback |
| 19 | **NEXT** 🎯 | Advanced scan features, STL security, audit logging |
| 20 | TODO | Frontend error boundaries, accessibility compliance |

**Legend**: ✅ Complete | 🎯 Next Priority | ⏳ In Progress

---
## Implementation Priority & Sequencing

**Current Status (as of 2025-10-19)**:
- ✅ Phase 14: **PARTIAL** - Gemini SDK integration complete, LLM fallback functional
- ✅ Phase 17: **PARTIAL** - SDK migration, metrics retention, export endpoint complete
- 🎯 **Next Target**: Phase 19 - Advanced scan features, STL security

**Remaining Critical Path**:
1. **Phase 15** (High Priority): Missing nodes complete the graph architecture
   - Required for: Full conversation flow, history summarization, response formatting
   - Blocks: Phase 16 routing validation
   
2. **Phase 16** (High Priority): Routing map provides maintainable structure
   - Required for: Graph validation, state transition safety
   - Blocks: Production deployment confidence

**Enhanced Features (Should Implement)**:
3. **Phase 19** 🎯 (NEXT): Advanced scan features for production readiness
   - STL security with temporary URLs
   - Download audit logging
   - Enhanced filtering and pagination
   - Can be implemented in parallel with Phase 15/16
   
4. **Phase 17** (Complete Remaining): Finish performance monitoring
   - Response time decorators
   - Alert thresholds
   - Analytics tracking
   
5. **Phase 20**: Frontend polish for user experience
   - Error boundaries
   - Accessibility compliance

**Optional Enhancements (May Implement)**:
6. **Phase 18**: Redis scaling for distributed deployment
   - Optional feature for production scaling
   - Can be deferred until needed

This roadmap addresses the critical gaps identified in Grok's analysis while maintaining the granular, anti-hallucination structure of the original phase.md format.
