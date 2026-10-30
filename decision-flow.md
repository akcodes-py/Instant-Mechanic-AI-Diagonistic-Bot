# System Decision Flows

This document details the step-by-step decision trees and runtime flows that govern Instant Mechanic. It shows **how requests travel through the system**, **what checks are made**, and **how the fallback cascades operate**.

---

## 1. High-Level System Architecture Flow

```mermaid
flowchart TD
    User([User / Driver on Web Client]) -->|1. Starts anonymous session| Client[React 19 + TypeScript SPA]
    Client -->|2. HTTP API Request| Router[FastAPI Gateway]
    
    Router --> ChatRoute[POST /api/chat/]
    Router --> UploadRoute[POST /api/upload/]
    Router --> DiagRoute[POST /api/diagnosis/]
    Router --> BookRoute[POST /api/booking/]

    ChatRoute --> Triage[Tier 1: Deterministic Triage Rules]
    Triage -->|Vague / Unmatched Car Query| Groq[Tier 2: Groq Llama 3.3 70B]
    
    UploadRoute --> Preprocess[Albumentations CLAHE]
    Preprocess --> Vision[YOLO11n Warning Light Detector]
    
    DiagRoute --> Safety[Critical Safety Hazard Gate]
    Safety --> Conformal[NLP Classifier + Conformal Prediction]
    Conformal -->|Set Size > 2| GroqDiag[Groq Structured JSON Diagnosis]

    BookRoute --> DB[(SQLite DB via Async SQLAlchemy)]
```

---

## 2. Chat & Symptom Triage Flow (`POST /api/chat/`)

Every incoming message is passed through a deterministic-first filter before any external AI is considered:

```mermaid
flowchart TD
    Start([Incoming Chat Request]) --> Honeypot{Honeypot field 'website' empty?}
    Honeypot -- No --> RejectBot[400 Bad Request: Bot Detected]
    Honeypot -- Yes --> RateLimit{Rate Limit <= 30 req/min?}
    RateLimit -- Exceeded --> RejectRate[429 Too Many Requests]
    RateLimit -- OK --> Session[Get or Create Session + Deterministic Vehicle Extraction]
    
    Session --> RuleCheck{Matches Deterministic Rule?}
    RuleCheck -- "Greeting / Short (<3 words)" --> ReplyGreet[Return Deterministic Greeting / Prompt]
    RuleCheck -- "Non-car query" --> ReplyNonCar[Return 200 Reject: 'I only assist with cars']
    RuleCheck -- "Breakdown Match (Battery/Brakes/Tyre/...)" --> ReplyRule[Return Deterministic Safety & Service Action]
    
    RuleCheck -- No Direct Match --> CarCheck{Is Car Related?}
    CarCheck -- No --> ReplyReject[Return 200 Reject: 'Please describe your car issue']
    CarCheck -- Yes --> GroqCheck{Groq Configured & Words >= 3?}
    GroqCheck -- Yes --> CallGroq[Query Groq Llama 3.3 for Clarification]
    GroqCheck -- No / Groq Error --> FallbackReply[Return Deterministic Car Guidance Fallback]
    
    CallGroq -- Success --> ReturnAI[Return 200 with follow_up reply, ai_used=true]
    CallGroq -- Timeout/Fail --> FallbackReply
    FallbackReply --> ReturnDet[Return 200 with deterministic guidance, ai_used=false]
```

---

## 3. Media Upload & Warning Light Detection Flow (`POST /api/upload/`)

Media uploads follow a strict validation cascade and optional local YOLO inference:

```mermaid
flowchart TD
    Upload([Incoming Multipart File]) --> ExtCheck{Valid File Extension?}
    ExtCheck -- No --> Ext400[400: Unsupported Extension]
    ExtCheck -- Yes --> SizeCheck{Within Size Limit?<br>Img:10MB, Audio:15MB, Video:50MB}
    SizeCheck -- No --> Size400[400: File Too Large]
    SizeCheck -- Yes --> MagicCheck{Magic Bytes / Header Valid?}
    MagicCheck -- No --> Magic400[400: Corrupted or Mismatched Content]
    MagicCheck -- Yes --> SaveDisk[Save to MEDIA_ROOT with UUID Filename]

    SaveDisk --> KindCheck{Is Image & ML Inference Enabled?}
    KindCheck -- No / Audio / Video --> StoreDB[Persist in DB with 'analyzed=false']
    KindCheck -- Yes --> Albumentations[Albumentations CLAHE & Quality Check]
    
    Albumentations --> YOLO[Run YOLO11n Inference imgsz=960, conf=0.25]
    YOLO --> GateCheck{Class Confidence Check}
    GateCheck -- "Check Engine / ESP / Oil >= 0.50" --> ReliableLabel[Mark Detection as Reliable]
    GateCheck -- "Other 7 classes >= 0.40" --> ReliableLabel
    GateCheck -- Below Threshold --> DropDetection[Discard Detection]
    
    ReliableLabel --> UpdateHistory[Append Detected Warning Lights to Session History]
    UpdateHistory --> Response201[Return 201 Created with Vision Payload & Honest analyzed=true]
    DropDetection --> ResponseNoVision[Return 201 Created with analyzed=false]
```

