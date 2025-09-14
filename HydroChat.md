# HydroChat Technical Specification

## 1. Project Goal
HydroChat is a conversational administrative assistant for the HydroFast platform. It enables clinicians to perform routine patient administrative tasks (CRUD operations and retrieval of scan histories) using natural language instead of navigating the mobile UI. The assistant maps user intent deterministically to existing backend REST API endpoints—no direct DB access, no AI wound processing, no authentication flows. Reliability, schema compliance, and clarification/confirmation loops are mandatory to prevent erroneous data changes.

## 2. Technology Stack (Planned & Fixed for v1)
- Runtime Language: Python 3.x (same venv as Django backend)
- LLM Base Model: `gemini-2.5-flash` (API key: `GEMINI_API_KEY`) – chosen for speed; keep prompts lean; no reliance on very long context windows.
- Orchestration Framework: LangGraph (primary). LangChain only for reusable tool binding helpers if needed (avoid deep dependency coupling).
- Execution Mode: **Synchronous** (requests) – simpler integration; future async upgrade path reserved.
- HTTP Layer: Custom thin wrapper around `requests` with retry/backoff adapter; interface isolation allows mock swap.
- State & Memory: Explicit structured state object (see Section 8 Expanded) + rolling message window (last 5 turns) + summary string.
- Serialization / Validation: Pydantic models for tool IO contracts; strict NRIC regex validation before calls.
- Config: Environment + runtime override (Section 16) – environment is canonical, override for tests only.
- Logging: Human-readable bracketed taxonomy + optional JSON emitter later; no Personally Identifiable Information beyond masked NRIC.
- Testing: Real API integration tests + optional mock HTTP client (manual selection, no automatic fallback).
- Security: No local file access, no DB direct queries, only allowed REST endpoints.

## 3. Core Capabilities (Agent Tools)
1. create_patient – Create a new patient (requires: first_name, last_name, nric). Optional: date_of_birth, contact_no, details.
2. get_patient_details – Retrieve a patient by ID or via internal name resolution (see Section 14). If multiple matches, disambiguate.
3. update_patient – Full update (PUT) of patient fields by ID (may accept a name which is resolved to ID first). Must include required trio after merge.
4. delete_patient – Delete patient by ID (or resolved from name) with confirmation guard.
5. list_patients – List all patients visible to current user context (used for name resolution cache).
6. get_patient_scan_results – List scan or scan result objects for a given patient (ID or resolved name) – prefer `scan-results` endpoint for richer metadata when available.

Note: Scan creation and AI processing endpoints under `/api/ai-processing/` are explicitly out of scope.

## 4. Tool ↔ API Mapping
| Tool Name | User Intent Example | API Endpoint | HTTP Method | Backend Handler / Notes |
|-----------|---------------------|--------------|-------------|--------------------------|
| create_patient | "Add new patient John Doe NRIC S1234567A" | `/api/patients/` | POST | `PatientViewSet.create` – Requires first_name, last_name, nric |
| list_patients | "Show all patients" | `/api/patients/` | GET | `PatientViewSet.list` |
| get_patient_details | "Get patient 5" | `/api/patients/{id}/` | GET | `PatientViewSet.retrieve` |
| update_patient | "Update patient 5 contact 91234567" | `/api/patients/{id}/` | PUT | `PatientViewSet.update` – Send full object (fetch first if doing partial semantic update) |
| delete_patient | "Remove patient 5" | `/api/patients/{id}/` | DELETE | `PatientViewSet.destroy` – Confirmation required in dialogue |
| get_patient_scan_results | "Show scans for patient 5" | `/api/scans/?patient={id}` | GET | `ScanViewSet.list` filtered by patient; or `/api/scan-results/?patient={id}` for result objects |

## 5. Data Model References (Backend Ground Truth)
Patient (`backend/apps/patients/models.py`):
- Required: first_name (max 50), last_name (max 50), nric (unique, max 9)
- Optional: date_of_birth, contact_no, details
- System assigned: id, user (server side), implicit creation via `perform_create` will attach default user if anonymous.

Scan / ScanResult (read-only usage for HydroChat):
- Query scans filtered by `patient` query param for chronological history (descending by created_at).
- Results: Use `scan-results` if needing STL & depth metadata in one pass.
 - Serializer (key fields actually exposed to client): `id`, `scan_id`, `patient_name`, `patient_name_display`, `scan_date`, `stl_file`, `depth_map_8bit`, `depth_map_16bit`, `preview_image`, `volume_estimate`, `processing_metadata`, `file_sizes`, `created_at`, `updated_at`.
 - `preview_image` is the STL **rendered preview** (used for user-facing visual). `stl_file` is the 3D mesh to offer as download **after explicit user confirmation**.

