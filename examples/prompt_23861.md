<!-- pr-triage-prompt schema v3 -->

# PR #23861 — [VCOPS-76551] - Stop collection in password management tests

**Repo:** vcf/mops  **SHA:** 2ec5116f78bb  **Jira:** VCOPS-76551
**Components:** Network Operations
**Packages:** com.vmware.vropsqa.test, com.vmware.vropsqa.test.util
**Jira summary:** [Flow Analytics - Port to ESM] Enhance combobox - support for nested options

## Retrieval keys (for the test-suite knowledge base)

- Components: Network Operations
- Packages: com.vmware.vropsqa.test, com.vmware.vropsqa.test.util
- Classes: AdapterMonitoringStopTest, AdapterUtils, MonitoringStateResponse, AdapterSummary
- Operations: AdapterMonitoringStopTest.testStopAdapterCollection, AdapterUtils.<init>, AdapterUtils.fetchAdapters, AdapterUtils.stopAdapterCollection, AdapterUtils.startAdapterCollection, MonitoringStateResponse.<init>, MonitoringStateResponse.isSuccess, AdapterUtils.putMonitoringState, AdapterUtils.resolveAdapterInstancesArray, AdapterUtils.truncate, AdapterUtils.createAdaptersListGet, AdapterUtils.createMonitoringStatePut, AdapterSummary.<init>, AdapterSummary.from, AdapterSummary.firstNonEmpty, AdapterSummary.textOrNull

### com.vmware.vropsqa.test

- `…/vropsqa/test/AdapterMonitoringStopTest.java` (added, +123/-0)
    - Classes: `AdapterMonitoringStopTest`
    - Functions: `AdapterMonitoringStopTest.testStopAdapterCollection`

### com.vmware.vropsqa.test.util

- `…/test/util/AdapterUtils.java` (added, +212/-0)
    - Classes: `AdapterUtils`, `MonitoringStateResponse`, `AdapterSummary`
    - Functions: `AdapterUtils.<init>`, `AdapterUtils.fetchAdapters`, `AdapterUtils.stopAdapterCollection`, `AdapterUtils.startAdapterCollection`, `MonitoringStateResponse.<init>`, `MonitoringStateResponse.isSuccess`, `AdapterUtils.putMonitoringState`, `AdapterUtils.resolveAdapterInstancesArray`, `AdapterUtils.truncate`, `AdapterUtils.createAdaptersListGet`, `AdapterUtils.createMonitoringStatePut`, `AdapterSummary.<init>`, `AdapterSummary.from`, `AdapterSummary.firstNonEmpty`, `AdapterSummary.textOrNull`

### VCFPasswordManagement

- `…/main/resources/VCFPasswordManagement-testng.xml` (modified, +8/-0)

<!-- ===== pr-triage-prompt BEGIN task footer (full) ===== -->

## Task for the agent

You have access to a knowledge base of test-suite documents. Each document has a top-level suite name, a `## Components` section, and a `## Test Coverage` section with per-case entries under `### testXxx` headers describing **Purpose**, **Key Operations**, and **API Endpoints**.

Using **only** the retrieved test-suite context, list which **test cases** are most likely to exercise the code changed above. Lean on the *Retrieval keys* section (components, packages, classes, operations) and the Jira components to match against suite `## Components` and per-case `**Key Operations**` / `**API Endpoints**` lines.

**Output format** — one line per case, exactly:

    <SuiteName> → <testCaseName> — <one-sentence justification citing a specific class, function, operation, or component from the changes above>

Rules:
- Do not invent test names. If nothing in the KB is relevant, reply exactly `none`.
- Prefer coverage: include every case that plausibly exercises any changed class or operation — do not stop at the single best match.
- Do not include setup/fixture cases unless they directly exercise the change.

<!-- ===== pr-triage-prompt END task footer ===== -->
