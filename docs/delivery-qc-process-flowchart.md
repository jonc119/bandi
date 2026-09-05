# Delivery QC Process Flowchart

```mermaid
flowchart TD
    A["Outlook delivery email arrives<br/>with updated ICS calendar"] --> B["Power Automate copies ICS attachment<br/>to protected intake folder"]

    B --> C["4:00 PM Delivery QC check<br/>for today's scheduled deliveries"]

    C --> D["Calendar parser extracts<br/>package name, project, delivery date,<br/>DL number, and expected containers"]

    D --> E{"Manufactured Stratus<br/>package or container?"}

    E -- "No" --> F["Exclude unrelated deliveries,<br/>pickups, tools, meetings, and transfers"]
    E -- "Yes" --> G["Read matching package and containers<br/>from Stratus using GET-only access"]

    G --> H["Deterministic comparison<br/>Calendar expectations vs. Stratus evidence"]

    H --> I{"Package matched<br/>unambiguously?"}
    I -- "No" --> J["INVESTIGATE<br/>Not found or ambiguous match"]
    I -- "Yes" --> K{"Container count<br/>matches calendar?"}

    K -- "No" --> L["INVESTIGATE<br/>Container-count mismatch"]
    K -- "Yes" --> M{"Are all expected containers<br/>Field Received?"}

    M -- "Yes" --> N["PASS<br/>Delivery statused correctly"]
    M -- "Some" --> O["INVESTIGATE<br/>Partial delivery"]
    M -- "None" --> P["INVESTIGATE<br/>Not Field Received"]
    M -- "Unknown status" --> Q["INVESTIGATE<br/>Status needs review"]

    J --> R["Generate QC report"]
    L --> R
    N --> R
    O --> R
    P --> R
    Q --> R
    F --> R

    R --> S["Responsive daily HTML dashboard<br/>grouped investigations + direct source links"]
    R --> T["Excel, JSON, CSV, and Markdown audit files"]
    R --> U["Follow-up email drafts<br/>not sent in shadow mode"]
    R --> AB["Historical dashboard<br/>date filters, sorting, and period totals"]

    S --> V["Read-only local dashboard viewer"]
    AB --> V
    T --> W["Hermes explains the latest results"]
    U --> W

    V --> X["Review locally<br/>or through an explicitly approved Tailscale route"]
    W --> X

    X --> Y{"Approved to go live?"}
    Y -- "No" --> Z["Remain in shadow mode<br/>No emails or production changes"]
    Y -- "Yes, later" --> AA["Enable approved notifications<br/>while keeping Stratus read-only"]
```

## Key Control

Hermes and Qwen orchestrate and explain the report, but deterministic code decides
`PASS` or `INVESTIGATE`. Stratus remains read-only, and the process does not delete
or modify company data.
