# PROJECT MEMORY

## 2026-08-27 — Deployment V2 completed in production

- `DEPLOYMENT_V2_STATUS=COMPLETED_IN_PRODUCTION`; `PRODUCTION_PUBLIC_URL=https://bywill.xyz`; HTTPS, fresh login, Real AI, Public Smoke, and stability PASS.
- Production source head is `8d17693f87f9e5f2f44e02d749db0630c920284b`, while artifact identity is service-specific: Web `fe62a8f8743e...` and Business API `94cb4af945c4...` retain revision `7cd0c3a44c8b1bc39ffff26d66fdcceeb71e3140`; AI API/Worker `41b1dd2578b2...` uses revision `8d17693f87f9e5f2f44e02d749db0630c920284b`.
- Production contract identity is OpenAPI SHA256 `cc4c77cfa8d1d9937969ddaeacdfe24283cbb3283e9f43dd6e01c77ab5cee6f3`; Alembic head is `20260823_0006`; MySQL stays on persistent volume `aipdv-mysql-data`.
- The production MVP5 DeepSeek capability bundle was explicitly materialized from commit `7cd0c3a44c8b1bc39ffff26d66fdcceeb71e3140`. Real AI provider, Worker, MinIO, hash, `content_ref`, pricing, persistence, and Business API readback passed. The AI candidate remained proposal-only; a quality-blocked candidate was not adopted, and the owner confirmed a manually edited Baseline.
- Deployment V2 backup reference is `/var/backups/aipdv/deployment-v2-20260825T084536Z`. The pre-V2 Web/API image identities remain rollback references `9777a02bc060...` and `b7d7255118e2...`.
- Resolved incidents: production build resource saturation; legacy Secret disclosure and credential rotation; first Web image rejected for browser API origin `localhost`; AI success persistence omitted `pricing_version`, fixed by `8d17693f`. No Secret value is stored here.
- Permanent operational policy: build application images off-host only; never print environment values during Secret audits; inspect key names only; rotate disclosed credentials; validate production browser configuration from built bundles; explicitly precheck the AI capability catalog before enabling Real AI.

## MVP5 Current Governance Memory

- `MVP5_STATUS=COMPLETED_IN_MAIN`; current Gate is `MVP5-COMPLETE`; accepted scope is Option C: submitted Test Record → No-Issue/Validation Complete or Issue → defect/optimization classification → disposition.
- The accepted MVP5 implementation commit is `dd7ff5356a2f8362f2f0287cfa3132aae4a8bd33`, parent `03e2054c195d7b798f494193bc0ba464fcdc6180`; it is the product implementation identity. A later governance closeout child does not replace this implementation identity.
- `origin/main` and `origin/codex/mvp5-execution` were both promoted to `dd7ff5356a2f8362f2f0287cfa3132aae4a8bd33` by ordinary non-force fast-forward. No force push, other-ref push, or tag push was used; `PRODUCTION_CHANGED=NO`.
- The final OpenAPI identity is SHA256 `cc4c77cfa8d1d9937969ddaeacdfe24283cbb3283e9f43dd6e01c77ab5cee6f3` (64 paths / 77 operations). Contract/Runtime semantic consistency passed: `createIssueDisposition` accepts `current_version_fix | defer | reject`; persisted Response/domain history may retain `derive_new_version`; the sole public derive entry is `POST /api/v1/projects/{project_id}/versions:derive`.
- The feedback loop is accepted: `current_version_fix` preserves source Issue and source Confirmation Round and creates a next Confirmation Round draft without an extra Project Version; `derive_new_version` creates the atomic non-working Project Version with Issue source binding; optimization flow and No-Issue backend mutual exclusion passed.
- Real AI integration is PASS using DeepSeek through the OpenAI-compatible Requirement Clarification path. AI is proposal-only (`AI_DIRECT_AUTHORITY=NO`), Human confirmation is required, manual fallback is preserved, and the controlled call cost was `$0.000241`. No API key, Secret, or Authorization header was persisted or committed.
- Validation is PASS: backend focused validation, AI focused 38 passed, frontend affected 14 passed, frontend typecheck/lint/production build, HTTP/API/MySQL integration, migration chain, Contract materialization, and full local product flow. Product functional completeness for the current demo scope is PASS; `MVP6_REQUIRED_FOR_CORE_DEMO=NO`.
- The implementation package contained 68 files: Contract 3, Backend 7, AI 9, Frontend 8, generated client 34, Tests 7, Database 0. Alembic head remains `20260823_0006`; no migration or undeclared schema change was introduced.
- Post-promotion content state is clean by content checks: tracked content diff 0, staged content diff 0, true-untracked count 0, and diff check PASS. The known 354 EOL/stat-only status noise remains accepted and was not normalized. `SECRET_TOKEN_PATTERN_HITS=0`; `SECRET_COMMITTED=NO`.
- MVP5 is complete for the current product demo scope. The next independently authorized phase is `DEPLOYMENT_V2` on the existing Alibaba Cloud server; this closeout does not authorize deployment, release, tag, production migration, or production secret work.

## MVP4 Current Governance Memory

