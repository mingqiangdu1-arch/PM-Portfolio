# ER 图

> 文档状态：当前有效
> 设计版本：V1.0
> 建立日期：2026-07-29
> 确认日期：2026-07-29
> 说明：Mermaid 图用于冻结关系和基数；字段、约束与索引以《数据字典》《数据库详细设计》为准

## 1. 总体 ER

```mermaid
erDiagram
    USER_ACCOUNT ||--o{ USER_SESSION : owns
    USER_ACCOUNT ||--o{ PROJECT_MEMBER : joins
    PROJECT ||--o{ PROJECT_MEMBER : authorizes
    USER_ACCOUNT ||--o{ PROJECT : creates
    PROJECT ||--o{ PROJECT_VERSION : contains
    PROJECT ||--|| PROJECT_CONTEXT : remembers
    PROJECT_VERSION ||--o{ VERSION_CHANGE_RECORD : receives
    PROJECT_VERSION ||--o{ REQUIREMENT : contains
    PROJECT_VERSION ||--o{ PRD : contains
    PROJECT_VERSION ||--o{ DESIGN_REVIEW : reviews
    PROJECT_VERSION ||--o{ IMPLEMENTATION_PLAN : plans
    PROJECT_VERSION ||--o{ ISSUE : owns

    REQUIREMENT ||--o{ REQUIREMENT_VERSION : versions
    PRD ||--o{ PRD_VERSION : versions
    PRD ||--o{ FLOW_DECISION : decides
    PRD ||--o{ FLOW : describes
    FLOW ||--o{ FLOW_VERSION : versions
    FLOW_VERSION ||--o{ FLOW_EXPORT : derives

    DESIGN_REVIEW ||--o{ DESIGN_REVIEW_SCOPE : freezes
    DESIGN_REVIEW ||--o{ REVIEW_FEEDBACK : contains
    REVIEW_FEEDBACK ||--o{ REVIEW_FEEDBACK_DISPOSITION : resolves
    IMPLEMENTATION_PLAN ||--o{ IMPLEMENTATION_PLAN_VERSION : versions
    IMPLEMENTATION_PLAN ||--o{ CONFIRMATION_ROUND : confirms
    CONFIRMATION_ROUND ||--o{ CONFIRMATION_MATERIAL : references
    CONFIRMATION_ROUND ||--o{ DIFFERENCE_RECORD : records
    CONFIRMATION_ROUND ||--o{ READINESS_CHECK_RESULT : checks
    CONFIRMATION_ROUND ||--o{ TEST_RECORD : validates
    TEST_RECORD ||--o{ TEST_EVIDENCE : proves
    TEST_RECORD o|--o{ ISSUE : originates
    ISSUE ||--o| BUG_DETAIL : extends
    ISSUE ||--o| OPTIMIZATION_DETAIL : extends
    ISSUE ||--o{ ISSUE_DISPOSITION : decides

    STORED_FILE ||--o{ FILE_VERSION : versions
    FILE_VERSION ||--o{ FILE_RELATION : links
    FILE_VERSION ||--o{ FILE_PARSE_RESULT : parses

    AI_TASK ||--o{ AI_CALL : invokes
    AI_CALL ||--o{ AI_CONTEXT_USAGE : uses
    AI_CALL ||--o{ AI_RESULT : returns
    AI_RESULT ||--o{ AI_EVALUATION : evaluates
    AI_RESULT ||--o{ AI_ADOPTION : concludes

    BEHAVIOR_EVENT ||--o{ EVENT_COMPENSATION : corrects
    METRIC_DEFINITION ||--o{ METRIC_SNAPSHOT : calculates
    OPTIMIZATION_EVALUATION ||--o{ OPTIMIZATION_METRIC_RESULT : compares
```

## 2. 业务主链 ER