## 6. Conversation Logic & Control Flow
### 6.1 Patient Creation
State machine steps:
1. Parse intent -> create_patient.
2. Extract candidate fields (first_name, last_name, nric, optional others).
3. If any required missing -> ask targeted question(s) only for missing fields.
4. Validate NRIC length (<=9 chars) before API call (light client-side guard; backend still authoritative).
5. Call POST. On 400 with field errors, surface messages verbatim and re-ask only invalid/missing fields.

### 6.2 Updates
Because backend uses PUT (no PATCH exposed), the tool must:
1. Fetch current representation (GET) if user provided only partial updates.
2. Merge user-specified fields over existing object.
3. Ensure required trio (first_name, last_name, nric) still present.
4. Submit full payload via PUT.

### 6.3 Deletion Confirmation
Deletion requires a two-step guard:
1. User intent recognized (delete/remove) – capture target patient id.
2. Agent asks: "Confirm deletion of patient <id or name>? (yes/no)".
3. Only on explicit affirmative (yes / confirm / proceed) call DELETE.
4. Negative or ambiguous -> abort and inform user.

### 6.4 Ambiguity Resolution
Examples:
- "Show results" with no patient reference -> ask "Which patient ID?".
- Multiple numeric tokens -> clarify which is patient id vs other numbers.
- Name-based reference ("John Doe's scans") – Initial version respond that ID is required unless a name→ID resolution enhancement is implemented later.

### 6.5 Error Handling Patterns
| HTTP Status | Typical Cause | Agent Response Strategy |
|-------------|---------------|--------------------------|
| 400 | Validation (missing nric, duplicate nric) | Present field errors; prompt for corrected value(s). |
| 404 | Patient id not found | Inform user; offer to list patients. |
| 403 | Permission restriction (future when auth enforced) | Inform user insufficient rights. |
| 500 | Server error | Apologize briefly; suggest retry or escalation. |

## 7. Tool Specifications (Structured I/O Contracts)
Pydantic-style definitions (for implementation reference):
```python
class PatientCreateInput(BaseModel):
    first_name: str
    last_name: str
    nric: str
    date_of_birth: date | None = None
    contact_no: str | None = None
    details: str | None = None

class PatientOutput(BaseModel):
    id: int
    first_name: str
    last_name: str
    nric: str
    date_of_birth: date | None
    contact_no: str | None
    details: str | None

class PatientUpdateInput(PatientCreateInput):
    id: int

class ScanResultListItem(BaseModel):
    id: int
    scan_id: int
    patient_name: str | None
    patient_name_display: str | None
    scan_date: datetime | None  # SerializerMethodField from scan.created_at
    stl_file: HttpUrl | None
    depth_map_8bit: HttpUrl | None
    depth_map_16bit: HttpUrl | None
    preview_image: HttpUrl | None
    volume_estimate: float | None
    processing_metadata: dict | None
    file_sizes: dict | None  # SerializerMethodField with file sizes in MB
    created_at: datetime
    updated_at: datetime
```
(Exact runtime implementation can adapt; keep alignment with backend serializer fields.)

## 8. State Management Schema (Expanded / Authoritative)
All keys MUST exist (initialize defaults) to avoid hallucination. Missing keys => implementation bug.

| Key | Type | Description | Init |
|-----|------|-------------|------|
| recent_messages | deque[Message] (maxlen=5) | Last 5 raw user/assistant/tool messages for prompt context | empty deque |
| history_summary | str | Abstractive summary of earlier turns (updated when >5 turns) | "" |
| intent | Enum | Classified intent (CREATE_PATIENT, UPDATE_PATIENT, DELETE_PATIENT, LIST_PATIENTS, GET_PATIENT_DETAILS, GET_SCAN_RESULTS, UNKNOWN) | UNKNOWN |
| pending_action | Enum| Action still in-progress awaiting data/confirmation | UNKNOWN |
| extracted_fields | dict | Raw parsed fields from user text (may be unvalidated) | {} |
| validated_fields | dict | Sanitized field values ready for tool payload | {} |
| pending_fields | set[str] | Required patient fields still missing (first_name,last_name,nric) | empty set |
| patient_cache | list[PatientOutput] | Cached patients (≤1000) for name resolution | [] |
| patient_cache_timestamp | datetime| Timestamp of cache refresh | epoch |
| disambiguation_options | list[dict] | When multiple name matches: [{id,name,nric_masked}] | [] |
| selected_patient_id | int|None | Resolved patient ID for current action | None |
| clarification_loop_count | int | # clarifications issued this user turn (cap=1) | 0 |
| confirmation_required | bool | True if waiting on yes/no for destructive or download | False |
| awaiting_confirmation_type | Enum | (DELETE, DOWNLOAD_STL, NONE) | NONE |
| last_patient_snapshot | dict| Original fetched patient json before update merge | {} |
| last_tool_request | dict| {method,url,payload,attempt} last executed tool call | {} |
| last_tool_response | dict| Truncated successful response body (masking applied) | {} |
| last_tool_error | dict| {status,body,retryable} on failure | {} or None |
| scan_results_buffer | list[ScanResultListItem] | Most recently fetched results (unpaginated full set) | [] |
| scan_pagination_offset | int | Current page offset for scan browsing | 0 |
| scan_display_limit | int | Max results to show per reply (fixed=10) | 10 |
| download_stage | Enum | NONE, PREVIEW_SHOWN, AWAITING_STL_CONFIRM, STL_LINKS_SENT | NONE |
| metrics | dict | {total_api_calls:int, retries:int, successful_ops:int, aborted_ops:int} | counters 0 |
| nric_policy | dict | {regex:"^[STFG]\\d{7}[A-Z]$", mask_style:"first+******+last2"} | constant |
| config_snapshot | dict | Copy of runtime config (auth token redacted) | {} |

