# HydroChat Implementation Phases

**Status**: Canonical | **Last merged**: August 27, 2025 (phase_2.md consolidated)

**INVARIANT**: There is exactly one progress table in this document; statuses for Phases 14–22 are authoritative here; any other status mention is invalid. Phase 14 is DONE (Gemini API integration complete with 28 tests passing). Phase 15 is DONE (Missing Core Nodes implementation complete with 22 tests passing, all 289 total tests passing). Phase 16 is DONE (Centralized Routing Map & Frontend Message Retry implementation complete with 28 backend tests passing, 10 frontend tests passing, all 317 total tests passing - August 29, 2025: Backend test failures resolved, all HydroChat tests now passing).

Source Spec: `HydroChat.md` (authoritative). This `phase.md` acts as tactical roadmap / checklist. Any scope change: update `HydroChat.md` first, then adjust here.

Legend:
- D = Deliverables (artifacts produced)
- EC = Exit Criteria (verifiable conditions to advance)
- DEP = Dependencies (must be satisfied before starting)
- RISK = Key risks / mitigations

---
## Phase 0 – Repository & App Scaffolding
D:
- New Django app `backend/apps/hydrochat/` (no models; pure service layer)
- Enums (`intent`, `pending_action`, `confirmation`, `download_stage`) per spec
- Pydantic base models (config, patient/scan tool IO)
- Config loader (`HydroConfig`) with redaction
- Utility: NRIC masker/validator, timestamp helper
- Placeholder test file `test_hydrochat_smoke.py`
EC:
- `manage.py check` passes
- Importing enums/models causes no side effects
DEP: none
RISK: Namespace collisions – prefix internal helpers with `hydro_`.

## Phase 1 – HTTP Client & Retry Layer
D:
- `http_client.py` with: `request(method, path, *, json=None, params=None)`
- Retry policy (0.5s, 1.0s) for GET/PUT/DELETE + POST only on network failure pre-response (max 2 retries total)
- Metrics counters structure (in-memory)
- Masking application at logging boundary
EC:
- Unit tests simulate 502 then 200 -> single retry counted
- Auth header redacted in log captures
DEP: Phase 0
RISK: Over-retry POST – guard with response presence flag.

## Phase 2 – State Object & Serialization
D:
- `state.py` with full key set initialized exactly as spec (deque for recent_messages)
- Enum usage enforced; serialization method returning JSON-safe snapshot
- Cancellation reset method
EC:
- Test verifying all required keys exist & enums serialized by name
DEP: Phase 0
RISK: Missing key later causing hallucination – add assertion in constructor.

## Phase 3 – Intent Classification & Field Extraction
D:
- Rule-based classifier (regex library) per Section 15
- Field extractor for NRIC, name (two-token), DOB (YYYY-MM-DD), contact, details remainder
- Fallback stub for future LLM classification (returns UNKNOWN for now)
EC:
- Tests covering each intent phrase mapping
- Unknown phrase returns UNKNOWN
DEP: Phase 2
RISK: Regex over-match – keep anchored groups, unit tests for negatives.

## Phase 4 – Tool Layer (Patients & Scans)
D:
- Functions: `tool_create_patient`, `tool_list_patients`, `tool_get_patient`, `tool_update_patient`, `tool_delete_patient`, `tool_list_scan_results`
- Pydantic input/output validation
- NRIC masking inside response snapshot
EC:
- Tests hitting mocked endpoints (responses) verifying payload structure & masking
DEP: Phases 1,3
RISK: Divergence from backend serializer – add integration smoke later.

## Phase 5 – Name Resolution Cache
D:
- Cache refresh logic (age check 5 min)
- Exact full-name (case-insensitive) resolution algorithm
- Ambiguity list builder with masked NRICs
EC:
- Tests: unique match, none, multiple
DEP: Phase 4
RISK: Stale cache after create/delete – invalidate on successful ops.