```mermaid
erDiagram
    PROJECT {
        BIGINT id PK
        BIGINT owner_user_id FK
        VARCHAR status
        VARCHAR last_module
        DATETIME archived_at
    }
    PROJECT_VERSION {
        BIGINT id PK
        BIGINT project_id FK
        BIGINT parent_version_id FK
        VARCHAR version_no
        VARCHAR lifecycle_status
        VARCHAR workflow_node
        BOOLEAN is_working
    }
    REQUIREMENT {
        BIGINT id PK
        BIGINT project_version_id FK
        VARCHAR status
    }
    REQUIREMENT_VERSION {
        BIGINT id PK
        BIGINT requirement_id FK
        VARCHAR version_no
        BOOLEAN is_effective
        CHAR content_hash
    }
    PRD {
        BIGINT id PK
        BIGINT project_version_id FK
        VARCHAR prd_type
        BOOLEAN is_main
    }
    PRD_VERSION {
        BIGINT id PK
        BIGINT prd_id FK
        VARCHAR version_no
        BOOLEAN is_effective
        BIGINT ai_result_id FK
    }
    FLOW {
        BIGINT id PK
        BIGINT prd_id FK
        BIGINT parent_flow_id FK
        VARCHAR flow_scope
    }
    FLOW_VERSION {
        BIGINT id PK
        BIGINT flow_id FK
        VARCHAR version_no
        BIGINT drawio_file_version_id FK
        VARCHAR validation_status
    }
    DESIGN_REVIEW {
        BIGINT id PK
        BIGINT project_version_id FK
        VARCHAR status
    }
    IMPLEMENTATION_PLAN {
        BIGINT id PK
        BIGINT project_version_id FK
        VARCHAR status
    }
    CONFIRMATION_ROUND {
        BIGINT id PK
        BIGINT implementation_plan_id FK
        INT round_no
        BOOLEAN is_effective
        VARCHAR confirm_status
    }
    TEST_RECORD {
        BIGINT id PK
        BIGINT confirmation_round_id FK
        BIGINT supersedes_test_record_id FK
        VARCHAR result_status
        DATETIME submitted_at
    }
    ISSUE {
        BIGINT id PK
        BIGINT project_version_id FK
        BIGINT test_record_id FK
        VARCHAR issue_type
        VARCHAR status
    }
    ISSUE_DISPOSITION {
        BIGINT id PK
        BIGINT issue_id FK
        VARCHAR disposition_type
        BIGINT target_project_version_id FK
        DATETIME decided_at
    }

    PROJECT ||--o{ PROJECT_VERSION : contains
    PROJECT_VERSION ||--o{ REQUIREMENT : contains
    REQUIREMENT ||--o{ REQUIREMENT_VERSION : versions
    PROJECT_VERSION ||--o{ PRD : contains
    PRD ||--o{ PRD_VERSION : versions
    PRD ||--o{ FLOW : optionally_has
    FLOW ||--o{ FLOW_VERSION : versions
    PROJECT_VERSION ||--o{ DESIGN_REVIEW : reviews
    PROJECT_VERSION ||--o{ IMPLEMENTATION_PLAN : plans
    IMPLEMENTATION_PLAN ||--o{ CONFIRMATION_ROUND : confirms
    CONFIRMATION_ROUND ||--o{ TEST_RECORD : validates
    PROJECT_VERSION ||--o{ ISSUE : owns
    TEST_RECORD o|--o{ ISSUE : originates
    ISSUE ||--o{ ISSUE_DISPOSITION : decides
    PROJECT_VERSION o|--o{ ISSUE_DISPOSITION : target_version
```

业务基数规则：

- Project 1:N Project Version；同一 Project 只有一个 `is_working=1`。
- PRD 直接属于 Project Version；Flow 直接属于 PRD。
- Implementation Plan 1:N Confirmation Round；同一 Plan 只有一个有效轮次。
- Test Record 直接属于 Confirmation Round。
- Issue 必须属于 Project Version，`test_record_id` 可空。

## 3. AI 追溯 ER

```mermaid
erDiagram
    SKILL ||--o{ SKILL_VERSION : versions
    SKILL_VERSION ||--o{ PROMPT : supports
    PROMPT ||--o{ PROMPT_VERSION : versions
    TEMPLATE ||--o{ TEMPLATE_VERSION : versions
    SKILL_VERSION ||--o{ CONTEXT_STRATEGY : supports
    CONTEXT_STRATEGY ||--o{ CONTEXT_STRATEGY_VERSION : versions
    MODEL_CATALOG ||--o{ PROVIDER_PROFILE : configures

    AI_TASK ||--o{ AI_CALL : retries
    PROVIDER_PROFILE ||--o{ AI_CALL : executes
    SKILL_VERSION ||--o{ AI_CALL : applies
    PROMPT_VERSION ||--o{ AI_CALL : prompts
    TEMPLATE_VERSION o|--o{ AI_CALL : formats
    CONTEXT_STRATEGY_VERSION ||--o{ AI_CALL : selects_context
    AI_CALL ||--o{ AI_CONTEXT_USAGE : records
    AI_CALL ||--o{ AI_RESULT : produces
    AI_RESULT ||--o{ AI_EVALUATION : evaluates
    AI_RESULT ||--o{ AI_ADOPTION : reviews
    AI_RESULT o|--o{ REQUIREMENT_VERSION : formalizes
    AI_RESULT o|--o{ PRD_VERSION : formalizes
    AI_RESULT o|--o{ IMPLEMENTATION_PLAN_VERSION : formalizes
```

```mermaid
flowchart LR
    T["AI Task：一次用户意图"] --> C1["AI Call #1：失败"]
    T --> C2["AI Call #2：成功"]
    C1 --> X1["Context Usage 快照"]
    C2 --> X2["Context Usage 快照"]
    C2 --> R["AI Result：候选"]
    R --> E["Evaluation：自动/人工"]
    R --> A["Adoption：采用/修改/拒绝"]
    A --> V["正式领域版本"]
```