Clarification guard: if `clarification_loop_count >=1` and still missing required fields, instruct user explicitly what is needed or allow `cancel`.

### 8.1 Enumerations (Authoritative Set)
Explicit Python `Enum` classes (conceptual spec; implement in code before graph construction). Using enums (instead of raw strings) reduces typo risk and constrains conditional routing.

```python
from enum import Enum, auto

class Intent(Enum):
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    LIST_PATIENTS = auto()
    GET_PATIENT_DETAILS = auto()
    GET_SCAN_RESULTS = auto()
    UNKNOWN = auto()

class PendingAction(Enum):
    NONE = auto()               # No multi-step action in progress
    CREATE_PATIENT = auto()
    UPDATE_PATIENT = auto()
    DELETE_PATIENT = auto()
    GET_SCAN_RESULTS = auto()

class ConfirmationType(Enum):
    NONE = auto()
    DELETE = auto()
    DOWNLOAD_STL = auto()

class DownloadStage(Enum):
    NONE = auto()               # No scan retrieval yet
    PREVIEW_SHOWN = auto()      # Stage 1 preview lines displayed (no STL links)
    AWAITING_STL_CONFIRM = auto() # Asked user if they want STL links
    STL_LINKS_SENT = auto()     # STL links (or placeholders) delivered
```

State values MUST use these enums (never ad‑hoc strings). When serializing logs or snapshots, use `enum.name`.

### 8.2 recent_messages Serialization Strategy
Runtime structure: an internal `deque(maxlen=5)` for O(1) append & automatic truncation.
Serialization boundary (logs, LLM prompt, checkpoint tests): convert to a plain list via `list(deque_instance)` to guarantee JSON compatibility and immutability of the emitted snapshot.
Deserialization (if later adopting persistence): reconstruct with `deque(restored_list, maxlen=5)`.
Benefit: deterministic ordering + small memory footprint + avoids accidental mutation of historical messages after snapshotting.

## 9. Security & Auth Assumptions
- Agent receives pre-configured auth token (e.g., Bearer) – not obtained interactively.
- All operations restricted to REST calls; no direct filesystem or DB operations.
- Do not expose raw tokens in responses/log echoes.
 - NRIC Masking: Display first char + 6 asterisks + last 2 chars (S******7A). Full NRIC only if user explicitly asks (“show full nric”) AND user originally supplied it.
 - Do not fabricate NRICs. If user omits NRIC in create flow, ask; never invent.

## 10. Out of Scope (Hard Boundaries)
- AI processing endpoints: `/api/ai-processing/*` and scan upload workflow (`/api/scans/upload_image/`).
- Authentication flows (login/logout/token refresh).
- File download orchestration and STL post-processing.
- Advanced fuzzy heuristics beyond simple exact / case-insensitive full-name matching (basic name→ID resolution now supported; no partial substring scoring, no phonetic algorithms in initial build).

## 11. Implementation Phasing (Recommended)
1. Define tool models & HTTP client wrapper with retry/backoff (idempotent GET/PUT/DELETE, non-retry POST by default unless network failure before response).
2. Build intent classifier (rule-based initial: keywords create/list/show/update/delete/scan(s)).
3. Implement state machine for required fields & confirmations.
4. Add error translation layer mapping backend serializer errors to user prompts.
5. Add regression test harness: simulated dialogues for each tool (happy path + validation error + delete cancel + ambiguous query).

## 12. Feasibility Confirmation
All required CRUD & listing functions are fully supported by existing endpoints (`patients`, `scans`, `scan-results`). No backend schema changes required. PUT-only update semantics necessitate pre-fetch & merge pattern (documented). Deletion & creation flows align with REST conventions already in place. Therefore HydroChat is feasible using only current REST API surface.