- Freeze is unchanged: `MVP4-TEST-RECORD-CONTRACT-FREEZE-20260824-V1`, contract `MVP4-v1`, and frozen base `7dd83c6423a1e449043e4fcf78c34783ce562119`; AI, schema change, migration change, and post-submit Issue semantics are OUT.
- The accepted materialized OpenAPI raw SHA256 is `7ef6943de306ea73339b6b96c333186dc425c0c84a3e241bc3af5ceb0ac62b98` (60 paths / 71 operations). Its five Test Record operations cover list/create by Confirmation Round, single-record get, draft update, and submit.
- Accepted scope is the minimum vertical chain: confirmed/effective Confirmation Round → Test Record draft → edit/save with optimistic concurrency → submit → submitted read-only → reopen/read identical persisted data. Submitted records are immutable; correction, reopen, supersede, evidence upload, and Issue/no-Issue disposition remain OUT.
- Migration head remains `20260823_0006`. MVP4 reused the existing `confirmation_round`, `test_record`, `user_account`, `idempotency_record`, `operation_audit_log`, and `outbox_event` foundations and introduced no table, column, index, or migration.
- Accepted implementation commit is `2aff618b147f753b68b288891e79e1064fa70b56`, a direct child of the MVP3 governance baseline `7dd83c6423a1e449043e4fcf78c34783ce562119`. It contains the 32-file Contract/backend/generated-client/frontend/test vertical delivery.
- Focused validation is PASS: OpenAPI generation/materialization checks, 23 backend focused tests, 33 frontend focused tests, and frontend typecheck. Real HTTP → API → disposable MySQL `8.4.11` integration passed at Alembic `20260823_0006`; temporary containers and network were removed.
- Push acceptance is PASS: repository-local GitHub username binding resolved GCM multi-account ambiguity; the exact non-writing dry-run passed; `origin/codex/mvp4-execution` was then created at the accepted commit by one ordinary non-force push.
- Main promotion is PASS: `origin/main` was ordinarily fast-forwarded directly from `7dd83c6423a1e449043e4fcf78c34783ce562119` to `2aff618b147f753b68b288891e79e1064fa70b56`. The execution branch remains at the same accepted implementation commit. A later governance closeout child does not change the accepted implementation identity.
- `MVP4_STATUS=COMPLETED_IN_MAIN`; `MVP4_INTEGRATION_ACCEPTANCE=PASS`; `MVP4_MAIN_PROMOTION=PASS`; current Gate is `MVP4-COMPLETE`; next Gate is `AWAITING_NEW_USER_AUTHORITY`.
- No Release, Tag, Deployment, Production Migration, or Production authority was granted or exercised. `PRODUCTION_CHANGED=NO`.

## MVP3 Historical Governance Memory

- Freeze is unchanged: `MVP3-SCOPE-CONTRACT-FREEZE-20260823-V1`, contract `MVP3-v1`, frozen base `1ca41c531475e62af026301684353657c567c6fa`, artifact SHA256 `d5edb3d811091b8181959d7ff79f4a82e961685fde8924ffc60107c6fcb5b621`; AI is OUT.
- The historical OpenAPI baseline remains SHA256 `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e` (50 paths / 56 operations). The accepted materialized target raw SHA256 is `c37c50a3bebfe77daa245363dac9dae2212f303f59deff823540bddc2b7a6039` (57 paths / 66 operations).
- Migration `20260823_0006` is accepted on top of `20260821_0005`. Its same-target runtime guard remains frozen: authenticate and verify target identity, read the three foundation counts before DDL, and continue only for 0/0/0. Disposable evidence never substitutes for Staging or Production existing-data evidence.
- Backend Package 1 `e3bbcf7519d968f106ecbdb3820a8d1c5b4637f6`, Backend Package 2 `b7c1a62f3f00e922af7df6444703a89c835c9578`, and Frontend Package 3 `c39c710a25cf50cdc85497526f6c567066799a22` are accepted.
- Integration acceptance is PASS on disposable MySQL `8.4.11`, Alembic `20260823_0006`, and a real HTTP API runtime. The accepted chain is: confirmed MVP2 source → Plan → V1 → effective → Round1 confirmed; save V2 while V1 remains effective; switch to V2 → `needs_reconfirmation`; confirm Round2 → Round1 `superseded`, Round2 confirmed/effective.
- The Integration Gate used 18 successful HTTP calls including authentication and repeated frozen MVP3 operations. Temporary API/MySQL containers and their Docker network were removed; no repository file, staging environment, deployment, or production system was changed.
- Main promotion is PASS: `origin/main` was ordinarily fast-forwarded from `1ca41c531475e62af026301684353657c567c6fa` to the accepted MVP3 implementation commit `c39c710a25cf50cdc85497526f6c567066799a22`. The source branch `origin/codex/backend-mvp3-package1` remains at that accepted commit. A later governance closeout child does not change the accepted implementation identity and must not be described as part of the three-package implementation.
- `MVP3_STATUS=COMPLETED_IN_MAIN`; `MVP3_INTEGRATION_ACCEPTANCE=PASS`; `MVP3_MAIN_PROMOTION=PASS`; current Gate is `MVP3-COMPLETE`; next Gate is `AWAITING_NEW_USER_AUTHORITY`.
- No Release, Tag, Deployment, Production Migration, or Production authority was granted or exercised. `PRODUCTION_CHANGED=NO`.

## MVP2 Historical Governance Memory

- Freeze is unchanged: `RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1`, contract `mvp2.prd-review.rc02.v1`, OpenAPI SHA256 `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e` (50 paths / 56 operations), migration head `20260821_0005`; AI is OUT.
- Backend Package 1 `2499d7a`, Backend Package 2 `28e904e`, Frontend Package `00511ae`, and source-binding fix `201a53e` are accepted. The fix preserves the persisted effective Requirement Version ID in confirmed/effective lists and leaves draft/non-effective null.
- Integration acceptance is PASS: the authorized PRD happy path passed in disposable MySQL/API and real browser evidence. A later speculative `GET design-reviews` 405 is out of the frozen eight generated operations and is not an implementation failure.
- Post-push closeout is PASS on `origin/codex/backend-mvp2-package1-local` at `201a53e`; its canonical real-content diff is clean and true-untracked count is zero.
- `MVP2_STATUS=COMPLETED_IN_MAIN`; `MVP2_MAIN_PROMOTION=PASS`.
- `BACKEND_PACKAGE_1=ACCEPTED`; `BACKEND_PACKAGE_2=ACCEPTED`; `FRONTEND_PACKAGE=ACCEPTED`; `SOURCE_BINDING_FIX=ACCEPTED`; `MVP2_INTEGRATION_REVIEW=ACCEPT`; `PRD_HAPPY_PATH=PASS`.
- Accepted reconciliation merge is `32e8d7e1395ddb90395f146d06ac29a99ebbd011`, with parents `14bc14ea8af1cdd85d82556271dfe0a0957cc5af` and `201a53ec40d3eb7c6e62025355c0a7806ff524de`; this merge is in Main ancestry. The governance closeout is a later child and does not claim `32e8d7e` remains the future remote tip.
- Current Gate is `MVP2-COMPLETE`; next gate is `AWAITING_NEW_USER_AUTHORITY`. No further MVP2 action is authorized by this closeout. `RELEASE_AUTHORITY=NOT_GRANTED`, `TAG_AUTHORITY=NOT_GRANTED`, `DEPLOYMENT_AUTHORITY=NOT_GRANTED`, `PRODUCTION_CHANGED=NO`.

