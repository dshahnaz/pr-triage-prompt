<!-- pr-triage-prompt schema v2 -->

# PR #23861 — [VCOPS-76551] - Stop collection in password management tests

**Repo:** vcf/mops   **SHA:** 2ec5116f78bba8e74e25711cb7e3066d14e50fd0   **Jira:** VCOPS-76551
**Components:** Network Operations
**Packages:** com.vmware.vropsqa.test, com.vmware.vropsqa.test.util

## Jira ticket

**Summary:** [Flow Analytics - Port to ESM] Enhance combobox - support for nested options

Found Styling inconsistencies found across the components used in the form, we need to address it fro consistent look and feel wrt to other pages in VCF OPS

 

- Dropdown, Select , Font inconsistency
- Select, Dropdown,  border, color inconsistency

_Components: Network Operations_

## PR description

## Change Description 
We want to run our password management tests with collection on adapters stopped. 

Adding a step at the begining of the test to stop collection on adapters before running the password management tests. 

We query for adapters of the following kind and then stop collection on these adapters : 

VcfAdapter
VMWARE
NSXTAdapter
VirtualAndPhysicalSANAdapter

These are the adapters found on starting state setup. 

Test is passing and stopping collection on adapters as expected 

https://uts-logs.lvn.broadcom.net/user-logs/mops-test/5672326/5fb0544e-6699-42eb-aeb6-f5bc89bc532c/test_driver_log.txt

`   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:109)  [] - ===== AdapterMonitoringStopTest summary =====
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:110)  [] - Stopped successfully (200): 4
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:112)  [] -   [STOPPED] VcfAdapter:3737a19d-ccf8-426b-a021-1c56b8e3ec85
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:112)  [] -   [STOPPED] NSXTAdapter:7f53a287-567a-4c32-b917-639476371b39
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:112)  [] -   [STOPPED] VirtualAndPhysicalSANAdapter:81479006-e89f-4ec1-a38b-5e47a522c437
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:112)  [] -   [STOPPED] VMWARE:67586384-809d-45e7-b4d6-b9ea3199f360
   [testng] 04-14@00:57:02 INFO  (AdapterMonitoringStopTest.java:121)  [] - ===== AdapterMonitoringStopTest completed =====`

## Changes — summary

| Module | Language | Files | Classes changed | Functions changed | +/- |
|---|---|---|---|---|---|
| com.vmware.vropsqa.test | Java | 1 | AdapterMonitoringStopTest | AdapterMonitoringStopTest.testStopAdapterCollection | +123/-0 |
| com.vmware.vropsqa.test.util | Java | 1 | AdapterUtils, MonitoringStateResponse, AdapterSummary | AdapterUtils.<init>, AdapterUtils.fetchAdapters, AdapterUtils.stopAdapterCollection, AdapterUtils.startAdapterCollection, MonitoringStateResponse.<init>, MonitoringStateResponse.isSuccess, AdapterUtils.putMonitoringState, AdapterUtils.resolveAdapterInstancesArray, AdapterUtils.truncate, AdapterUtils.createAdaptersListGet, AdapterUtils.createMonitoringStatePut, AdapterSummary.<init>, AdapterSummary.from, AdapterSummary.firstNonEmpty, AdapterSummary.textOrNull | +212/-0 |
| VCFPasswordManagement (`ops/tests/dev/VCFPasswordManagement`) | Other | 1 | — | — | +8/-0 |

## Retrieval keys (for the test-suite knowledge base)

- Components: Network Operations
- Packages: com.vmware.vropsqa.test, com.vmware.vropsqa.test.util
- Classes: AdapterMonitoringStopTest, AdapterUtils, MonitoringStateResponse, AdapterSummary
- Operations: AdapterMonitoringStopTest.testStopAdapterCollection, AdapterUtils.<init>, AdapterUtils.fetchAdapters, AdapterUtils.stopAdapterCollection, AdapterUtils.startAdapterCollection, MonitoringStateResponse.<init>, MonitoringStateResponse.isSuccess, AdapterUtils.putMonitoringState, AdapterUtils.resolveAdapterInstancesArray, AdapterUtils.truncate, AdapterUtils.createAdaptersListGet, AdapterUtils.createMonitoringStatePut, AdapterSummary.<init>, AdapterSummary.from, AdapterSummary.firstNonEmpty, AdapterSummary.textOrNull

### com.vmware.vropsqa.test

- `ops/tests/dev/VCFPasswordManagement/src/main/java/com/vmware/vropsqa/test/AdapterMonitoringStopTest.java` (added, +123/-0)
    - Package: `com.vmware.vropsqa.test`
    - Classes: `AdapterMonitoringStopTest`
    - Functions/methods: `AdapterMonitoringStopTest.testStopAdapterCollection`
    - Excerpt:
      `package com.vmware.vropsqa.test;`
      `import com.fasterxml.jackson.databind.JsonNode;`
      `import com.vmware.vropsqa.test.util.AdapterUtils;`
      `import com.vmware.vropsqa.test.util.AdapterUtils.AdapterSummary;`
      `import com.vmware.vropsqa.test.util.AdapterUtils.MonitoringStateResponse;`

### com.vmware.vropsqa.test.util

- `ops/tests/dev/VCFPasswordManagement/src/main/java/com/vmware/vropsqa/test/util/AdapterUtils.java` (added, +212/-0)
    - Package: `com.vmware.vropsqa.test.util`
    - Classes: `AdapterUtils`, `MonitoringStateResponse`, `AdapterSummary`
    - Functions/methods: `AdapterUtils.<init>`, `AdapterUtils.fetchAdapters`, `AdapterUtils.stopAdapterCollection`, `AdapterUtils.startAdapterCollection`, `MonitoringStateResponse.<init>`, `MonitoringStateResponse.isSuccess`, `AdapterUtils.putMonitoringState`, `AdapterUtils.resolveAdapterInstancesArray`, `AdapterUtils.truncate`, `AdapterUtils.createAdaptersListGet`, `AdapterUtils.createMonitoringStatePut`, `AdapterSummary.<init>`, `AdapterSummary.from`, `AdapterSummary.firstNonEmpty`, `AdapterSummary.textOrNull`
    - Excerpt:
      `package com.vmware.vropsqa.test.util;`
      `import com.fasterxml.jackson.databind.JsonNode;`
      `import com.fasterxml.jackson.databind.ObjectMapper;`
      `import org.apache.http.client.methods.CloseableHttpResponse;`
      `import org.apache.http.client.methods.HttpGet;`

### VCFPasswordManagement (`ops/tests/dev/VCFPasswordManagement`)

- `ops/tests/dev/VCFPasswordManagement/src/main/resources/VCFPasswordManagement-testng.xml` (modified, +8/-0)

## Task for the agent

You have access to a knowledge base of test-suite documents. Each document has a top-level suite name, a `## Components` section, and a `## Test Coverage` section with per-case entries under `### testXxx` headers describing **Purpose**, **Key Operations**, and **API Endpoints**.

Using **only** the retrieved test-suite context, list which **test cases** are most likely to exercise the code changed above. Lean on the *Retrieval keys* section (components, packages, classes, operations) and the Jira components to match against suite `## Components` and per-case `**Key Operations**` / `**API Endpoints**` lines.

**Output format** — one line per case, exactly:

    <SuiteName> → <testCaseName> — <one-sentence justification citing a specific class, function, operation, or component from the changes above>

Rules:
- Do not invent test names. If nothing in the KB is relevant, reply exactly `none`.
- Prefer coverage: include every case that plausibly exercises any changed class or operation — do not stop at the single best match.
- Do not include setup/fixture cases unless they directly exercise the change.