## Phase 6 – Graph Construction (Core Flow: Create/List)
D:
- LangGraph (or structured orchestrator) nodes 1–12 subset to support: create patient (with missing field prompts) & list patients
- Logging taxonomy categories: INTENT, MISSING, TOOL, SUCCESS, ERROR
EC:
- Dialogue test: missing NRIC path prompts then success
- Dialogue test: list patients basic
DEP: Phases 2–5
RISK: Premature complexity – limit nodes to required subset first.

## Phase 7 – Full Node Inventory Completion
D:
- Implement remaining nodes (update, delete with confirmation, get details, scan results preview & pagination, STL confirmation)
- Routing token enforcement with assertion table
EC:
- Tests for: update merge, delete cancel vs confirm, scan preview (no STL leak), STL confirmation path
DEP: Phase 6
RISK: Token drift – central routing map constant used by tests.

## Phase 8 – Error Handling & Validation Loops
D:
- 400 validation parsing, repopulate `pending_fields`
- 404 patient not found path offering list option
- Clarification loop count guard
- Cancellation command handling
EC:
- Tests for duplicate NRIC (400) then correction
- Cancel mid-creation resets state
DEP: Phase 7
RISK: Infinite loops – enforce loop counter.

## Phase 9 – Scan Results Two-Stage & Pagination Enhancements
D:
- Stage 1 preview (no STL URLs) with offset tracking
- Stage 2 STL link reveal after affirmative
- Depth map augmentation only on explicit request
EC:
- Tests ensuring STL links absent before confirmation
- Pagination: show 20 results via two user “show more” commands
DEP: Phase 7
RISK: Race conditions between pages – ensure state offset atomic update.

## Phase 10 – Logging & Metrics Finalization
D:
- Structured log formatter + mask enforcement
- Agent stats command implementation
- Metrics increments for each tool call & retry
EC:
- Test: stats output after series of calls
DEP: Previous phases using logging placeholders
RISK: PII leakage – add test verifying raw NRIC absent.

## Phase 11 – Django Endpoint `/api/hydrochat/converse/`
D:
- DRF view (APIView) handling POST with conversation_id + message
- Stateless load or new state creation (in-memory store keyed by UUID)
- Response schema per spec (agent_op, intent, missing_fields, awaiting_confirmation)
- State TTL eviction strategy (simple LRU / timestamp sweep placeholder)
EC:
- Integration test hitting local patient endpoints (real DB) executing create + update
DEP: Phases 6–10
RISK: Memory leak – add max active conversations cap.