P1 facts are historical only: `1be1aec`, `portfolio-p1-v1-accepted-main`, and migration `20260729_0004` describe the earlier accepted P1 release and do not describe current MVP2 state or authorization. Earlier design-stage statements that development had not started are historical context, not current status.

> 项目：AI 产品设计与验证平台（亦称 AI 产品工作流平台）  
> 建立日期：2026-07-27  
> 用途：后续产品、设计、架构、数据与开发工作的长期知识入口。当前产品口径以 `产品设计体系整理/` 九份 V1.0 文档为准；本文只保存摘要，不替代领域主责文档。

## 1. 项目定位

本项目是面向产品经理及产品研发协作人员的 AI 驱动产品设计与验证工作平台。平台以项目和项目版本为主线，辅助完成需求分析、PRD、流程设计、设计评审、实现方案、实现确认、测试验证、Issue 分析、优化迭代和知识沉淀，形成可追溯、可复用、可持续优化的产品研发闭环。

平台的价值不是用单次对话生成孤立文档，而是把产品过程、AI 能力、项目记忆、知识资产和真实运行数据组织为长期系统能力。

## 2. 核心设计原则

- Documentation First：所有实现建立在已确认文档上，设计变化先同步文档。
- Architecture First、Database First、Flow First、Implementation Last。
- 项目版本是一轮完整产品迭代，不等同于 PRD、Flow 或文件版本。
- 流程允许从指定节点进入、跳过可选节点及一键运行，但应记录缺失项和当前阶段。
- AI 调用采用动态上下文，不把全部历史直接送入模型。
- AI 输出必须可追溯到任务、Skill/Skill Version、Prompt、Template、Model 和上下文来源。
- 核心业务数据不物理删除；归档保留历史，回滚通过创建新版本实现。
- Experience 与 Checklist 分工明确：Experience 提供可复用分析经验，Checklist 提供场景化检查提醒。
- 知识入库受控：AI 生成候选，规则筛选并由人工审核；Skill 安装同样需要安全检查、测试和用户确认。
- 产品数据闭环只依赖真实系统数据，重点比较版本、Prompt 和流程优化前后的变化。

## 3. 用户角色

MVP 核心用户为产品负责人（产品经理、独立产品开发者或承担产品职责的项目负责人），拥有项目内最终确认权。评审者、实现确认人和测试人员是流程参与身份，同一用户可兼任。平台管理者维护基础配置并可兼任知识审核者。细粒度 RBAC、团队空间和审批链属于增强能力。

## 4. 产品整体流程

主流程：

创建项目 → 创建项目版本 → 需求输入与确认 → PRD 生成/上传/编辑 → 需求审查 → Flow 生成/上传/编辑（可选）→ 设计评审（可循环）→ 实现方案 → 实现确认与差异记录 → 产品验证 → Issue/Bug/Optimization → 经验候选与 Checklist 候选 → 人工审核入库 → 优化需求进入新项目版本。

补充规则：

- 新项目自动创建 V1。
- 已有资料可从指定节点进入，缺失阶段不阻断但需标记。
- Flow 是否需要由 AI 建议、用户决定。
- Flow 初步采用“文本流程 Review → Mermaid Review → `.drawio` → 逻辑校验与版本保存”的分层生成路径，最终交付 `.drawio`、PNG 和 SVG。
- 子流程可从主流程的节点或业务模块独立生成和保存，并保留父 Flow、来源位置及来源文档版本关系。
- Flow 路径当前为暂定产品方案；流程图类型、Review 交互、自动布局、逻辑校验和导出规格尚未冻结。
- 普通 Bug、小范围异常、文案或 UI 微调不创建项目版本；新功能、业务规则变化、重大优化或重大实现调整创建新版本。
- 历史回滚不覆盖当前版本，而是基于历史版本创建新版本。
- 新版本继承项目上下文和主 PRD；Flow、Implementation Plan 不默认继承。

## 5. 平台模块关系

可见一级业务模块统一为：项目中心、产品设计、实现确认、产品验证、知识中心、系统设置。文件与产物、AI 执行与上下文、配置审计是跨模块支撑能力；分析与运营属于增强能力。历史“数据中心”“AI 能力中心”不再作为当前一级导航。

- 项目中心：项目、版本、阶段、资料、最近模块与项目级配置入口。
- 产品设计：Requirement、PRD、Flow、Design Review、Review Feedback、Implementation Plan。
- 实现确认：Implementation Confirmation、实际实现资料、Difference Record、进入测试条件。
- 产品验证：Test Record、Issue、Bug、Optimization、迭代判断。
- 知识中心：Experience Candidate、Experience、Scenario、Checklist、Skill、Prompt、Template。
- 文件与产物服务：统一上传、版本、业务对象关联、解析结果与向量化入口；MVP 不设独立一级入口。
- 系统设置：用户偏好、模型/API 配置、模块开关。
- 数据闭环：行为事件、AI 调用、输出质量、文档质量、知识复用和版本效果分析。

## 6. 数据流

业务数据流以 Project → Project Version 为根，产品设计产物依次形成 Requirement、PRD/PRD Version、Flow/Flow Version、Design Review/Feedback 和 Implementation Plan；实现确认关联实际资料并产生 Difference Record；验证阶段形成 Test Record 与 Issue，Issue 可分化为 Bug 或 Optimization。

AI 数据流：Business Backend 接收任务 → Task Router → Skill Manager → Context Manager/Context Strategy → 结构化检索、规则过滤与向量检索 → Knowledge Retriever → Prompt Builder → LLM Gateway → Result Processor → 保存正式业务产物、AI Call Record 与 Context Record → 返回用户或生成知识候选。

知识闭环：Issue → AI 分析 → Experience Candidate → 规则筛选/人工审核 → Experience → 场景化 Checklist 候选 → 人工确认 → Checklist → 后续 Review/分析调用。