## 4. 文件与版本 ER

```mermaid
erDiagram
    STORED_FILE {
        BIGINT id PK
        VARCHAR logical_name
        VARCHAR status
        BIGINT owner_user_id FK
    }
    FILE_VERSION {
        BIGINT id PK
        BIGINT stored_file_id FK
        VARCHAR version_no
        VARCHAR object_key
        CHAR checksum_sha256
        BIGINT size_bytes
    }
    FILE_RELATION {
        BIGINT id PK
        BIGINT file_version_id FK
        VARCHAR object_type
        BIGINT object_id
        BIGINT object_version_id
        VARCHAR relation_type
    }
    FILE_PARSE_RESULT {
        BIGINT id PK
        BIGINT file_version_id FK
        VARCHAR parser_version
        VARCHAR status
        JSON result_json
    }
    FLOW_VERSION {
        BIGINT id PK
        BIGINT drawio_file_version_id FK
    }
    FLOW_EXPORT {
        BIGINT id PK
        BIGINT flow_version_id FK
        BIGINT file_version_id FK
        VARCHAR export_format
    }
    CONFIRMATION_MATERIAL {
        BIGINT id PK
        BIGINT confirmation_round_id FK
        BIGINT file_version_id FK
    }
    TEST_EVIDENCE {
        BIGINT id PK
        BIGINT test_record_id FK
        BIGINT file_version_id FK
    }

    STORED_FILE ||--o{ FILE_VERSION : versions
    FILE_VERSION ||--o{ FILE_RELATION : links
    FILE_VERSION ||--o{ FILE_PARSE_RESULT : parses
    FILE_VERSION o|--o{ FLOW_VERSION : editable_source
    FLOW_VERSION ||--o{ FLOW_EXPORT : exports
    FILE_VERSION ||--o{ FLOW_EXPORT : stores
    FILE_VERSION ||--o{ CONFIRMATION_MATERIAL : evidences
    FILE_VERSION ||--o{ TEST_EVIDENCE : evidences
```

文件关系必须指向 `file_version_id`，不能只指向逻辑 File，否则历史记录无法确定当时使用的内容。

## 5. 知识预留 ER（Sprint 6）

```mermaid
erDiagram
    ISSUE o|--o{ EXPERIENCE_CANDIDATE : suggests
    AI_CALL o|--o{ EXPERIENCE_CANDIDATE : suggests
    EXPERIENCE_CANDIDATE o|--o| EXPERIENCE_VERSION : approved_as
    EXPERIENCE ||--o{ EXPERIENCE_VERSION : versions
    EXPERIENCE ||--o{ EXPERIENCE_PROJECT_RELATION : relates
    PROJECT ||--o{ EXPERIENCE_PROJECT_RELATION : relates
    SCENARIO ||--o{ CHECKLIST : groups
    CHECKLIST ||--o{ CHECKLIST_VERSION : versions
    EXPERIENCE_VERSION o|--o{ CHECKLIST_VERSION : sources
    EXPERIENCE_VERSION o|--o{ KNOWLEDGE_USAGE : used
    CHECKLIST_VERSION o|--o{ KNOWLEDGE_USAGE : used
    SKILL_VERSION o|--o{ KNOWLEDGE_USAGE : used
    AI_TASK ||--o{ KNOWLEDGE_USAGE : retrieves
    AI_CALL o|--o{ KNOWLEDGE_USAGE : injects
    EXPERIENCE_VERSION o|--o| KNOWLEDGE_INDEX_RECORD : indexes
    CHECKLIST_VERSION o|--o| KNOWLEDGE_INDEX_RECORD : indexes
```

`knowledge_index_record` 是 MySQL 到 Qdrant 的派生映射；索引必须能从有效知识版本完整重建。

## 6. 事件与指标 ER

