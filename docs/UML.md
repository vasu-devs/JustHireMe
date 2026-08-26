# UML — JustHireMe

Structural and behavioural models. Diagrams are Mermaid, so they render in
GitHub and in the docs site without a separate toolchain.

---

## 1. Use case

```mermaid
flowchart LR
    C(["Candidate"])
    LLM(["LLM provider"])
    SRC(["Job sources"])

    subgraph System["JustHireMe"]
        U1(["Import profile"])
        U2(["Scan for jobs"])
        U3(["Review ranked leads"])
        U4(["Generate package"])
        U5(["Give feedback"])
        U6(["Track application"])
        U7(["Configure provider"])
        U8(["Erase all data"])
    end

    C --> U1 & U2 & U3 & U4 & U5 & U6 & U7 & U8
    U2 --> SRC
    U4 --> LLM
    U2 -.->|"«include» rank"| U3
```

---

## 2. Component diagram

```mermaid
flowchart TB
    subgraph Shell["Tauri shell (Rust)"]
        SUP["Sidecar supervisor"]
        TOK["Token + port state"]
        UPD["Updater · notifications"]
    end

    subgraph Web["Webview — React"]
        VIEWS["Feature views"]
        SVC["src/api — service layer"]
        WS["useWS"]
    end

    subgraph Side["Sidecar — FastAPI"]
        DEP["Composition root — api/dependencies"]
        MW["Middleware: TrustedHost · CORS · bearer"]
        R["Routers (one per feature)"]
        B["Business services + orchestrators<br/>leads · settings · templates · system<br/>discovery.orchestrator · generation.orchestrator · automation.ghost"]
        A["llm adapters"]
        D["Repository facade"]
    end

    subgraph Stores["Local stores"]
        SQL[("SQLite")]
        KUZ[("Kùzu")]
        LAN[("LanceDB")]
        FS[("Generated PDFs")]
    end

    SUP -->|spawn| Side
    TOK --> VIEWS
    VIEWS --> SVC --> MW --> R --> B --> D
    DEP -.->|injects services| R
    R --> D
    B --> A
    WS <-->|events| R
    D --> SQL & KUZ & LAN & FS
```

---

## 3. Class diagram — data access

```mermaid
classDiagram
    class Repository {
        +leads: LeadStore
        +settings: SettingsStore
        +profile: ProfileStore
        +graph: GraphStore
        +vector: VectorStore
        +feedback: FeedbackStore
        +resume_templates: TemplateStore
    }
    class LeadStore {
        +get_all_leads() list
        +get_lead_by_id(job_id) dict
        +save_lead(lead) None
        +update_lead_status(job_id, status) None
        +save_asset_package(job_id, resume, cover, projects, coverage) None
        +save_lead_feedback(job_id, feedback, note) dict
        +mark_applied(job_id) None
        +get_due_followups(limit, now) list
    }
    class ProfileStore {
        +get_profile() dict
        +load_profile_snapshot() dict
        +save_profile_snapshot(snapshot) None
        +purge_profile_deletion_tombstones() dict
    }
    class GraphStore {
        +graph_available() bool
        +graph_counts() dict
        +graph_snapshot() dict
        +sync_job_leads(leads) dict
        +sync_profile_relationships() dict
    }
    class VectorStore {
        +vec
        +search(query, k) list
    }

    Repository o-- LeadStore
    Repository o-- ProfileStore
    Repository o-- GraphStore
    Repository o-- VectorStore
```

## 3.1 Class diagram — ranking criteria

The criteria set is open for extension: a new criterion implements the base and
registers itself, and nothing else changes.

```mermaid
classDiagram
    class Criterion {
        <<abstract>>
        +key: str
        +weight: float
        +evaluate(lead, profile, ctx) CriterionResult
    }
    class CriterionResult {
        +score: float
        +evidence: list~str~
        +gaps: list~str~
    }
    class StackCoverage
    class RoleAlignment
    class SeniorityFit
    class Evidence
    class Logistics
    class LearningCurve
    class Registry {
        +register(criterion) None
        +all() list~Criterion~
    }

    Criterion <|-- StackCoverage
    Criterion <|-- RoleAlignment
    Criterion <|-- SeniorityFit
    Criterion <|-- Evidence
    Criterion <|-- Logistics
    Criterion <|-- LearningCurve
    Criterion ..> CriterionResult
    Registry o-- Criterion
```

---

## 4. Sequence — scan and rank

```mermaid
sequenceDiagram
    actor U as Candidate
    participant UI as React UI
    participant S as src/api/discovery
    participant R as discovery router
    participant D as discovery.service
    participant Q as quality_gate
    participant K as ranking.service
    participant DB as Repository
    participant WS as WebSocket

    U->>UI: Scan
    UI->>S: discoveryApi.scan(api)
    S->>R: POST /api/v1/scan
    R-->>S: 200 {status: started}
    S-->>UI: enable Stop

    R->>D: run scan (background task)
    loop each source
        D->>D: fetch + normalise
        D->>Q: gate(lead)
        alt accepted
            Q-->>D: ok
            D->>DB: save_lead
            D->>WS: LEAD_UPDATED
        else rejected
            Q-->>D: reason
        end
    end
    D->>K: score top-K via LLM, rest deterministic
    K->>DB: persist scores + provenance
    K->>WS: LEAD_UPDATED (scored)
    WS-->>UI: live updates
    D->>WS: scan_done
    WS-->>UI: re-enable Scan
```