产品数据闭环：用户操作 → 事件埋点 → 采集存储 → 指标计算 → 看板 → 问题发现 → 功能/Prompt/流程优化 → 新版本验证。

## 7. 数据库与 ER 设计原则

数据库逻辑分为七层：业务数据、文件与文档、AI 能力、知识资产、AI 上下文、系统配置、审计与记录。

核心 ER：

- User 1:N Project；Project 1:N Project Version；Project 1:1 Project Context。
- Project Version 1:N Requirement、PRD、Design Review、Implementation Plan、Issue。
- PRD 1:N PRD Version；PRD 0:N Flow；Flow 1:N Flow Version。
- Design Review 1:N Review Feedback。
- Implementation Plan 1:N Confirmation Round；每轮关联 Difference Record 和实际资料，同一方案只有一个当前有效轮次。
- Confirmation Round 1:N Test Record；Issue 必须属于 Project Version，可选关联 Test Record；Bug/Optimization 是 Issue 的类型扩展。
- Experience N:M Project；Scenario 1:N Checklist。
- Skill 1:N Skill Version；Prompt 与 Context Strategy 均绑定 Skill Version。
- Template 1:N Template Version。
- AI Call Record 1:N Context Record。
- File 1:N File Version、1:N File Parse Result，并通过多态 File Relation 关联业务对象。

当前确认的物理设计基线为 MySQL 8.4 LTS、InnoDB、utf8mb4、`BIGINT UNSIGNED` 主键、UTC `DATETIME(6)`、`row_version` 乐观锁；核心检索与约束字段结构化，JSON 仅用于非核心扩展。Qdrant 仅在 Sprint 6 知识增强阶段启用并保存可重建派生索引，MySQL/对象存储继续作为事实源，不建立 `vector_embedding` 事实表。

## 8. AI 设计原则

- Agent 不是简单模型调用，而是受业务后端控制的独立服务。
- Task Router 识别任务；Skill Manager 以规则、语义和用户选择三级方式匹配 Skill。
- Context Manager 按 Context Strategy 决定必需/可选上下文、数量限制和压缩策略。
- 上下文优先级总体为：当前任务、当前项目版本、项目长期上下文、Checklist、Experience、历史版本、全局/跨项目知识。两份文档中的细分权重有差异，后续应统一配置口径。
- Knowledge Retriever 采用 SQL/关键词、向量和规则过滤的混合检索。
- Prompt Builder 组合 System Prompt、Skill 规则、项目背景、当前需求、经验、Checklist 和 Template。
- LLM Gateway 统一 generate/chat/embedding，并屏蔽供应商差异。
- Result Processor 进行格式检查、内容评分、重试/人工修改和结果分类。
- 项目记忆更新分自动更新、AI 建议候选、用户手动更新三类，避免历史污染。
- AI Call Record 保存追溯信息；不保存完整上下文全文，Context Record 保存来源与摘要；采用结果保存全文，未采用结果保存摘要。

## 9. Skill、Prompt、Template 与 Checklist 原则

- Skill 是执行方法和能力单元，不承载大量经验；必须版本化。
- Skill 生命周期：发现/导入 → 安全检查 → 测试 → 候选 → 用户确认 → 启用 → 版本迭代 → 停用/废弃，历史版本保留。
- Prompt 绑定 Skill Version，记录 System Prompt、用户模板和变量。
- Template 控制输出结构，区分系统与用户来源并版本化。
- Checklist 绑定 Scenario、Stage、来源和标签，是提醒与审查项，不是简单的对错判断。
- Checklist 来源可为 Experience、Manual、System；重要修改应生成新版本，但现有物理表尚未给出 checklist_version。

当前产品设计阶段可使用 3 个用户级 External Skill：

- `jobs-to-be-done`：用户、场景、核心任务、痛点和期望结果分析；适用于产品设计阶段。
- `opportunity-solution-tree`：产品目标、用户机会、候选方案与验证关系分析；适用于产品设计阶段。
- `epic-hypothesis`：把功能或模块方向转化为可验证假设；适用于产品设计阶段。

External Skill 只提供分析方法，不得覆盖 `产品设计体系整理/` 中的当前正式设计。默认单次任务使用一个主 Skill，确有必要时最多组合一个辅助 Skill，不同时调用全部三个。实体位于 `F:\AI-Agent-System\skills\external`，详细来源、版本、适配和安全记录见 `F:\AI-Agent-System\skills\INDEX.md`。

Interaction Design 阶段启用 2 个用户级 External Skill：

- `user-flow-mapping`：用户任务流、页面入口/出口、跨页面跳转、用户可感知分支及异常恢复；不得用于后端、API、数据库、Agent 内部链路或技术架构。
- `wireframing`：页面目标、信息层级、内容区域、组件占位、操作入口和低保真结构；本项目不启用其高保真、视觉规范与开发实现内容。

Interaction Design 执行时的调用顺序为先 `user-flow-mapping`、后 `wireframing`；阶段已于 2026-07-27 完成并验收，两个 Skill 现均调整为 disabled，不再默认加载。上一阶段的 `jobs-to-be-done` 保持 candidate，另外两个产品设计 Skill 保持 disabled。External Skill 只提供方法支持，不得覆盖正式产品设计。页面状态机仍是 Interaction Design 之后的独立阶段。

## 10. API 设计记忆

API 采用 REST，统一前缀 `/api/v1/`，统一返回 `{code, message, data}`；常规能力以资源式 API 为主，评审提交、确认、版本派生等使用显式业务命令。查看版本、设置当前工作版本和基于历史派生必须分离。业务调用由 Frontend → Business API → Service → MySQL，AI 调用由 Business API → AI Agent API → Skill/Context/Knowledge/LLM → Result → Database。

已覆盖用户、项目/项目版本、Requirement、PRD、Review、Flow、Implementation、Test/Issue/Bug/Optimization、File、Agent、Skill、Experience/Checklist、Template、Context 和 Module Config。现有设计是资源清单级草案，字段级请求/响应、鉴权、分页、幂等、错误码和异步协议仍待后续阶段确认。

## 11. 页面功能结构记忆

当前页面工作基线已覆盖功能信息架构、交互设计和页面状态机，尚未进入视觉 UI：