## 13. Future Enhancements (Document Only, Not for Initial Build)
- Add name→ID resolution cache by fetching list once and fuzzy matching.
- Introduce PATCH endpoint or partial update tool to reduce payload.
- Add tool for listing a single scan result’s file metadata directly.

## 14. Patient Name Resolution (Implemented Minimal Form)
Purpose: Allow user to reference patients by full name in natural language ("Show scans for Jason Wong").

Resolution Algorithm (internal helper, not exposed as a tool):
1. If user supplies explicit numeric ID, use directly (skip resolution).
2. Else ensure local cache of patients (invoke `list_patients` if cache empty or stale > N minutes – default 5).
3. Build candidate set with case-insensitive full-name match (`first_name + ' ' + last_name`).
4. If exactly one match → return that ID.
5. If zero matches → ask user to confirm creation (if intent was create) or offer to list patients; do not guess.
6. If multiple matches (e.g., duplicate names) → present indexed list with IDs, ask user to choose ID explicitly; do not auto-pick.

Constraints & Safeguards:
- No fuzzy partial similarity (Levenshtein, etc.) in v1 – reduces hallucination risk.
- Cache invalidated after create/delete or explicit user request ("refresh patients").
- On update/delete requests with ambiguous names, must obtain ID confirmation before performing action.

Example Dialogue (Delete Ambiguous Name):
User: Delete patient John Lee.
Agent: I found 2 patients named John Lee: (1) ID 12 – NRIC S1234567A, (2) ID 34 – NRIC T7654321B. Which ID should I delete?
User: 12.
Agent: Please confirm deletion of patient ID 12 (John Lee) – yes or no?
User: yes.
Agent: Patient ID 12 deleted successfully.

Error Handling Integration:
- If list fetch fails → inform user and retry once before abandoning name resolution.
- If patient list large (>1000) consider temporary warning about potential performance (future optimization placeholder).

## 15. Intent Classification & Field Extraction
Deterministic pre-LLM regex rules first. Patterns (case-insensitive):
- CREATE: /(create|add|new)\s+(patient)/
- UPDATE: /(update|change|modify|edit)\s+(patient|contact|nric|name|details)/
- DELETE: /(delete|remove|del)\s+(patient)/
- LIST_PATIENTS: /(list|show|all)\s+patients/
- GET_SCAN_RESULTS: /(show|list|get).*(scan|result)/
- GET_PATIENT_DETAILS: /(show|get).*(patient)/ when not matching scans.
If none match → fallback LLM classification with strict JSON schema {intent,reason}. UNKNOWN triggers clarifying prompt.

Field extraction order:
1. Deterministic regex for NRIC: ^[STFG]\d{7}[A-Z]$.
2. Name: look for pattern after verbs; try two consecutive capitalized tokens.
3. contact_no: digits & optional separators; normalize to digits or +country.
4. date_of_birth: must match YYYY-MM-DD else ask again specifying format.
5. details: any remaining descriptive tail after recognized tokens.

## 16. Config & Overrides
Config source precedence: ENV → optional runtime override (tests/dev only). Env vars: `HYDRO_BASE_URL`, `HYDRO_AUTH_TOKEN`, fallback to `BASE_URL`, `AUTH_TOKEN` if first absent. Structure:
```python
class HydroConfig(BaseModel):
        base_url: HttpUrl
        auth_token: str | None = None
        timeout_s: float = 10.0
        def override(self, **kwargs): ...  # disabled if not DEBUG
```
`get_config()` returns a snapshot dict with `auth_token` redacted to first 4 chars + '***'. Nodes must not mutate snapshot.

## 17. Tool Execution & Retry Policy
Allowed methods: GET, POST, PUT, DELETE. Retries (max 2) only for network errors or HTTP 502/503/504.
Backoff sequence: 0.5s then 1.0s. POST retried **only** if no server response (timeout/connection reset). No retry on 4xx. Metrics updated: `metrics.retries += 1` per retry attempt.
`last_tool_request` & `last_tool_response` always stored (with NRIC masked). If response body > 3KB, truncate to 512 chars and set `truncated=True` flag.

## 18. Update (PUT) Merge Algorithm
Steps:
1. GET patient (if operation=UPDATE and user supplied partial fields).
2. Copy server JSON → working dict.
3. Overlay each field from `validated_fields` that is not None.
4. Verify presence of first_name, last_name, nric.
5. Remove read-only fields (`id`, `user`) from outgoing body.
6. Send PUT. On 400 validation: parse errors, repopulate `pending_fields` from failing keys; re-prompt.