```mermaid
erDiagram
    BUSINESS_EVENT_OUTBOX {
        BIGINT id PK
        VARCHAR event_id UK
        VARCHAR event_name
        VARCHAR publish_status
        JSON payload_json
    }
    AI_EVENT_OUTBOX {
        BIGINT id PK
        VARCHAR event_id UK
        VARCHAR event_name
        VARCHAR publish_status
        JSON payload_json
    }
    BEHAVIOR_EVENT {
        BIGINT id PK
        VARCHAR event_id UK
        VARCHAR event_name
        DATETIME occurred_at
        BIGINT project_version_id
        BIGINT ai_task_id
        VARCHAR trace_id
        JSON payload_json
    }
    EVENT_COMPENSATION {
        BIGINT id PK
        VARCHAR original_event_id FK
        VARCHAR compensation_type
        JSON replacement_payload
    }
    EVENT_INGEST_REJECTION {
        BIGINT id PK
        VARCHAR event_id
        VARCHAR rejection_code
        JSON field_errors
    }
    OPERATION_AUDIT_LOG {
        BIGINT id PK
        BIGINT actor_user_id FK
        VARCHAR operation_name
        VARCHAR object_type
        BIGINT object_id
        VARCHAR trace_id
    }
    IDEMPOTENCY_RECORD {
        BIGINT id PK
        BIGINT user_id FK
        VARCHAR endpoint_key
        VARCHAR idempotency_key
        CHAR request_hash
    }
    RETENTION_POLICY {
        BIGINT id PK
        VARCHAR policy_code
        VARCHAR table_name
        INT retention_days
        VARCHAR approval_status
    }
    DATA_PURGE_RUN {
        BIGINT id PK
        BIGINT retention_policy_id FK
        DATETIME cutoff_at
        BIGINT affected_count
        VARCHAR status
    }
    METRIC_DEFINITION {
        BIGINT id PK
        VARCHAR metric_id
        VARCHAR metric_version
        VARCHAR grain
        TEXT formula_text
    }
    METRIC_SNAPSHOT {
        BIGINT id PK
        BIGINT metric_definition_id FK
        DATETIME window_start
        DATETIME window_end
        DECIMAL numerator
        DECIMAL denominator
        DECIMAL metric_value
        VARCHAR quality_status
    }
    DATA_QUALITY_RUN {
        BIGINT id PK
        VARCHAR rule_set_version
        DATETIME window_start
        DATETIME window_end
        VARCHAR status
    }
    DATA_QUALITY_ISSUE {
        BIGINT id PK
        BIGINT data_quality_run_id FK
        VARCHAR rule_id
        VARCHAR severity
        VARCHAR affected_metric_id
    }
    OPTIMIZATION_EVALUATION {
        BIGINT id PK
        VARCHAR optimization_id UK
        VARCHAR conclusion
        DATETIME baseline_start
        DATETIME observation_end
    }
    OPTIMIZATION_METRIC_RESULT {
        BIGINT id PK
        BIGINT optimization_evaluation_id FK
        VARCHAR metric_id
        VARCHAR metric_role
        DECIMAL before_value
        DECIMAL after_value
    }
    EXPERIMENT_DEFINITION {
        BIGINT id PK
        VARCHAR experiment_key UK
        VARCHAR primary_metric_id
        VARCHAR status
    }
    EXPERIMENT_ASSIGNMENT {
        BIGINT id PK
        BIGINT experiment_definition_id FK
        VARCHAR subject_type
        BIGINT subject_id
        VARCHAR variant
    }

    BUSINESS_EVENT_OUTBOX ||--o| BEHAVIOR_EVENT : publishes
    AI_EVENT_OUTBOX ||--o| BEHAVIOR_EVENT : publishes
    BEHAVIOR_EVENT ||--o{ EVENT_COMPENSATION : corrected_by
    USER_ACCOUNT ||--o{ OPERATION_AUDIT_LOG : acts
    USER_ACCOUNT ||--o{ IDEMPOTENCY_RECORD : scopes
    RETENTION_POLICY ||--o{ DATA_PURGE_RUN : governs
    METRIC_DEFINITION ||--o{ METRIC_SNAPSHOT : produces
    DATA_QUALITY_RUN ||--o{ DATA_QUALITY_ISSUE : finds
    METRIC_SNAPSHOT o|--o{ DATA_QUALITY_ISSUE : affects
    OPTIMIZATION_EVALUATION ||--o{ OPTIMIZATION_METRIC_RESULT : compares
    METRIC_DEFINITION ||--o{ OPTIMIZATION_METRIC_RESULT : supplies
    EXPERIMENT_DEFINITION ||--o{ EXPERIMENT_ASSIGNMENT : assigns
```

事件消费者只追加 `behavior_event` 或拒收记录；指标任务只追加快照和质量结果，不修改原始事件。

## 7. 关系验收清单

- [ ] Project、Project Version、工作版本和版本派生基数与正式版本规则一致。
- [ ] Requirement、PRD、Flow、Plan、File、Template、Checklist 均使用领域专属版本表。
- [ ] Review Scope 固定到明确产物版本。
- [ ] Confirmation Round 为 1:N 且只有一个当前有效轮次。
- [ ] Test Record 只直接关联 Confirmation Round。
- [ ] Issue 必属 Project Version，Test Record 可空，Bug/Optimization 不成为并列主对象。
- [ ] AI Task、Call、Context、Result、Evaluation、Adoption 可完整追溯。
- [ ] Event、Audit、Outbox、Compensation 与 Metric Snapshot 相互分离。
- [ ] Knowledge 与 Qdrant 保持“权威事实/派生索引”边界。