- 首页：项目列表、最近项目、最近任务、AI 能力入口。
- 项目中心：项目列表 → 项目详情 → 版本管理；显示当前版本、阶段、历史记录。
- 产品设计：需求确认 → PRD → Flow → Review → 实现方案。
- 实现确认：设计方案 → 实际实现资料 → 差异分析 → 确认。
- 产品验证：测试任务 → Issue/Bug → 优化建议 → 迭代规划。
- 知识中心：Experience、Checklist、Skill、Prompt、Template（增强阶段开放完整管理）。
- 系统设置：模型/API、用户偏好、模块配置。

## 12. MVP 路线

MVP 是端到端薄闭环：Project Version → Requirement → PRD → Review → Implementation Plan → Confirmation Round → Test Record → Issue → 派生新版本，并包含基础文件能力和最小可追溯 AI 调用链。Flow 为可选产物。开发交接文档原第一至第三阶段解释为 MVP 内部交付里程碑，不代表第一阶段完成即为完整 MVP。

Experience、Checklist、Skill 管理、RAG 检索、完整数据埋点和分析看板属于增强能力；但 MVP 必须同步记录核心业务事实、AI 调用追溯、采用/修改/拒绝、基础质量检查和版本归因。组织级协作、外部平台集成、生态市场与自动评测属于未来规划。

### CloudBase 云端验证补充记录

CloudBase 仅作为 MVP 核心闭环完成后、集成测试阶段的候选云端部署 PoC 环境，不构成生产技术基线，也不改变当前 Development Planning 的基础设施可替换原则。本阶段技术方案不得以 CloudBase 专有能力形成业务、数据、文件、缓存、权限或部署锁定。生产服务器、云厂商、实例规格与容量方案应根据 MVP 测试和 CloudBase PoC 结果另行评审并冻结。

## 13. 文档索引与引用关系

当前权威层级：`产品设计体系整理/` 领域基线 → `PROJECT_MEMORY.md` 长期摘要 → `PROJECT_STATUS.md` 阶段状态。历史 DOCX 和 `项目初始化/` 分析文档只作追溯证据。

| 当前领域 | 主责文档 |
|---|---|
| 定位、用户、场景、MVP | `产品设计体系整理/产品设计总览.md` |
| 模块与对象归属 | `产品设计体系整理/产品功能架构.md` |
| 端到端流程与门禁 | `产品设计体系整理/核心业务流程.md` |
| 各类版本与文档效力 | `产品设计体系整理/版本管理规则.md` |
| 冲突裁决与待验证项 | `产品设计体系整理/产品设计决策记录.md` |
| 数据闭环、采集边界与治理 | `产品设计体系整理/产品数据闭环设计.md` |
| 平台、AI、质量、知识和版本指标 | `产品设计体系整理/数据指标体系.md` |
| AI 输出评价口径 | `产品设计体系整理/AI质量评价指标.md` |
| 版本前后对比与归因 | `产品设计体系整理/版本优化指标.md` |
| 数据采集、事件触发与公共信封 | `数据埋点与数据库设计/数据埋点设计.md` |
| 数据库表、约束、索引与迁移分期 | `数据埋点与数据库设计/数据库详细设计.md` |
| 字段、枚举与表级字典 | `数据埋点与数据库设计/数据字典.md` |
| 数据关系与六类 ER 视图 | `数据埋点与数据库设计/ER图.md` |
| 指标计算、血缘与数据质量门槛 | `数据埋点与数据库设计/指标计算逻辑.md` |

以下表格为历史来源索引：

| 领域 | 主责文档 | 补充/汇总文档 | 关系说明 |
|---|---|---|---|
| 总体大纲 | `已有设计草稿/草稿0大纲.docx` | `开发交接文档_V1.1.docx` | 草稿0定义四类设计边界；交接文档汇总全局 |
| 产品与流程 | `草稿1产品设计.docx` | 草稿2、草稿3、开发交接文档 | 草稿1给出原始流程；草稿2/3扩展模块和数据流 |
| 模块与页面功能 | `草稿2平台架构模块设计.docx` | 草稿8、开发交接文档 | 只到功能结构，未进入交互/UI |
| 数据流 | `草稿3平台架构数据流设计.docx` | 草稿5、草稿9、产品数据闭环设计 | 分别覆盖业务、AI/上下文与运营数据闭环 |
| 数据库/ER | `草稿4平台架构数据库设计.docx` | 草稿6、草稿7、开发交接文档 | 草稿4是逻辑与 ER 总设计，草稿6字段初稿，草稿7物理表初稿 |
| AI 上下文 | `草稿5AI上下文管理与调用流程设计.docx` | 草稿3、草稿9 | 草稿5定义检索、策略、压缩；草稿9定义完整调用生命周期 |
| AI Agent | `草稿9AI agent调用流程设计.docx` | 草稿8、开发交接文档 | 调度、Skill、Prompt、模型、结果处理与异常 |
| API | `草稿10API接口设计.docx` | 开发交接文档 | 接口资源清单和调用关系 |
| 系统架构 | `草稿8平台系统架构设计.docx` | 开发交接文档 | 前后端、服务、存储、部署与技术栈 |
| 数据闭环 | `产品数据闭环设计.docx` | 开发交接文档第16章 | 历史指标与后台功能初稿；当前口径已迁入正式 Markdown 基线 |
| 开发交接/MVP | `开发交接文档_V1.1.docx` | `项目开发规划与MVP路线.docx`（0 字节） | 当前唯一有效的汇总与 MVP 来源 |
| 埋点与数据方案 | `数据埋点与数据库设计方案.docx`（0 字节） | `数据埋点与数据库设计/` 五份当前有效 Markdown | DOCX 仅为历史无效占位；字段级 DDL-ready 设计已由当前基线补齐，可执行契约仍在 Sprint 0 实现 |

后续按“当前领域主责文档 → PROJECT_MEMORY 摘要 → PROJECT_STATUS 阶段状态”的单向引用维护，不再由历史开发交接文档反向定义当前口径。

## 14. 文档维护规范