## 19. Scan Results Two-Stage Flow & Pagination
Stage 1 (Preview Mode):
- Fetch via `/api/scan-results/?patient={id}` (server orders by `-created_at` descending per ScanResultViewSet.get_queryset()).
- Store full list into `scan_results_buffer`.
- Slice first `scan_display_limit` (10) results.
- For each result line:
    - Preview image markdown if `preview_image` present: `![Scan {scan_id} Preview]({preview_image})`
    - Metadata: `Scan {scan_id} | Date: {scan_date.date() if scan_date else created_at.date()} | Volume: {volume_estimate or '—'} | STL: { 'Yes' if stl_file else 'No' }`
    - Do NOT include stl_file link yet.
- If more than 10 total: append summarizer line `(Showing 10 of {total}. Say 'show more scans' to display more.)` and set `scan_pagination_offset=10`.
- Set `download_stage=PREVIEW_SHOWN` and `awaiting_confirmation_type=DOWNLOAD_STL`; ask: "Would you like to download STL files for these scans? (yes/no)".

Stage 2 (STL Link Mode):
- Triggered only if user answers affirmative while `download_stage=PREVIEW_SHOWN`.
- Provide per-entry lines ONLY for those displayed so far (respect pagination) with a link placeholder: `Download STL (Scan {scan_id}): {stl_file}` else `(No STL available)`.
- Set `download_stage=STL_LINKS_SENT`, clear `awaiting_confirmation_type`.

Pagination Expansion:
- If user says "show more scans" and buffer length > current offset: show next 10 (respect STL link stage logic—if still pre-download ask again after new page).
- If no more: respond "No additional scans." Do not loop.

Depth Maps: Only list if user specifically requests ("show depth maps"). In that case augment each line with `Depth: 8-bit:{'Y' if depth_map_8bit else 'N'} 16-bit:{'Y' if depth_map_16bit else 'N'}`.

### 19.1 Node Split Justification (format_scan_previews vs provide_stl_links)
Two distinct nodes are mandated for clarity and security:
- `format_scan_previews` (Stage 1): Pure presentation of paginated metadata + preview images. It MUST NOT surface STL URLs. It is re-runnable for pagination expansions. It transitions download flow by setting `download_stage=PREVIEW_SHOWN` and (after user affirmative) to `DownloadStage.AWAITING_STL_CONFIRM`.
- `provide_stl_links` (Stage 2): Executes only after explicit affirmative confirmation. It emits STL URLs (or “No STL available”), updates `download_stage=STL_LINKS_SENT`, and clears any confirmation flags.
Benefits: (a) single responsibility, (b) simpler conditional branching, (c) unambiguous audit boundary before revealing file resources, (d) test isolation (preview formatting vs link disclosure), (e) future extensibility (adding depth map link stage) without merging concerns.

### 19.2 Soft Cap (Optional Future) — NOT enabled in v1
If patient scan histories become very large, introduce `SCAN_BUFFER_CAP` (e.g. 500). After fetch: if length > cap, keep the most recent `cap` entries and set `scan_buffer_truncated=True` in state (add key when implemented). v1 defers cap to keep implementation minimal; only instrumentation/logging of length is required initially.

## 20. Confirmation & Clarification Rules
Confirmation triggers: DELETE patient, STL download stage.
Accepted affirmatives: {"yes","y","confirm","proceed"}; negatives: {"no","n","cancel","abort"}.
Invalid response increments `clarification_loop_count`; after 1 invalid attempt, respond with explicit allowed options.

## 21. NRIC Validation & Masking
Regex: `^[STFG]\d{7}[A-Z]$` pre-check before any API call. If fails: ask user to re-enter NRIC in format hint: "Format ST1234567A". Masking rule: first char + 6 asterisks + last 2.
**Note**: This is agent-side validation only; backend enforces length (≤9) + uniqueness constraints but accepts broader formats. Agent policy is more restrictive than server requirements.
Never auto-generate NRIC. Duplicate NRIC 400 error handled by prompting for a different one.

## 22. Logging Taxonomy
Format: `[🤖HydroChat][CATEGORY] Message`
Categories:
- INTENT: Classified user request.
- MISSING: Required fields absent.
- AMBIGUOUS: Multiple name matches.
- CONFIRM: Awaiting yes/no.
- TOOL: Executing request.
- RETRY: Retry attempt.
- ERROR: Non-success outcome (HTTP >=400 or internal exception).
- SUCCESS: Completed action.
- PAGINATION: Serving additional scans.
Log Redaction: Replace auth token fully; mask NRIC; truncate large payloads.

## 23. Error Handling Mapping
| Scenario | Detection | State Update | User Feedback |
|----------|-----------|--------------|---------------|
| Validation 400 | status=400 & json keys | `pending_fields` from keys | Ask for specific field(s) again |
| Not Found 404 (patient) | status=404 | clear `selected_patient_id` | Offer list or re-specify ID |
| Not Found 404 (scans) | empty result list | none | Inform no scans available |
| Server Error 5xx | status>=500 after retries | set `last_tool_error` | Apology + suggest later retry |
| Network Timeout | exception | mark retryable | Retry or escalate if limit |
| Ambiguous Name | >1 match | populate `disambiguation_options` | Present options & stop |
| Clarification Exhausted | loop count >=1 & still missing | none | Explicit instruction or cancel suggestion |