## 4.1 Sequence — generate a package

```mermaid
sequenceDiagram
    participant UI as React UI
    participant S as src/api/generation
    participant R as generation router
    participant O as generation.orchestrator
    participant G as generation.service
    participant L as llm.client
    participant P as pdf_renderer
    participant DB as Repository
    participant WS as WebSocket

    UI->>S: generationApi.generate(api, jobId, templateId)
    S->>R: POST /api/v1/leads/{id}/generate
    R->>O: generate(job_id, notify, template_id)
    O->>DB: get_lead_by_id
    O->>O: lead_generation_blocker(lead)
    alt blocked
        O-->>R: raise UnprocessableError
        R-->>S: 422 (mapped by api.app)
    else ok
        O->>DB: status = tailoring
        O->>WS: LEAD_UPDATED
        O->>G: generate_with_contacts(lead, template)
        G->>L: prompt (cached context)
        L-->>G: content
        G->>P: render resume + cover letter
        P-->>G: file paths
        G-->>O: package
        O->>DB: save_asset_package
        alt save failed
            O->>WS: gen_error
            O-->>R: raise (lead reverted, never "ready")
            R-->>S: 503 transient / 500 permanent
        else saved
            O->>DB: status = approved
            O->>WS: gen_done + LEAD_UPDATED
            O-->>R: enriched lead
            R-->>S: 200 {lead}
        end
    end
```

---

## 5. State machine — lead lifecycle

```mermaid
stateDiagram-v2
    [*] --> discovered: scan / manual paste
    discovered --> tailoring: generate
    tailoring --> approved: package saved
    tailoring --> tailoring: transient failure (Retry-After)
    tailoring --> discovered: permanent failure
    approved --> applied: submitted
    applied --> interviewing: response
    interviewing --> offer
    interviewing --> rejected
    discovered --> discarded: quality gate / cleanup
    approved --> discarded: user discards
    offer --> [*]
    rejected --> [*]
    discarded --> [*]
```

## 5.1 State machine — sidecar lifecycle

```mermaid
stateDiagram-v2
    [*] --> reserving: shell starts
    reserving --> starting: port reserved, token minted
    starting --> alive: /health responds
    starting --> failed: spawn error
    alive --> degraded: a subsystem reports unavailable
    degraded --> alive: subsystem recovers
    alive --> stopping: POST /api/v1/shutdown
    degraded --> stopping
    stopping --> [*]: SIGTERM
    failed --> [*]
```

---

## 6. Entity relationships

```mermaid
erDiagram
    CANDIDATE ||--o{ SKILL : HAS_SKILL
    CANDIDATE ||--o{ PROJECT : BUILT
    CANDIDATE ||--o{ EXPERIENCE : WORKED_AS
    CANDIDATE ||--o{ EDUCATION : HAS_EDUCATION
    CANDIDATE ||--o{ CERTIFICATION : HAS_CERTIFICATION
    CANDIDATE ||--o{ ACHIEVEMENT : HAS_ACHIEVEMENT
    PROJECT   ||--o{ SKILL : PROJ_UTILIZES
    EXPERIENCE||--o{ SKILL : EXP_UTILIZES
    ACHIEVEMENT||--o{ SKILL : ACHIEVEMENT_USES
    PROJECT   ||--o{ EXPERIENCE : PROJECT_SUPPORTS_EXPERIENCE
    SKILL     ||--o{ SKILL : RELATED_SKILL
    JOBLEAD   ||--o{ SKILL : REQUIRES

    LEAD {
        text job_id PK
        text title
        text company
        text url
        text platform
        text status
        int  score
        text reason
        text match_points
        text asset_path
        text cover_letter_path
        text selected_projects
        text description
        text gaps
        int  resume_version
        text created_at
    }
    EVENT {
        int  id PK
        text job_id FK
        text action
        text ts
    }
    SETTING {
        text key PK
        text val
    }
    LEAD ||--o{ EVENT : logs
```

> The graph entities (upper half) live in Kùzu; `LEAD`, `EVENT` and `SETTING`
> live in SQLite. They are deliberately separate stores — see
> [LLD.md §3](LLD.md).

---

## 7. Deployment

```mermaid
flowchart TB
    subgraph Machine["User's machine"]
        subgraph App["JustHireMe.app / .exe"]
            Rust["Tauri shell process"]
            Webview["System webview<br/>(WebView2 / WKWebView / WebKitGTK)"]
            Py["jhm-sidecar (PyInstaller onefile)"]
        end
        subgraph AppData["App data directory"]
            F1[("crm.db — SQLite")]
            F2[("graph/ — Kùzu")]
            F3[("vectors/ — LanceDB")]
            F4[("assets/ — generated PDFs")]
        end
        Pack[("Runtime pack — OTA<br/>LanceDB · ONNX · Chromium")]
    end
    Ext["Job sources · LLM provider"]

    Rust --> Webview
    Rust -->|"spawn, loopback port"| Py
    Py --> F1 & F2 & F3 & F4
    Py -.->|optional| Pack
    Py -->|HTTPS| Ext
```

The installer stays slim: the heavy optional runtime (vector store, local
embedding model, browser) ships as an over-the-air **runtime pack** installed on
demand, not bundled into the installer.