- 新任务先读 `PROJECT_STATUS.md`，再读本文，并回到 `产品设计体系整理/` 对应领域主责文档核实细节。
- `PROJECT_MEMORY.md` 只保存稳定结论、跨文档关系和长期规则，不替代字段级设计。
- `PROJECT_STATUS.md` 只记录阶段、完成项、当前任务、禁区、阻塞和下一阶段。
- 交互设计与页面状态机共用阶段根目录 `交互设计与页面状态机/`，但正式产出必须分目录保存：交互设计产出统一放入 `交互设计与页面状态机/交互设计/`，页面状态机产出统一放入 `交互设计与页面状态机/页面状态机/`。
- 两个阶段的正式产出不得放在项目根目录、`产品设计体系整理/` 或对方阶段目录；跨阶段导航与说明可放在 `交互设计与页面状态机/README.md`，每份正式文档仍应只有一个主责阶段目录。
- 新增或调整设计时，先识别唯一主责文档，再更新所有引用/汇总文档和状态。
- 决策记录中“暂定/待决定”的事项不得在实现中自行冻结。
- 阶段完成后同步更新状态；涉及 Git 文件时结束前检查提交条件并征求 Commit/Push 确认。

## 15. 当前资料限制

- `数据埋点与数据库设计方案.docx` 和 `项目开发规划与MVP路线.docx` 为 0 字节，无法读取。
- 项目内不保留通用 Skill 副本；3 个产品设计 Skill 已归入用户级 External Skill 库。Template/Prompt 目录仍未建立；通用 `project-base` 模板未用于重建本项目。
- 历史 Word 文档的内容已完成结构化全量读取；因环境缺少 LibreOffice，未做页面视觉核对。本阶段正式输出均为 Markdown。

## 16. 当前有效交互设计基线

Interaction Design 已于 2026-07-27 通过用户验收。当前有效交互设计统一位于 `交互设计与页面状态机/交互设计/`，包括《交互设计方案》《信息架构》《页面结构设计》《页面跳转关系》《异常与空状态设计》。

稳定结论：

- 一级导航沿用项目中心、产品设计、实现确认、产品验证、知识中心、系统设置；文件、AI、上下文和数据反馈保持跨模块支撑能力。
- 项目与查看版本上下文在项目内页面持续可见；查看历史、设置当前工作版本和基于历史派生是三种独立交互。
- 用户主链为项目/版本 → Requirement → PRD → 可选 Flow → Review → Implementation Plan → Confirmation Round → Test Record → Issue 去向/新版本派生。
- AI 结果始终先进入候选审核；用户可直接采用、修改后采用、拒绝或重新生成，正式保存不得覆盖已评审或已确认历史。
- AI 长任务支持离开页面和从全局任务中心恢复；未知时长使用阶段反馈，不显示虚假百分比。
- 所有 MVP 核心页面族均定义正常、加载、空数据、失败、权限和只读反馈；这些是用户可感知交互，不替代正式页面状态机。
- 数据反馈只使用真实业务事实；比率展示分子、分母和样本量，分母为零显示 `N/A`，样本不足或无基线时不下改善结论。
- 页面状态机已作为独立阶段完成并验收；页面可感知状态、事件、守卫和转换以 `交互设计与页面状态机/页面状态机/页面状态机.md` 为准。

## 17. Wireframe/UI 阶段能力与产出规则

Wireframe、视觉规范与高保真原型阶段的正式产出统一存放在 `Wireframe与UI设计/`，不得放入项目根目录、`产品设计体系整理/` 或 `交互设计与页面状态机/`。其中：

- 低保真线框及其说明归入 `Wireframe与UI设计/Wireframe/`；
- `UI设计方案.md`、`设计系统规范.md` 及视觉规范材料归入 `Wireframe与UI设计/UI设计/`；
- 高保真页面、原型说明、Penpot/Figma 设计源记录、导出件和验收记录归入 `Wireframe与UI设计/高保真原型/`。

当前主要可编辑设计工具为 Penpot 官方 MCP，采用 Foundations、Components、Product UI 三 Pages 结构；Figma 路径因 Starter 限额/权限暂停，未来仅在官方额度或权限恢复后同步核心展示页面，不作为阶段阻塞依赖。官方 Figma Plugin 的 `figma-use`、`figma-generate-library` 和 `figma-generate-design` 保留登记，不复制到项目目录。

设计工具与外部 Skill 只负责执行已确认的产品设计、交互设计和页面状态机，不得覆盖正式业务决策。所有视觉阶段正式产出继续遵守本节目录边界。

## 18. 页面状态机 Skill

用户级 Personal Skill `page-state-machine-design` 已于 2026-07-27 创建并启用，实体位于 `F:\AI-Agent-System\skills\personal\page-state-machine-design`，Codex 通过 `C:\Users\10238\.codex\skills\personal\page-state-machine-design` 访问。该 Skill 用于页面或页面族的可观察状态、事件、守卫、转换、进入/退出动作、异步 AI 反馈、权限、持久化、并发冲突和异常恢复设计。

该 Skill 不承载本项目业务规则，不得重定义业务实体生命周期、后端编排、API、数据库、视觉样式或实现代码；正式产品设计与当前有效交互设计始终优先。状态机正式产出只能保存到 `交互设计与页面状态机/页面状态机/`。该 Skill 已用于本项目 Page State Machine 阶段，阶段于 2026-07-27 通过用户验收。

## 19. 当前有效页面状态机基线

Page State Machine 已于 2026-07-27 通过用户验收。当前有效主责文档为 `交互设计与页面状态机/页面状态机/页面状态机.md`，覆盖 10 个页面/页面族状态机、43 个信息架构页面、134 个唯一状态、179 个唯一转换及 7 个 Mermaid 核心转换图。

长期稳定规则：