## 24. Graph Node Inventory (Execution Order)
1. `ingest_user_message`
2. `classify_intent`
3. `extract_entities_and_fields`
4. `resolve_patient_reference`
5. `handle_ambiguity` (STOP if choices presented)
6. `collect_missing_fields` (STOP if still pending)
7. `confirmation_gate` (STOP if awaiting confirmation)
8. `prepare_tool_payload`
9. `execute_tool`
10. `handle_tool_error` (may STOP on validation or escalate)
11. `update_state_post_tool`
12. `fetch_scan_results` (intent=GET_SCAN_RESULTS)
13. `paginate_scan_results`
14. `format_scan_previews` (Stage 1) or `provide_stl_links` (Stage 2)
15. `summarize_history` (if >5 turns)
16. `finalize_response`

Each node strictly pure except for allowed side-effects: HTTP requests, logging, metrics increments. All transitions data-driven by state flags.

### 24.1 Routing Map (Conditional Return Tokens → Next Node)
This table is normative; implementation must ensure functions only return the listed tokens. Tokens are internal (not user-facing) and may be Enum members or string constants; prefer Enum where feasible.

| Conditional Node | Return Token | Next Node | Meaning |
|------------------|--------------|-----------|---------|
| handle_ambiguity | AMBIGUOUS_PRESENT | (STOP) | Options presented; wait for user selection |
| handle_ambiguity | RESOLVED | collect_missing_fields | Ambiguity resolved to a single patient |
| collect_missing_fields | NEED_MORE_FIELDS | (STOP) | Still awaiting required patient fields |
| collect_missing_fields | FIELDS_COMPLETE | confirmation_gate | All required fields gathered |
| confirmation_gate | AWAITING_CONFIRMATION | (STOP) | Waiting for yes/no from user |
| confirmation_gate | CONFIRMED | prepare_tool_payload | User affirmed destructive / sensitive action |
| confirmation_gate | REJECTED | finalize_response | User declined; action aborted |
| handle_tool_error | VALIDATION_ERROR | collect_missing_fields | 400 validation; request missing/invalid fields |
| handle_tool_error | RETRY_LATER | finalize_response | Non-retryable or user-aborted error |
| handle_tool_error | PROCEED | update_state_post_tool | No blocking error; continue |
| fetch_scan_results | NO_RESULTS | finalize_response | No scans found; respond immediately |
| fetch_scan_results | RESULTS_FOUND | paginate_scan_results | Proceed to pagination slice |
| paginate_scan_results | PAGE_READY | format_scan_previews | Provide current page previews |
| format_scan_previews | AWAITING_STL_CONFIRM | finalize_response | Asked user if they want STL links (Stage 1 end) |
| format_scan_previews | PAGINATION_CONTINUE | paginate_scan_results | User requested more pages (loop) |
| format_scan_previews | SKIP_STL | finalize_response | User declined STL download |
| provide_stl_links | STL_LINKS_SENT | finalize_response | Provided STL links (Stage 2 complete) |

STOP = execution pauses awaiting additional user input before resuming at next turn. Any token outside this table MUST raise a developer-visible error (fail fast to preserve determinism).

## 25. Response Formatting Templates
Patient Creation Success:
`Created patient #{id}: {first_name} {last_name} (NRIC {masked_nric}).`  Optional fields appended only if provided.
Patient Update Success:
`Updated patient #{id}: changed {field_list}.`
Deletion Success:
`Deleted patient #{id} ({name}).`
Scan Preview Header (if any):
`Scan Results for Patient #{patient_id}`
Scan Line Example:
`- Scan {scan_id} | Date {date} | Volume {vol or '—'} | STL {Yes/No}` + preview markdown previous line.
STL Download Line:
`Download STL (Scan {scan_id}): {stl_file_url}`
Validation Re-Ask:
`Need {missing_fields_comma}. Please provide.`

## 26. Safeguards Against Hallucination
- System prompt enumerates **only** allowed tools; instruct refusal for AI processing tasks.
- Pre-flight validation ensures path params + payload completeness before execute_tool runs.
- Strict masking & redaction rules enforced uniformly.
- Name resolution fails closed (no best-guess if 0 matches).
- Confirmation required for destructive or file disclosure (STL).

## 27. History Summarization Strategy
Trigger when total turn count >5: summarizer pass producing JSON { salient_patients:[ids], pending_action, unresolved_fields, last_result }. Merged into `history_summary`; older raw messages dropped (still accessible logically via summary). Summary not mutated by user content directly.