## Phase 12 – Frontend Screen Integration
D:
- `HydroChatScreen.js` with exact styling compliance (Hydro #27CFA0/Chat #0D6457 colors)
- Navigation registration & chatbot header button in Patients list using existing Chatbot Icon.svg
- Asset verification: ChatArrow.svg for send button (no new assets created)
- HydroChatService with comprehensive API integration & error handling
- Local conversation state mgmt (typing indicator, disabled send on in-flight, CRUD operation detection)
- Patient list refresh mechanism on agent CRUD operations (agent_op flag)
- Optimized test infrastructure with npx jest and organized test scripts in frontend/test/
EC:
- Jest tests: 28 total passing (title render with correct colors, disabled send states, typing indicator behavior, refresh flag functionality)
- Coverage: HydroChatScreen 91.35%, HydroChatService 100%
DEP: Phase 11
RISK: Asset path mismatches – add export test snapshot.

## Phase 13 – Extended Test Coverage & Hardening
D:
- Full conversation scenario tests (all intents)
- Concurrency test (simulated simultaneous conversations) for isolation
- Large scan results (simulate >25) pagination test
- Performance timing (ensure sub-threshold total latency excluding network)
EC:
- Coverage threshold (e.g., >80% agent package lines)
DEP: Phases 11–12
RISK: Flaky network dependent tests – use mock responses for non-critical paths.

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

## Phase 16 – Centralized Routing Map & Frontend Message Retry (HydroChat.md §24.1)
D:
- `routing_map.py` constant: Complete routing matrix per HydroChat.md §24.1 with all 16 nodes and conditional tokens
- Graph validation: State transition validation preventing invalid routes and hallucination per §26
- Route enforcement: Assertion checks in each node ensuring only valid next steps per routing table
- Documentation: Visual graph diagram showing all 16 nodes and connections with Mermaid/GraphViz
- Debug utilities: Graph state inspection, route tracing for debugging, state transition logging
- Token validation: Ensure only allowed tokens from §24.1 table are returned by conditional nodes
- **Routing tokens (SINGLE SOURCE)**: AMBIGUOUS_PRESENT, RESOLVED, NEED_MORE_FIELDS, FIELDS_COMPLETE, etc. per §24.1
- **Frontend Message Retry Implementation**: Critical healthcare workflow reliability feature per medical administrative requirements
- Retry functionality in `HydroChatScreen.js`: Implement `retryMessage(messageId)` function for failed message recovery
- Error state management: Clear error flags, set pending state, preserve original message content during retry
- Idempotency handling: Ensure retry operations don't create duplicate backend state or patient records
- User feedback: Loading indicators, success/failure notifications, retry attempt counting (max 3 retries)
- Network resilience: Handle intermittent connectivity issues common in medical facility environments
- Audit logging: Track retry attempts for medical record compliance and debugging diagnostics
EC:
- Test: Invalid state transition raises assertion error with clear diagnostic
- Test: All 16 nodes referenced in routing map with valid connections matching §24.1 table
- Test: Graph traversal validation catches orphaned nodes and unreachable states
- Test: Token validation prevents hallucinated routing decisions
- **Test (pytest): Message retry functionality preserves conversation state and doesn't duplicate backend operations**
- **Test (pytest): Retry button disabled after max attempts (3) with proper user messaging**
- **Test (pytest): Failed retry attempts are logged with messageId, timestamp, error reason for audit trail**
- **Test (pytest): Retry preserves exact original message content and conversation context**
- **Test (pytest): Idempotency - multiple retries of same message don't create duplicate patient records**
- **Test (Jest): RetryMessage component renders properly with loading states and error boundaries**
- **Test (Jest): Retry button UX - disabled during sending, proper visual feedback, accessibility labels**
- **Test (Jest): Network failure simulation - retry works after connectivity restored**
- Documentation: README section with complete graph visualization
- Test: Route enforcement catches developer errors in node implementations
DEP: Phase 15 (all nodes must exist before mapping)
RISK: Route explosion – keep map simple and data-driven; Maintenance burden – auto-generate validation from routing constants; Token drift – enforce token enum usage; **Retry complexity – implement idempotency checks to prevent duplicate medical records; Network timing – add proper timeout handling; User confusion – clear retry attempt indicators and max limit messaging**.

**NOTE**: All routing tokens and node inventory are defined authoritatively in this phase. Other phases reference these definitions rather than restating them.

## Phase 17 – Enhanced Metrics & Performance Monitoring (HydroChat.md §29, §22)
D:
- Extended `MetricsLogger`: LLM API call tracking, conversation flow timing, response latency monitoring
- Performance benchmarks: Sub-2-second response time enforcement per §2 synchronous mode (excluding network)
- Conversation analytics: Intent classification accuracy, user satisfaction indicators, error rate tracking
- Alert thresholds: Error rate >20% warnings, excessive retry detection, performance degradation alerts
- Dashboard data preparation: JSON export of metrics for external monitoring per §29
- Agent stats command: Developer-only access restrictions per §29 (not exposed to end-clinician)
- Logging taxonomy enhancement: Performance timing logs, LLM interaction logs per §22
- Metrics retention policy: Prevent metric storage explosion with configurable retention
EC:
- Test: Performance benchmark fails if response time >2s (mocked network delays)
- Test: LLM API metrics track successful/failed/retried calls with cost tracking
- Test: Conversation analytics export includes accuracy percentages and error rates
- Test: Agent stats command shows new metrics categories with proper access control
- Test: Alert thresholds trigger warnings at configured levels (error rate >20%)
- Integration: Stats command restricted to developer-only context per §29
DEP: Phases 14-15 (LLM integration needed for API metrics, all nodes needed for flow timing)
RISK: Metric storage explosion – implement retention policy; Performance overhead – batch metric updates; Alert fatigue – tune thresholds carefully.

## Phase 18 – Advanced State Management (Redis Option) (HydroChat.md §2 Future)
D:
- `redis_state_store.py`: Redis-backed conversation state persistence with same interface as ConversationStateStore
- Configuration toggle: `USE_REDIS_STATE=true/false` environment variable per §16 config pattern
- State serialization: Enhanced serialization handling complex objects (deque, enums, datetime) for Redis storage
- Connection management: Redis connection pooling, health checks, failover to in-memory per resilience patterns
- Migration utilities: State export/import between in-memory and Redis stores for deployment transitions
- TTL and LRU policies: Redis-native expiration and eviction aligned with in-memory behavior
- Backward compatibility: Same interface as existing ConversationStateStore for drop-in replacement
EC:
- Test: Redis store maintains same behavior as in-memory store for all operations
- Test: Graceful fallback to in-memory when Redis unavailable with proper logging
- Test: State serialization round-trip preserves all field types (deque maxlen, enum values, datetime)
- Test: Connection pooling handles multiple concurrent conversations efficiently
- Load test: 100 concurrent conversations with Redis backend maintaining <2s response times
- Test: TTL and LRU eviction policies work correctly in Redis context
DEP: Phase 16 completion (stable state management needed)
RISK: Redis dependency – make optional with clear fallback; Serialization bugs – comprehensive round-trip tests; Connection failures – implement circuit breaker pattern.

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

## Phase 21 – Documentation & Release Prep (Previously Phase 14)
D:
- Update `README.md` with HydroChat usage summary
- Append change log entry in `HydroChat.md` (dated)
- Add developer run guide snippet
- Final compliance checklist tying spec sections to implementation references
EC:
- Internal checklist passes with no open TODOs
DEP: All prior phases
RISK: Drift between spec & code – crosswalk table enforced.

## Phase 22 – Optional Post-GA (Deferred, Document Only) (Previously Phase 15)
D:
- Persistence layer for state (Redis) abstraction stub
- Soft cap for scan buffer + instrumentation
- Fuzzy name resolution placeholder feature flag
EC:
- Only documentation & feature flags (no active code unless toggled off by default)
DEP: GA (Phases 0–21)
RISK: Scope creep – keep behind disabled flags.

---
## Testing Strategy Requirements (Phases 14-22)

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

3. **Routing & Message Retry Tests** (Phase 16):
   - **Graph routing validation**: Complete routing matrix enforcement with state transition testing
   - **Message retry functionality**: Preserve conversation state, prevent duplicate backend operations
   - **Idempotency validation**: Ensure retried messages don't create duplicate patient records
   - **Network resilience**: Test retry behavior during intermittent connectivity scenarios
   - **Retry limits**: Validate max 3 retry attempts with proper user messaging and audit logging
   - **Error state management**: Test error flag clearing and pending state transitions during retry

4. **Performance & Load Tests** (Phases 17):
   - Response time benchmarking with timing assertions (<2s per §2)
   - Concurrent conversation isolation (expand from current 10 to 50 threads)
   - Memory usage monitoring during extended conversations with leak detection
   - Metrics collection accuracy under load with proper retention policies
   - Graph routing performance with all 16 nodes under concurrent load
   - LLM API performance impact measurement and optimization

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
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase16_routing_retry.py -v

# Performance benchmarking
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase17_performance.py -v --benchmark

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
   - **Message retry integration**: Test retry functionality with backend API calls preserving healthcare workflow continuity
   - **Healthcare workflow validation**: Ensure retry preserves patient CRUD operations without duplication
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
- Tests accompany feature introduction same phase (no deferred test debt)
- Masking & logging guard tests should run early (Phase 6 onward) to catch regressions

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
## Implementation Priority & Sequencing
**Critical Path (Must Implement)**:
1. Phase 14: LLM integration addresses core specification gap ✅ DONE
2. Phase 15: Missing nodes complete the graph architecture
3. Phase 16: Routing map provides maintainable structure

**Enhanced Features (Should Implement)**:
4. Phase 17: Performance monitoring for production readiness
5. Phase 20: Frontend polish for user experience

**Optional Enhancements (May Implement)**:
6. Phase 18: Redis scaling for production deployment
7. Phase 19: Advanced features for power users



## Advancement Gate (Per Phase)
Move only when EC validated (automated test or explicit checklist). If blocked: annotate RISK & mitigation plan before proceeding.

---
## Quick Start (Upcoming Implementation Order)
1. Implement Phase 0 & 1 in a single branch (foundation) → run initial tests
2. Layer Phase 2–4 (state + tools) → integration mock tests
3. Introduce graph (Phase 6) minimal features
4. Expand features (Phases 7–9) with incremental tests
5. Finalize backend endpoint (Phase 11) before frontend work
6. Frontend integration (Phase 12)
7. Hardening + docs (13–14)

This roadmap is intentionally granular to reduce hallucination risk and provide objective advancement gates. Update statuses as work completes.

---
## Phase Progress Tracking (CANONICAL - Single Source of Truth)

| Phase | Focus | Status | Critical Path | Implementation Notes |
|-------|-------|---------|--------------|---------------------|
| 0 | Project Infrastructure & CRUD Foundation | ✅ DONE | Yes | App scaffolding, enums, config, utils complete |
| 1 | LangGraph Conversation State | ✅ DONE | Yes | HTTP client with retry/backoff + masking complete |
| 2 | Intent Classification + Routing | ✅ DONE | Yes | State object with serialization + cancellation complete |
| 3 | Agent Configuration & PII Masking | ✅ DONE | Yes | Regex classifier + field extractor + LLM stub complete |
| 4 | Patient Name Resolution | ✅ DONE | Yes | Tool layer with Pydantic validation + NRIC masking complete |
| 5 | Patient Field Validation | ✅ DONE | Yes | Name resolution cache with TTL + ambiguity handling complete |
| 6 | Patient Creation Core | ✅ DONE | Yes | LangGraph orchestrator with 5 core nodes + logging complete |
| 7 | Ambiguity Resolution | ✅ DONE | Yes | Full node inventory: update/delete/details/scans complete |
| 8 | Field Update Engine | ✅ DONE | Yes | Error handling + validation loops + cancellation complete |
| 9 | Patient Deletion | ✅ DONE | Yes | Two-stage STL + pagination + depth maps complete |
| 10 | Scan Results Query | ✅ DONE | Yes | Structured logging + metrics + agent stats complete |
| 11 | Frontend Integration + Error Handling | ✅ DONE | Yes | Django API endpoint + state store + TTL/LRU complete |
| 12 | Final Backend Polish & Edge Cases | ✅ DONE | Yes | React Native screen + service + navigation complete |
| 13 | QA Checklist & Validation | ✅ DONE | Yes | Coverage 80.13% + scenarios + concurrency complete |
| 14 | Gemini API Integration & LLM Fallback | ✅ DONE | Yes | **GeminiClient + LLM fallback + 28 tests passing** |
| 15 | Missing Core Nodes Implementation | ✅ DONE | Yes | **ingest_user_message + summarize_history + finalize_response complete** |
| 16 | Centralized Routing Map & Frontend Message Retry | 📋 TODO | Yes | Complete routing matrix + graph validation + retry functionality |
| 17 | Enhanced Metrics & Performance Monitoring | 📋 TODO | Yes | Extended metrics + performance benchmarks + analytics |
| 18 | Advanced State Management (Redis Option) | 📋 TODO | No | Redis-backed state persistence with fallback |
| 19 | Advanced Scan Results & STL Security | 📋 TODO | No | Enhanced filtering + temporary URLs + audit logging |
| 20 | Frontend Error Boundaries & Accessibility | 📋 TODO | No | Error boundaries + WCAG 2.1 + screen reader support |
| 21 | Documentation & Release Prep | 📋 TODO | Yes | README updates + changelog + compliance checklist |
| 22 | Optional Post-GA (Deferred) | 📋 DEFERRED | No | Redis stubs + soft caps + fuzzy resolution flags |

**Legend:** ✅ DONE = Completed with all tests passing | 📋 TODO = Planned implementation | 📋 DEFERRED = Post-GA features

**Test Status**: 289 total tests, 289 passing (100% success rate), coverage maintained