- 页面状态、业务实体生命周期、工作流节点、异步任务状态、权限模式和最近访问模块必须分域，不得使用一个“状态”字段混合表达。
- 查看历史版本、设置当前工作版本和基于历史派生是三个独立事件；任何操作都不得静默替代另一个。
- AI 输出始终先成为候选；生成任务的排队、准备、生成、检查、成功、部分结果、质量阻断、失败、取消和目标过期均有独立反馈，离开页面不会自动取消任务。
- Requirement、PRD、Plan 等正式产物的修改通过新草稿或新版本完成；评审快照、历史版本、已确认轮次和已提交验证事实不可原位覆盖。
- Design Review、Implementation Confirmation、Test Record 与 Issue 去向均包含提交中、失败恢复、权限变化和并发保护；失败不得改变旧的正式事实。
- 加载失败、首次空、筛选空、前置不足、权限拒绝、只读、归档、对象不存在和局部失败是不同页面状态，UI 不得合并为无解释的空白页。
- 刷新、返回和深链恢复必须保留项目、查看版本、对象、筛选、任务和用户输入上下文；敏感提交在重新认证后不得自动重放。
- Flow 保持文本 Review → Mermaid Review → `.drawio` → 逻辑校验 → 版本保存的分层路径，AI 和自动布局结果仍是候选。

尚未冻结的边界继续沿用上游决策状态：仅布局变化的 Flow Version 策略、已提交 Test Record 的正式更正机制、细粒度 RBAC，以及 API 幂等/错误码/任务协议不得由 UI 或实现自行决定。

## 20. 当前有效 Wireframe/UI 视觉基线

Penpot Phase 1 核心样板于 2026-07-28 通过用户人工验收并升格为 V1 正式视觉基线。全量高保真原型于 2026-07-29 通过用户人工验收并升格为当前有效 V1 高保真基线。主责文档为 `Wireframe与UI设计/UI设计/UI设计方案.md`、`Wireframe与UI设计/UI设计/设计系统规范.md` 与 `Wireframe与UI设计/高保真原型/高保真原型说明.md`；可编辑设计源和验证记录见 `Wireframe与UI设计/高保真原型/Penpot MCP配置与验证.md`。

长期稳定规则：

- 产品形态优先桌面端 Web SaaS；采用浅色、中高密度的“轻盈可信工作台 / Light Trace Workspace”。
- 不使用蓝色作为主色，不使用紫罗兰表示 AI；Sage 只承担主操作与选中，Apricot 只承担 AI 身份和候选差异，Amber 表示一般提醒，Red 表示错误、拒绝和删除。
- 段落级操作放在内容区顶部，整篇级操作放在底部；`修改后采用` 是候选审核页唯一主按钮，避免重复操作竞争。
- 主对比区优先于右侧检查栏；来源可追溯默认展开，质量检查显示摘要，业务规则默认折叠或只显示异常。
- 双栏内容保持章节水平对齐、充分行高和内边距；只高亮真正变化的词句，并明确区分新增、修改和删除。
- 核心任务区必须显示当前审核对象和进度，例如 `当前正在审核：1.1 背景与目标`、`第 1/12 段`。
- 基础控件默认使用 40px 高度、8px 圆角、1px 暖灰边框及统一图标粗细；状态不得只依赖颜色表达。
- Penpot 的 Foundations、Components、Product UI 三 Pages、98 个活动 Token、首批五类组件和 PRD Candidate Review 样板构成当前 V1 执行基线；项目内 `design-tokens.json` 是机器可读副本。
- 当前有效全量设计包括 16 个基础组件家族、14 个业务 Pattern、11 个 Wireframe 页面族映射、43/43 页面编号覆盖、43 个代表状态、AI 前中后生命周期、全局任务中心与 T01～T07 原型入口。
- Penpot 全量稿曾因把像素行高写入倍率字段而导致固定文字层不可见；已按“原行高 ÷ 字号”恢复倍率，并完成 20 个正式画板的 PNG 真实渲染检查。后续写入 Penpot `lineHeight` 必须使用倍率，不得直接写入像素值。
- 后续页面必须沿用本基线，不得修改已确认的业务逻辑、交互流程或页面状态机；具体色值可通过 Token 优化，但不得改变语义角色。
- 全量高保真阶段已经验收关闭；后续视觉调整必须作为明确变更进入，不得在开发阶段静默改写当前设计基线。

## 21. 当前有效数据埋点与数据库设计基线

数据埋点与数据库设计已于 2026-07-29 通过用户确认。当前有效主责文档为 `数据埋点与数据库设计/数据埋点设计.md`、`数据库详细设计.md`、`数据字典.md`、`ER图.md` 与 `指标计算逻辑.md`。

长期稳定规则：

- 43 个页面、10 个页面族状态机和 179 个唯一转换均已按服务端业务事实、AI 运行事实、关键前端行为、审计记录或不采集分类；MVP 不采鼠标轨迹、完整点击流和停留时长。
- 全量设计包含 77 张表，并按 MVP、Sprint 6 和未来阶段实施；MVP 迁移不提前创建无业务用途的空表。
- `behavior_event` 与 `operation_audit_log` 分离；业务事实、AI 事实、Outbox、补偿、拒收和幂等记录职责独立，多个服务不得共享表级写权限。
- Requirement、PRD、Flow、Implementation Plan、File、Template、Checklist 保持领域专属不可变版本与谱系；Implementation Plan 具有多轮不可变 Confirmation Round，Test Record 直接关联轮次，Issue 归属 Project Version，Bug/Optimization 为扩展。
- AI Task、Call、Context、Result、Evaluation、Adoption 分表；重试新增 Call，不覆盖失败记录；未采用 AI 输出正文和完整敏感上下文不得复制到分析明细。
- Qdrant 只保存可从 MySQL/对象存储重建的派生向量索引；MVP 只采预置知识来源，Sprint 6 再完整启用知识候选、检索、注入、引用和采用链路。
- 当前登记 59 个唯一指标，按结果、驱动、护栏和数据质量组织；VO-01～09 以 `版本优化指标.md` 为唯一编号与定义来源。上线后先采集 2～4 周基线，不虚设业务目标。
- 五份文档达到 DDL-ready，但不包含可执行 SQL、Alembic、OpenAPI、JSON Schema、分析后台页面或业务代码；这些实现仍须在用户明确启动 Development / Sprint 0 后开展。

## 22. 当前有效 AI 能力体系设计基线

AI 能力体系设计已于 2026-07-29 通过用户确认，阶段交接标记为“窗口切换节点 8”。当前有效主责文档为 `AI能力体系设计/AI能力设计文档.md`、`Agent架构设计.md`、`Skill体系设计.md`、`模板管理设计.md`、`Prompt管理设计.md` 与 `Context管理设计.md`。