## 28. Cancellation Handling
User input matches cancellation set {"cancel","abort","stop"}: reset: pending_action, pending_fields, disambiguation_options, confirmation flags, download_stage → NONE. Reply: `Action cancelled. What would you like to do next?`

## 29. Metrics & Diagnostics
Command (developer-only): user says "show agent stats" → produce counts: total_api_calls, retries, successful_ops, aborted_ops, cached_patients, cache_age_sec. Not exposed to end-clinician by default.

## 30. Change Control Procedure
Any new tool requires: (1) spec table entry, (2) state impact note, (3) node insertion point revision, (4) tests, (5) log taxonomy extension, (6) dated delta appended below. Implementation MUST NOT precede spec update.

## 31. Frontend Integration (HydroChat UI Bridge)
Authoritative contract for embedding the conversational assistant inside the existing React Native app while preserving deterministic agent behavior and preventing UI-driven hallucination.

### 31.1 Entry Point & Navigation
- Add chatbot icon button to `PatientsListScreen` header (top-right) immediately to the right of the existing “+” button.
- Route name: `HydroChat`.
- Navigation: Stack push. Back action returns to Patients List; if agent performed CRUD (op flag in response), trigger patient list refresh (see 31.6).

### 31.2 Screen Visual Baseline
- Screen background: `#FCFFF8` (match other screens).
- Title: “Hydro” (color `#27CFA0`) + “Chat” (color `#0D6457`), Urbanist, weight 700, size 22.
- Layout: (1) Header, (2) Scrollable messages area, (3) Composer bar fixed at bottom (safe area aware).

### 31.3 Composer & Placeholder Behavior
- Composer container: horizontal row, padding 8, background transparent.
- TextInput:
    - Placeholder (initial proxy guidance) text color `#707070`, value: “Type your message here”.
    - When user starts typing (non-empty), any separate proxy helper message (31.4) disappears.
    - Background: `#EEEEEE`, borderRadius 13, minHeight 40, multiline growth up to ~120px before internal scroll.
- Send button:
    - Square or circular (min 44x44), background `#27CFA0`, centered icon (send.svg white fill/stroke).
    - Disabled while request in-flight (opacity 0.5).
    - On in-flight: replace icon with ActivityIndicator (white).

### 31.4 Initial Proxy Message (Ephemeral)
- Before first real user message, render a faint, dismiss-on-type proxy bubble at bottom above composer: text color `#707070`, background `#EEEEEE`, content e.g. “Try: ‘List patients’ or ‘Create patient Jane Tan NRIC S1234567A’”.
- Removed immediately once user types any non-whitespace character OR after first agent response.

### 31.5 Message Bubble Styling
Uniform bubble background per design directive.

| Role | Alignment | Background | Text Color | Style Details |
|------|-----------|------------|-----------|---------------|
| user | right | `#EEEEEE` | `#707070` | borderRadius 16 (optionally lesser radius 6 on bottom-right), maxWidth 78%, marginVertical 4 |
| assistant | left | `#EEEEEE` | `#707070` | borderRadius 16 (optionally lesser radius 6 on bottom-left), maxWidth 85%, marginVertical 4 |
| typing indicator | left | `#EEEEEE` | `#707070` italic | Replaced when final assistant content arrives |

No role-based color inversion to keep palette congruent with other screens.

### 31.6 Local Conversation State
```
{
    conversationId: string | null,
    messages: Array<{
         id: string;
         role: 'user' | 'assistant';
         content: string;
         pending?: boolean;     // true while awaiting server finalization (assistant only)
         error?: boolean;       // user message that failed send
    }>,
    sending: boolean,
    typing: boolean,          // assistant is “thinking”
    lastAgentOperation: { type: 'CREATE'|'UPDATE'|'DELETE'|'NONE'; patientId?: number } | null
}
```
- Set `typing=true` immediately after POST send accepted by fetch layer; render typing indicator bubble (31.7).
- On response: replace typing bubble with final assistant content; update `lastAgentOperation`.
- On navigation back: if `lastAgentOperation.type` in {CREATE, UPDATE, DELETE}, refresh patient list then reset to NONE.

### 31.7 Typing Indicator Behavior
- Visual: bubble with either animated three dots “•••” OR italic “Thinking…” (implementation choice; both acceptable).
- Animation: simple opacity pulse (750–1000ms loop) or translating dots; no dependency on heavy animation libs.
- Removal: when first assistant message arrives OR on error.
- Accessibility: `accessibilityLabel="Assistant is typing"`.