---

## 4. Diagnosis & Uncertainty Routing Flow (`POST /api/diagnosis/`)

The diagnosis pipeline prioritizes passenger safety and uses conformal prediction sets to decide when to trust local ML versus escalating to an LLM:

```mermaid
flowchart TD
    DiagReq([POST /api/diagnosis/]) --> ValidateSession{Valid Session & User Messages?}
    ValidateSession -- No Messages --> Diag400[400: User message required]
    ValidateSession -- Only Greetings --> Diag422[422: Please describe your vehicle symptom]
    ValidateSession -- Valid --> SafetyKeywords{Critical Hazard Present?<br>Smoke, Fire, Burning Smell, Brake Failure}

    SafetyKeywords -- Yes --> ImmediateCritical[Force Urgency = CRITICAL<br>Do-Not-Drive Warning + Helpline]
    SafetyKeywords -- No --> Tier1Rule{Matches Rule Diagnosis?}
    
    Tier1Rule -- Yes --> UseRuleDiag[Construct Deterministic Rule Diagnosis, ai_used=false]
    Tier1Rule -- No --> MLCheck{ENABLE_ML_INFERENCE & NLP Model Available?}
    
    MLCheck -- Yes --> ConformalPred[Compute Conformal Prediction Set alpha=0.05]
    ConformalPred --> SetSizeCheck{Prediction Set Size}
    SetSizeCheck -- "Size == 1" --> SingleML[Use Deterministic ML Service Mapping]
    SetSizeCheck -- "Size == 2" --> MultiML[Use ML-Assisted Assessment with Multi-Causes]
    SetSizeCheck -- "Size > 2 (High Uncertainty)" --> EscalateLLM[Escalate Query to Groq]
    
    MLCheck -- No --> EscalateLLM
    EscalateLLM --> GroqCall{Groq Configured?}
    GroqCall -- Yes --> GroqJSON[Generate Structured JSON Diagnosis, ai_used=true]
    GroqCall -- No / Provider Error --> GenericFallback[Safe Generic Automotive Fallback, ai_used=false]
    
    UseRuleDiag --> SafetyCheckFinal
    SingleML --> SafetyCheckFinal
    MultiML --> SafetyCheckFinal
    GroqJSON --> SafetyCheckFinal
    GenericFallback --> SafetyCheckFinal
    ImmediateCritical --> SafetyCheckFinal[Final Safety Override Guarantee]

    SafetyCheckFinal --> Persist[Persist Diagnosis in DB]
    Persist --> ReturnDiag[Return 201 Created with Disclaimer & Honest ai_used flag]
```

---

## 5. Booking Flow (`POST /api/booking/`)

Booking operations are strictly deterministic and never depend on AI:

```mermaid
flowchart TD
    BookReq([Incoming Booking Payload]) --> FieldCheck{Required Fields Present?<br>Name, Mobile, Location, Service Type}
    FieldCheck -- Missing --> Book400[400: Missing Required Fields]
    FieldCheck -- Present --> ValidateData{Validate Formats}
    ValidateData -- "Name < 2 chars" --> Val400[400: Invalid Name]
    ValidateData -- "Invalid Indian Mobile [6-9]xxxxxxxxx" --> Val400
    ValidateData -- "Location < 5 chars" --> Val400
    ValidateData -- "Service Type Not in 7 Allowed" --> Val400
    
    ValidateData -- Valid --> DiagLink{Diagnosis ID Provided?}
    DiagLink -- Yes --> VerifyOwnership{Diagnosis belongs to this session?}
    VerifyOwnership -- No (Mismatch) --> Mismatch400[400: Diagnosis does not match session]
    VerifyOwnership -- Yes --> LinkDiag[Link Diagnosis to Booking]
    DiagLink -- No --> SkipLink[Standalone Booking]
    
    LinkDiag --> SaveBooking[Save to DB as 'pending']
    SkipLink --> SaveBooking
    SaveBooking --> Return201[Return 201 Created with Confirmation & Indian Helpline]
```