长期稳定规则：

- 平台 AI 能力是受业务服务约束的候选生成与分析能力；Agent 不拥有 Project、Project Version、正式产物或流程节点的状态所有权，`ready` 不等于正式。
- 标准主链为业务任务 → Task Router → Skill Version → Prompt/Template Version → Context Strategy Version → 动态检索与组合 → LLM Gateway → Result Processor → 用户审核/正式化 → 评价与反馈。
- AI 任务同时按业务阶段、任务动作、目标对象、风险级别、输出形态和执行模式分类；生产任务类型来自受控目录，不接受前端任意字符串动态创建。
- Task Router 先做权限、状态、任务、Schema 和兼容性硬过滤，再按“合法用户选择 > 精确规则 > 合法候选内语义排序 > 默认版本”选路；无合法能力时 blocked，不用通用模型冒充专用 Skill。
- 每次调用冻结 Capability Bundle；AI Capability Version 以 Skill、Prompt、Template、Context Strategy、Model、Provider 运行配置和评价/结果规则版本组合形成规范化指纹，组件原始 ID 仍是权威追溯字段。
- Agent 使用 precheck、queued、preparing、generating、checking、ready/partial/quality_blocked/failed/cancelled/expired/stale_target 等既有状态语义；重试新增 Call 或 Task，不覆盖失败历史，离页不自动取消。
- 平台运行时 Skill 与开发环境 Codex Skill 分离；Skill 遵循来源登记、隔离、静态审核、动态测试、固定回归、人工批准、启用、版本迭代、停用/废弃的受控生命周期。MVP 不开放任意外部安装。
- Prompt 负责版本化语言指令并绑定 Skill Version；Template 负责输出结构；Context 保存本次事实和参考；Experience 是 advisory 分析经验，Checklist 是场景化提醒和完整度检查，五者不得混用。
- Context Strategy 区分必需/可选来源、权限、数量、Token、压缩和缺失处理；权限过滤先于语义/向量排序，当前正式事实与候选/历史/建议来源必须显式区分，必需来源不得因超限静默丢弃。
- Qdrant 仅在 Sprint 6 启用并作为可从 MySQL/对象存储重建的派生索引；不可用时降级结构化/关键词检索，不影响 MVP 主链。
- AI Task、Call、Context Usage、Result、Evaluation 与 Adoption 分域记录；正式结果必须 100% 追溯实际能力版本、目标快照和上下文来源，未采用正文和完整敏感上下文不得复制到分析明细。
- 质量证据分运行可用、输出合格、用户可用和下游有效四层；结构、必填、追溯和安全是正式化硬门禁，重大错误不得被平均分掩盖，优化应按单一能力版本或明确组合变更归因。
- 六份文档冻结逻辑能力、职责、生命周期、检索和追溯规则，不包含代码、可执行 DDL/Alembic、OpenAPI、JSON Schema 或管理页面实现；Development / Sprint 0 仍需用户明确启动。

## 23. 当前有效技术方案设计基线

技术方案设计已于 2026-07-29 通过用户确认。当前有效主责文档为 `技术方案设计/技术架构设计.md`、`接口设计.md`、`部署方案.md`、`权限设计.md`、`日志与监控设计.md` 与 `技术风险清单.md`。

长期稳定规则：

- 运行边界为 Next.js Web → Business API；Business API 通过内部契约调用 AI API/Worker。Browser 不直接访问 AI 服务、数据库、Redis 或模型供应商；AI 候选只能由 Business API 在用户确认后正式化。
- Business API 是身份、权限、Project Version、正式业务产物、文件元数据、审计和 Business Outbox 的写入方；AI Service/Worker 只写 AI 运行与追溯事实。多个服务使用独立数据库账号和表级写权限。
- MySQL 8.4 是业务、AI 追溯、事件与审计事实源；MinIO/S3 保存文件正文；Redis 只承担 Celery Broker、短期进度/SSE、限流和可重建缓存，故障时不得产生虚假成功。
- 文件使用初始化、短期单对象签名传输、完成 HEAD/大小/校验和验证和元数据生效的两阶段协议；对象键和签名 URL 不属于业务 ID，不进入日志或长期事件。
- 公共接口统一 `/api/v1`，内部接口统一 `/internal/v1`；字段级 Markdown 契约已覆盖身份、项目/版本、文件、Requirement、PRD/Flow、Review/Plan、Confirmation、Test/Issue、AI Task、SSE、正式化和内部 Context。Sprint 0 据此生成 OpenAPI 3.1、内部契约与事件 JSON Schema。
- 写命令使用 `Idempotency-Key`，可变对象使用 `expected_version`；ID 对外为字符串，时间为 UTC RFC 3339，列表使用稳定游标。历史与正式事实不可原位覆盖。
- 权限采用 `owner/reviewer/implementer/tester` 固定项目角色和 `admin` 系统角色；owner 保留最终确认权，admin 不自动获得项目内容决策权。Access JWT 短期有效，Refresh Token 七天、轮换、哈希存储并使用 Secure/HttpOnly Cookie。
- MVP 可观测性使用结构化 JSON 日志、Loki、Prometheus、Alertmanager 和 Grafana，通过 trace/command/task ID 关联服务、Outbox、事件与审计；MVP 不部署 Tempo。
- 三人团队按目录和契约分工：前端负责 `apps/web`，后端负责 `services/api`、OpenAPI、Alembic 和部署 DRI，AI/数据负责 `services/ai`、AI/事件 Schema、数据质量与监控。跨端能力必须先冻结契约；Alembic 迁移链由后端串行维护。
- 部署基线是可替换的 Local/CI/Staging/生产候选 Docker Compose 拓扑，不冻结生产云厂商、服务器型号或容量。CloudBase 只作为 MVP 核心闭环完成后的集成测试 PoC 候选，不能自动升格为生产技术基线。
- 六份文档冻结技术行为与实施边界，不包含业务代码、可执行 DDL/Alembic、OpenAPI/JSON Schema、Compose 或部署脚本；这些产物由明确启动后的 Development / Sprint 0 实现并验证。
