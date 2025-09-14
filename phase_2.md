# HydroChat Phase 2.0 - Critical Implementation Gaps

Source Spec: `HydroChat.md` (authoritative). Based on Grok feedback analysis comparing phase.md implementation against original specification. Post-Phase 13 status: 80.13% coverage, 217 tests passing.

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
.\.venv-win\Scripts\Activate.ps1; cd backend; pytest apps/hydrochat/tests/test_phase16_routing_validation.py -v

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
| 14 | TODO | Gemini API integration - LLM fallback classification |
| 15 | TODO | Missing nodes: ingest_user_message, summarize_history, finalize_response |
| 16 | TODO | Centralized routing map, graph validation, documentation |
| 17 | TODO | Enhanced metrics, performance monitoring, analytics |
| 18 | TODO | Redis state management option with fallback |
| 19 | TODO | Advanced scan features, STL security, audit logging |
| 20 | TODO | Frontend error boundaries, accessibility compliance |

---
## Implementation Priority & Sequencing
**Critical Path (Must Implement)**:
1. Phase 14: LLM integration addresses core specification gap
2. Phase 15: Missing nodes complete the graph architecture
3. Phase 16: Routing map provides maintainable structure

**Enhanced Features (Should Implement)**:
4. Phase 17: Performance monitoring for production readiness
5. Phase 20: Frontend polish for user experience

**Optional Enhancements (May Implement)**:
6. Phase 18: Redis scaling for production deployment
7. Phase 19: Advanced features for power users

This roadmap addresses the critical gaps identified in Grok's analysis while maintaining the granular, anti-hallucination structure of the original phase.md format.