### 31.8 API Contract (Single Endpoint Facade)
POST `/api/hydrochat/converse/`
Request:
```
{
    "conversation_id": "<uuid|null>",
    "message": "<raw user text>"
}
```
Response 200:
```
{
    "conversation_id": "<uuid>",
    "messages": [
         {"role":"assistant","content":"<reply>"}
    ],
    "agent_state": {
         "intent": "CREATE_PATIENT|UPDATE_PATIENT|DELETE_PATIENT|LIST_PATIENTS|GET_PATIENT_DETAILS|GET_SCAN_RESULTS|UNKNOWN",
         "awaiting_confirmation": false,
         "missing_fields": []
    },
    "agent_op": "CREATE|UPDATE|DELETE|NONE"
}
```
Errors:
- 400: `{ "error": "validation", "detail": "<message>" }`
- 500: `{ "error": "server" }`
Timeout client-side: 15s; treat as network error.

No streaming v1. Only one assistant message returned per turn.

### 31.9 Client Request Policy
- While `sending=true`, ignore additional send attempts (no queue).
- Retry flow: if network/500, show inline small button “Retry” beneath failed user bubble; retry reuses same `conversation_id` and `message`.
- Do not attempt exponential retry automatically.

### 31.10 Determinism & Guardrails
- Frontend does not infer or guess intent; displays only server-provided text.
- No local patient CRUD actions performed outside chat.
- No attempt to unmask NRIC; display exactly as provided.

### 31.11 NRIC & Sensitive Text Handling
- Agent already masks NRIC; frontend performs no transformations.
- Copy action (long press) copies displayed (masked) value only.

### 31.12 Assets
To be added under `frontend/src/assets/icons/`:
- `Chatbot Icon.svg` (header button)
- `ChatArrow.svg` (composer send)
(Assets already exist; spec updated to reflect actual filenames.)

### 31.13 File Additions & Modifications
- New: `frontend/src/screens/hydrochat/HydroChatScreen.js`
- Update: `frontend/src/screens/index.js` export HydroChat screen.
- Update: navigation stack `frontend/src/components/navigation/index.js` to register route.
- Update: `PatientsListScreen.js` header to append chatbot icon button (`accessibilityLabel="Open HydroChat"`).
- Optional: `frontend/src/theme/constants.js` with:
```
export const Colors = {
    brandPrimary: '#27CFA0',
    brandSecondary: '#0D6457',
    canvas: '#FCFFF8',
    bubble: '#EEEEEE',
    textPrimary: '#707070'
};
export const FontSizes = { chatTitle: 22 };
```

### 31.14 Styling Tokens (Normative)
- Background screen: `Colors.canvas`
- Bubble background: `Colors.bubble`
- Primary text (all chat content & placeholder): `Colors.textPrimary`
- Title split colors: `brandPrimary` / `brandSecondary`
- Send button background: `brandPrimary`

### 31.15 Accessibility & Semantics
- Buttons include accessibility labels (“Send message”, “Open HydroChat”).
- Typing indicator has live region (if supported) or be re-announced on each state change with throttling.
- Contrast: #707070 on #EEEEEE acceptable for 14–16px; monitor feedback for potential darkening.

### 31.16 Testing Guidance (Frontend)
Minimum Jest / component tests:
1. Renders title with two colored segments.
2. Disables send during in-flight and shows typing indicator.
3. Replaces typing indicator upon response.
4. Triggers patient list refresh flag when `agent_op=CREATE`.

### 31.17 Non-Goals (Unchanged)
No streaming tokens, avatars, file attachments, markdown rich rendering, or offline queue v1.

### 31.18 Change Log Entry (Added Below)
2025-08-21: Added Section 31 defining frontend HydroChat integration (navigation entry, UI spec, unified bubble background, typing indicator, API facade `/api/hydrochat/converse/`, refresh hint propagation, theming tokens).

---
### Change Log (Append Only)
2025-08-18: Added Sections 15–30 detailing LangGraph implementation, state schema expansion, scan preview two-stage flow, NRIC masking, retry/backoff, logging taxonomy, safeguards.
2025-08-18: Added Enumerations (8.1), recent_messages serialization strategy (8.2), scan node split rationale (19.1), optional soft cap note (19.2), Routing Map (24.1) for deterministic branching, and explicit guidance on split nodes format_scan_previews vs provide_stl_links.
2025-08-21: Field mapping audit completed. Updated Section 7 ScanResultListItem with complete field set from ScanResultSerializer. Confirmed server ordering by `-created_at` in Section 19. Clarified NRIC validation scope in Section 21 (agent-enforced vs backend constraints).
2025-08-21: Added Section 31 Frontend Integration (HydroChat UI Bridge) and endpoint facade specification `/api/hydrochat/converse/`.

---
This document is the authoritative blueprint for implementing HydroChat. Any deviation (new endpoints, partial updates, name search) must append a dated change note here before coding.
