# PROJECT STATUS

> 最后更新：2026-08-25

## Current Phase

MVP5 Complete in Main

MVP5 validation-feedback closure, real DeepSeek Requirement Clarification, Contract/Runtime alignment, focused validation, exact 68-file commit, feature-branch push, and ordinary non-force fast-forward Main promotion are complete. The accepted MVP5 implementation commit is `dd7ff5356a2f8362f2f0287cfa3132aae4a8bd33`, a direct child of the accepted MVP5 baseline `03e2054c195d7b798f494193bc0ba464fcdc6180`. The governance closeout is a later child and does not change the implementation commit identity.

## MVP5 Accepted Baseline

- `MVP5_STATUS=COMPLETED_IN_MAIN`; `MVP5_CURRENT_GATE=MVP5-COMPLETE`; `MVP5_OPTION=C`.
- Implementation commit: `dd7ff5356a2f8362f2f0287cfa3132aae4a8bd33`; parent `03e2054c195d7b798f494193bc0ba464fcdc6180`; `origin/main` and `origin/codex/mvp5-execution` both point to the implementation commit before governance closeout.
- Accepted product scope: submitted Test Record → Validation Decision → No Issue/Validation Complete or defect/optimization Issue → disposition. `current_version_fix` preserves source Issue and Confirmation Round and creates a next Confirmation Round draft without an extra Project Version. `derive_new_version` is exposed only through `POST /api/v1/projects/{project_id}/versions:derive`.
- Real AI: DeepSeek OpenAI-compatible Requirement Clarification passed with Human-in-the-loop; AI has no direct authority, manual fallback remains available, and the controlled call cost was `$0.000241`. No Secret or Authorization header was committed.
- Final OpenAPI identity: `cc4c77cfa8d1d9937969ddaeacdfe24283cbb3283e9f43dd6e01c77ab5cee6f3` (64 paths / 77 operations). OpenAPI/Runtime semantic consistency passed.
- Database: Alembic head `20260823_0006`; no new migration and no undeclared schema change.
- Validation: backend focused PASS; AI focused 38 passed; frontend affected 14 passed; frontend typecheck, lint, production build, HTTP/API/MySQL integration, database migration chain, controlled real AI, Contract materialization, and full local product flow all PASS. Product functional completeness for the current demo scope PASS; MVP6 is not required for the core demo.
- Commit package: 68 files — Contract 3, Backend 7, AI 9, Frontend 8, generated client 34, Tests 7, Database 0. Main promotion was ordinary non-force fast-forward; force push, other-ref push, and tag push were not used.
- Content state after promotion: tracked content diff 0, staged content diff 0, true-untracked count 0. Known 354 EOL/stat-only status noise is accepted and was not normalized. `SECRET_TOKEN_PATTERN_HITS=0`; `SECRET_COMMITTED=NO`.
- `PRODUCTION_CHANGED=NO`; Tag, Release, Deployment, and Production Migration authority remain not granted.

MVP4 Test Record contract materialization, backend and frontend vertical workflow, generated client, focused validation, disposable MySQL 8.4 integration acceptance, execution-branch push, and ordinary Main promotion are complete. The accepted MVP4 implementation commit is `2aff618b147f753b68b288891e79e1064fa70b56`, a direct child of the completed MVP3 Main baseline `7dd83c6423a1e449043e4fcf78c34783ce562119`. This governance closeout is a later child if promoted and does not claim `2aff618` remains the future remote tip.

## MVP4 Accepted Baseline

- Freeze: `MVP4-TEST-RECORD-CONTRACT-FREEZE-20260824-V1` / `MVP4-v1`; accepted OpenAPI raw SHA256 `7ef6943de306ea73339b6b96c333186dc425c0c84a3e241bc3af5ceb0ac62b98` (60 paths / 71 operations). AI is OUT.
- Frozen base: completed MVP3 Main governance baseline `7dd83c6423a1e449043e4fcf78c34783ce562119`.
- Accepted scope: confirmed/effective Confirmation Round → Test Record draft → edit/save → submit → submitted read-only → reopen/read identical persisted record. Post-submit Issue/no-Issue semantics, correction/supersede, evidence upload, AI, Release, and Deployment remain OUT.
- Database scope: reuse-only on migration head `20260823_0006`; existing `confirmation_round`, `test_record`, `user_account`, `idempotency_record`, `operation_audit_log`, and `outbox_event` foundations were reused. No schema or migration change was made.
- Accepted implementation commit: `2aff618b147f753b68b288891e79e1064fa70b56`; 32-file vertical delivery covering Contract, backend, generated client, frontend, focused tests, and disposable MySQL integration evidence.
- Validation: OpenAPI generation/materialization checks PASS; backend focused validation 23 passed; frontend focused validation 33 passed plus typecheck; real HTTP → API → disposable MySQL `8.4.11` integration at Alembic `20260823_0006` passed. Temporary containers and network were removed.
- Push acceptance: `origin/codex/mvp4-execution` was created at `2aff618b147f753b68b288891e79e1064fa70b56` by an ordinary non-force push after repository-local GCM account binding recovery and a successful non-writing dry-run.
- Main promotion: ordinary non-force direct fast-forward `7dd83c6..2aff618` to `origin/main`; `origin/codex/mvp4-execution` remains at the accepted implementation commit.
- `MVP4_STATUS=COMPLETED_IN_MAIN`; `MVP4_INTEGRATION_ACCEPTANCE=PASS`; `MVP4_MAIN_PROMOTION=PASS`.
- `MVP4_CURRENT_GATE=MVP4-COMPLETE`; `MVP4_NEXT_GATE=AWAITING_NEW_USER_AUTHORITY`. No further MVP4 implementation action is authorized by this closeout.
- `RELEASE_AUTHORITY=NOT_GRANTED`; `TAG_AUTHORITY=NOT_GRANTED`; `DEPLOYMENT_AUTHORITY=NOT_GRANTED`; `PRODUCTION_MIGRATION_AUTHORITY=NOT_GRANTED`; `PRODUCTION_CHANGED=NO`.

## MVP3 Historical Accepted Baseline

- Freeze: `MVP3-SCOPE-CONTRACT-FREEZE-20260823-V1` / `MVP3-v1`; artifact SHA256 `d5edb3d811091b8181959d7ff79f4a82e961685fde8924ffc60107c6fcb5b621`; AI is OUT.
- Frozen base: `1ca41c531475e62af026301684353657c567c6fa`. Historical OpenAPI baseline SHA256 is `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e` (50 paths / 56 operations); materialized target raw SHA256 is `c37c50a3bebfe77daa245363dac9dae2212f303f59deff823540bddc2b7a6039` (57 paths / 66 operations).
- Migration head: `20260823_0006` from `20260821_0005`; the frozen same-target 0/0/0 existing-data guard remains mandatory before its first DDL. No Production Migration Authority was granted or exercised.
- Accepted commits: Backend Package 1 `e3bbcf7519d968f106ecbdb3820a8d1c5b4637f6`, Backend Package 2 `b7c1a62f3f00e922af7df6444703a89c835c9578`, Frontend Package 3 `c39c710a25cf50cdc85497526f6c567066799a22`.
- Package acceptance: `BACKEND_PACKAGE_1=PASS`, `BACKEND_PACKAGE_2=PASS`, `FRONTEND_PACKAGE_3=PASS`.
- Integration acceptance: PASS on disposable MySQL `8.4.11` at Alembic `20260823_0006` using a real HTTP API runtime. The frozen chain passed: V1 effective and Round1 confirmed; V2 saved while V1 remained effective; V2 effective produced `needs_reconfirmation`; Round2 confirmation superseded Round1 and became effective.
- Integration cleanup: temporary API/MySQL containers and Docker network removed; repository files unchanged and worktree clean.
- Main promotion: ordinary non-force fast-forward `1ca41c5..c39c710` to `origin/main`; `origin/codex/backend-mvp3-package1` remains at the same accepted commit.
- `MVP3_STATUS=COMPLETED_IN_MAIN`; `MVP3_INTEGRATION_ACCEPTANCE=PASS`; `MVP3_MAIN_PROMOTION=PASS`.
- `MVP3_CURRENT_GATE=MVP3-COMPLETE`; `MVP3_NEXT_GATE=AWAITING_NEW_USER_AUTHORITY`. No further MVP3 implementation action is authorized by this closeout.
- `RELEASE_AUTHORITY=NOT_GRANTED`; `TAG_AUTHORITY=NOT_GRANTED`; `DEPLOYMENT_AUTHORITY=NOT_GRANTED`; `PRODUCTION_MIGRATION_AUTHORITY=NOT_GRANTED`; `PRODUCTION_CHANGED=NO`.

## MVP2 Historical Accepted Baseline

- Freeze: `RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1` / `mvp2.prd-review.rc02.v1`.
- Contract: `packages/contracts/openapi/openapi.json`, SHA256 `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e`, 50 paths / 56 operations.
- Migration freeze/head: `20260821_0005`; only `prd.source_requirement_version_id`, `idx_prd_source_requirement_version`, and its FK are authorized. AI is OUT.
- Accepted commits: Backend Package 1 `2499d7a`, Backend Package 2 `28e904e`, Frontend Package `00511ae`, source-binding fix `201a53e`.
- Integration / PRD happy path: PASS. The later `GET design-reviews` 405 is classified `VERIFICATION_PROCEDURE_OUT_OF_SCOPE_NOT_IMPLEMENTATION_FAILURE`.
- Post-push closeout: PASS on `origin/codex/backend-mvp2-package1-local` at `201a53e`; canonical content clean and true-untracked count zero.
- `MVP2_STATUS=COMPLETED_IN_MAIN`; `MVP2_MAIN_PROMOTION=PASS`.
- `BACKEND_PACKAGE_1=ACCEPTED`; `BACKEND_PACKAGE_2=ACCEPTED`; `FRONTEND_PACKAGE=ACCEPTED`; `SOURCE_BINDING_FIX=ACCEPTED`; `MVP2_INTEGRATION_REVIEW=ACCEPT`; `PRD_HAPPY_PATH=PASS`.
- `MVP2_CURRENT_GATE=MVP2-COMPLETE`; `MVP2_NEXT_GATE=AWAITING_NEW_USER_AUTHORITY`. No further MVP2 action is authorized by this closeout.
- `RELEASE_AUTHORITY=NOT_GRANTED`; `TAG_AUTHORITY=NOT_GRANTED`; `DEPLOYMENT_AUTHORITY=NOT_GRANTED`; `PRODUCTION_CHANGED=NO`.

The P1 release facts (including `1be1aec`, `portfolio-p1-v1-accepted-main`, and `20260729_0004`) are historical only.

## Completed

- [x] 盘点当前工作区与项目资料
- [x] 完整提取并关联阅读 13 份有效设计文档
- [x] 识别 2 份 0 字节文档资料缺口
- [x] 梳理产品定位、角色、业务流程和平台模块
- [x] 梳理数据流、数据库、ER 和生命周期原则
- [x] 梳理系统架构、AI Agent、AI 上下文和 API
- [x] 梳理页面功能结构和 MVP 路线
- [x] 建立 `PROJECT_MEMORY.md`
- [x] 建立项目文档索引与引用关系
- [x] 完成项目现状分析
- [x] 完成项目一致性检查报告（仅建议，未修改既有设计）
- [x] 完成项目启动规划
- [x] 建立当前有效产品设计基线与文档权威层级
- [x] 明确产品定位、核心用户、核心场景与模块边界
- [x] 梳理端到端核心业务流程及异常/回退路径
- [x] 明确 MVP、增强功能与未来规划
- [x] 裁决初始化阶段发现的主要产品设计冲突
- [x] 区分当前有效、历史、废弃与无效设计
- [x] 输出 `产品设计体系整理/` 下九份当前有效阶段文档
- [x] 审查并将 `jobs-to-be-done`、`opportunity-solution-tree`、`epic-hypothesis` 迁移为用户级 External Skill
- [x] 更新用户级 Skill 索引、许可证记录和项目内调用/Token 控制规则
- [x] 记录 Flow 主流程、子流程、双重 Review、版本保存与交付路径初步方案
- [x] 完善产品数据闭环，建立平台、AI、质量、知识与版本优化指标口径
- [x] 明确 MVP 最小必采数据与核心功能统计覆盖
- [x] 用户确认进入 Interaction Design 阶段
- [x] 审查并安装 `user-flow-mapping` 与 `wireframing` 用户级 External Skill
- [x] 验证 External 实体目录、Codex Junction 入口、许可证、依赖、安全性和重复性
- [x] 将上一阶段产品设计 Skill 调整为非默认调用状态
- [x] 完成用户任务分析与端到端用户流程设计
- [x] 完成信息架构与页面编号体系
- [x] 完成核心页面低保真结构与组件清单
- [x] 完成 AI 生成前、中、后候选审核交互
- [x] 完成 Review、修改、确认、版本保存与历史派生交互
- [x] 完成数据反馈、异常、空数据、权限、只读与并发恢复设计
- [x] 完成页面跳转关系与核心页面可感知状态覆盖检查
- [x] 建立并更新 `docs/INDEX.md`
- [x] 用户确认 Interaction Design 阶段验收通过
- [x] 将五份交互设计文档升级为当前有效交互设计基线
- [x] 将稳定交互结论写入 `PROJECT_MEMORY.md`
- [x] 将 `user-flow-mapping` 与 `wireframing` 调整为 disabled
- [x] 审查官方 Figma Plugin 的 `figma-use`、`figma-generate-library` 与 `figma-generate-design`
- [x] 确认三项 Figma Skill 已由官方 Plugin 提供，无需 GitHub 安装或项目内复制
- [x] 验证 Figma Connector 已连接，并记录目标文件编辑权限仍需正式设计前验证
- [x] 登记 Wireframe/UI 阶段 Skill 调用边界与专属产出目录规则
- [x] 检索 Project、Personal、External 三层页面状态机 Skill，未发现匹配项
- [x] 检索 OpenAI 官方 curated Skill 清单，未发现页面状态机候选；官方 experimental 路径当前不存在
- [x] 排除来源不明或仅面向代码运行时状态机的替代 Skill，避免混入页面交互设计阶段
- [x] 创建并验证 Personal Skill `page-state-machine-design`
- [x] 验证 Personal 实体目录、Codex Junction 入口、frontmatter 与 Agent 元数据
- [x] 更新全局 Skill 索引和项目内调用边界
- [x] 用户确认正式进入 Page State Machine 阶段
- [x] 使用 `page-state-machine-design` 完成 10 个页面/页面族状态机
- [x] 完成 134 个状态、179 个唯一转换和 7 个 Mermaid 核心转换图
- [x] 完成 AI 前/中/后、Review、修改、确认、版本保存与历史派生状态建模
- [x] 完成加载、失败、空数据、权限、只读、并发、刷新与恢复状态建模
- [x] 完成 T01～T07 端到端可达性与结构完整性校验
- [x] 用户确认 Page State Machine 阶段验收通过
- [x] 将 `页面状态机.md` 升级为当前有效 Page State Machine 基线
- [x] 同步更新 `PROJECT_MEMORY.md`、`PROJECT_STATUS.md`、`docs/INDEX.md` 与阶段目录说明
- [x] 用户确认继续进入 Wireframe、视觉规范与高保真原型阶段
- [x] 使用 `wireframing` 检查并补齐 43 个页面的低保真模板覆盖
- [x] 完成 11 个复用 Wireframe、共用组件、核心状态界面和响应式规则候选
- [x] 形成“可信工作台 / Traceable Workspace”视觉方向候选
- [x] 用户确认除色彩外的视觉方向，并要求取消蓝色主色和紫罗兰 AI 色
- [x] 用户确认低保真 Wireframe 和其余视觉方向继续执行
- [x] 将视觉方向调整为浅色 Sage 主操作、Apricot AI 候选的 Light Trace Workspace
- [x] 完成设计系统 Phase 0 发现、差距分析、Token/样式/组件范围锁定
- [x] 验证 Figma 账号与唯一 Starter 团队计划；席位显示 View，创建/写入权限待实测
- [x] 暂停受 Starter 限额影响的 Figma 写入路径，改用 Penpot 官方 MCP 作为当前主要可编辑设计工具
- [x] 完成 Penpot 官方来源、版本、许可证、用户级配置与最小连接/写入验证记录
- [x] 在 Penpot 建立 Foundations、Components、Product UI 三 Pages 结构
- [x] 写入 Primitives、Semantic Light、Metrics 共 98 个活动 Token，并同步 `design-tokens.json`
- [x] 创建 Button、Input、Tabs、Modal、AI Status 五类核心组件样板
- [x] 创建 1440 × 1024 的 PRD Candidate Review 核心页面样板并落实六项必要优化
- [x] 完成 Penpot 文件结构校验、越界检查与重复名称检查
- [x] 用户确认 Penpot 核心样板通过人工视觉验收并升格为 V1 正式视觉基线
- [x] 用户明确发出“开始全量设计”执行指令
- [x] 补齐 Foundations 的 Grid、Accessibility 与 Delivery 规范板
- [x] 完成 16 个基础组件家族、14 个业务 Pattern 与 30 个本地组件入口
- [x] 完成 11 个高保真页面族模板并覆盖 43/43 页面编号
- [x] 完成 43 个代表状态、AI 前中后生命周期与全局任务中心/覆盖层
- [x] 完成 T01～T07 原型入口与 16 条 `click → navigate-to` 交互
- [x] 完成 Penpot 文件校验、同级重复名称检查、组件计数和原型交互检查
- [x] 修复 Penpot 全量稿文字行高倍率错误，并保持节点、布局、文案和 16 条原型交互不变
- [x] 完成 20 个正式画板的官方 Penpot PNG 真实渲染检查
- [x] 用户确认 V1 全量高保真原型阶段人工验收通过
- [x] 将全量高保真原型升级为当前有效 V1 视觉与开发输入基线
- [x] 用户明确启动 Development Planning
- [x] 确认 Next.js 16、FastAPI 模块化单体 + 独立 AI 服务、MySQL 8.4、Redis、MinIO、DeepSeek 与 Qdrant 技术路线
- [x] 确认 Sprint 0～5 为十二周 MVP，Sprint 6 为知识中心与 AI 增强版本
- [x] 完成开发阶段、Sprint、前后端、AI、数据、测试、依赖、验收、上线和降级规划
- [x] 建立 79 个唯一开发任务及跨模块依赖和发布 Gate
- [x] 输出 `开发规划/` 下五份 Development Planning 文档
- [x] 用户确认 Development Planning 阶段成果并升级为当前有效 V1.0 基线
- [x] 完成 43 个页面、10 个页面族状态机和 179 个转换的采集/不采集分类
- [x] 完成事件触发时机、公共信封、幂等、Outbox、补偿、拒收和审计边界设计
- [x] 完成 MySQL 8.4 下 77 张表的 DDL-ready 字段、约束、索引、归档与迁移分期设计
- [x] 完成 AI 调用、领域文档版本、知识使用和数据分析后台需求设计
- [x] 完成 59 个唯一指标的计算、血缘、迟到、去重、N/A 与数据质量门槛登记
- [x] 将 VO-03～09 统一为专项《版本优化指标》的唯一编号和公式口径
- [x] 用户确认数据埋点与数据库设计并将五份文档升级为当前有效 V1.0 基线
- [x] 完成 AI 任务分类、标准任务目录与 Task Envelope
- [x] 完成规则、语义和用户选择三级 Task Router 与 Capability Bundle/指纹设计
- [x] 完成 Agent 组件职责、执行状态、重试、取消、过期、恢复和降级设计
- [x] 完成平台运行时 Skill 查询匹配、隔离安装、安全审核、版本、发布和停用机制
- [x] 完成 Prompt 分层组合、Template 结构管理与 Context 动态组合设计
- [x] 完成 Experience/Checklist 检索、权限过滤、Token 预算与冲突处理规则
- [x] 完成 AI Task/Call/Context/Result/Evaluation/Adoption 追溯和质量反馈闭环
- [x] 用户确认 AI 能力体系设计并将六份文档升级为当前有效 V1.0 基线
- [x] 用户明确启动技术方案设计并确认采用独立 `技术方案设计/` 阶段目录
- [x] 完成 Next.js Web、FastAPI 业务模块化单体、独立 AI API/Worker、MySQL、Redis、S3/MinIO 的实施层架构设计
- [x] 冻结 Business API 对外、AI API 内网、候选与正式化分离、分服务表级写权限和基础设施可替换边界
- [x] 完成 107 个公共/内部接口引用的字段级 Markdown 契约，覆盖身份、项目、文件、产物、评审、确认、验证、AI Task、SSE 和内部 Context
- [x] 完成固定项目角色、关键写实时授权、服务身份、签名文件访问与安全测试矩阵
- [x] 完成 Local/CI/Staging/生产候选 Compose 拓扑、发布、备份、恢复和 CloudBase PoC 隔离规则
- [x] 完成结构化日志、Loki、Prometheus、Alertmanager、Grafana、trace 传播、告警与故障排查设计
- [x] 建立 24 项技术风险及概率、影响、触发、预防、降级、DRI 和关闭 Gate
- [x] 明确 1 名前端、1 名后端、1 名 AI/数据工程师的目录主责、契约先行、迁移串行和并行联调规则
- [x] 用户确认六份技术方案并将其升级为当前有效 V1.0 技术设计基线
- [x] P1 Requirement / Baseline 核心纵向闭环完成
- [x] P1 Traceable RC 完成
- [x] Git SHA → Image → Container → Public Runtime traceability VERIFIED
- [x] Public Acceptance PASS
- [x] UUID/HTTP compatibility PASS
- [x] Alembic PRE/POST = 20260729_0004 / MATCH
- [x] Main Promotion PASS
- [x] Accepted Main = 1be1aec9410211e33f84b99c6166c6768fb487cf
- [x] Release Tag `portfolio-p1-v1-accepted-main` 已验证

## Current Task

`MVP5-GOVERNANCE-CLOSEOUT`：MVP5 Option C 产品闭环、真实 AI Requirement Clarification、Contract/Runtime alignment、focused validation、精确 68-file implementation commit、execution-branch push 和普通 fast-forward Main promotion 均已通过；本次仅同步最终治理事实，不授予 Release、Tag、Deployment 或 Production 权限。

## Next Phase

`MVP5-COMPLETE`。当前 MVP5 产品核心开发完成于当前 Demo scope；下一阶段为独立 `DEPLOYMENT_V2` intake。任何 Deployment、Release、Tag、Production Migration 或 Production action 均需新的明确用户授权。

## Prohibited

- 不重新打开冻结的 `MVP4-TEST-RECORD-CONTRACT-FREEZE-20260824-V1`、已接受的 MVP3/MVP2 Gate、Product Semantics、State Machine 或 AI Boundary
- 不修改 OpenAPI、Alembic / Schema、已接受源分支或 `origin/main`，除非进入新的明确 Gate
- 不把 disposable MySQL Gate 解释为 Staging/Production Existing Data Evidence，不绕过 `20260823_0006` 的同目标 0/0/0 fail-closed guard
- 不重新打开已完成的 MVP5 Contract、AI、Validation/Issue、generated client 或 product flow；任何新产品范围必须取得新的明确授权
- 不把历史 P1 事实描述为当前 MVP2 状态
- 不执行 Release、Tag、Deployment、Production 或 Production migration
- 未经新指令继续扩展已完成的全量高保真范围或修改已确认业务逻辑
- 绕过当前有效开发规划自行修改技术栈、MVP 边界、Sprint、模块依赖或发布 Gate
- 绕过当前有效基线，直接使用历史 DOCX 草稿作为实现依据
- 未经确认安装未知 Skill 或外部能力

## Known Gaps / Blockers

- `数据埋点与数据库设计方案.docx` 仍是 0 字节历史无效占位；其设计缺口已由 `数据埋点与数据库设计/` 五份当前有效 V1.0 Markdown 补齐，可执行事件 Schema、数据作业和验收查询仍由 Sprint 0 的 `DATA-001/002` 实现。
- `项目开发规划与MVP路线.docx` 为 0 字节无效占位；其缺口已由 `开发规划/` 下五份当前有效 V1.0 Markdown 文档补齐，不再作为 Development Planning 阻塞项。
- 唯一 DDL-ready ER、字段、约束与索引基线已冻结；可执行 MySQL DDL 和 Alembic 迁移仍由 Sprint 0 的 `BE-003` 形成并验证。
- 字段级 Markdown 接口、错误码、分页、幂等、乐观锁、SSE 和内部 AI Task/Context 协议已冻结；可执行 OpenAPI 3.1、内部契约与事件 JSON Schema 仍由 Sprint 0 的 `BE-002`、`AI-001`、`DATA-001` 形成并通过契约 Gate。
- 核心用户和流程参与身份已明确；细粒度 RBAC、团队空间和审批链仍待增强阶段设计。
- 用户级 External Skill 库新增 `user-flow-mapping` 与 `wireframing`，来源为 `seb1n/awesome-ai-agent-skills` 1.0.0、Commit `a6c8c0ef3c240faefe1b0b5cabe1567beaea60fd`、MIT 许可证；实际文件位于 `F:\AI-Agent-System\skills\external`，项目内不保留重复副本。
- 当前产品层冲突已裁决，页面状态机、Development Planning、ER、数据字典、事件、AI 能力和技术设计基线已验收；可执行 OpenAPI、事件契约、Alembic、安全配置和运行脚本将在 Sprint 0 形成实现事实源。
- Mermaid ER 已完成静态围栏、实体引用和关系覆盖检查；当前环境缺少 Mermaid 运行时解析器，渲染级语法验证留待文档工具链或 Sprint 0 CI 补充，不阻塞本阶段确认。
- Flow 采用条件启用：Sprint 0 通过 `AI-003` 完成固定样本 Gate；通过后在 Sprint 3 实现完整链路，失败则保持 `flow_enabled=false` 且不阻断 MVP 主链。
- 当前环境缺少 LibreOffice，未完成历史 DOCX 页面渲染核对；已完成结构化全量读取。本阶段只交付 Markdown，不受 DOCX 排版限制影响。
- Figma 写入路径因 Starter 限额/权限暂停；未来仅在官方额度或权限恢复后同步核心展示页面，不作为当前阶段阻塞依赖。
- 20 个正式画板已通过官方 Penpot PNG 真实渲染检查和用户人工验收；正式 SVG/PNG 文件包仍未保存到项目目录，作为非阻塞补交付物在需要交付或前端切图时补做。
- 当前 Penpot Plugin API 不支持修改文件名称，文件仍为 `新建文件 1`，需在 Penpot 界面人工重命名。
- Figma Plugin 包目录/清单版本为 2.0.16，内部 `plugin.lock.json` 的 `pluginVersion` 仍为 2.0.7；作为元数据差异记录，不影响当前 Skill 发现。
- 外部检索未发现成熟可信的 Page State Machine Skill；已按用户确认创建 Personal Skill `page-state-machine-design`，后续需通过本项目实际任务持续验证和迭代。
- AI Capability 指纹可由实际 Skill/Prompt/Template/Context Strategy/Model/Provider 版本组合计算；任务目录版本和 Router 策略版本的持久化映射仍需在 Sprint 0 字段级契约中复核，如需改变已确认数据结构必须重新进入数据设计评审。
- AI 能力体系设计只冻结逻辑能力、职责、生命周期和追溯规则；可执行 Agent 编排、Provider Adapter、Router 配置、Prompt/Template/Context Schema 与管理页面仍由 Development 任务实现。
- 技术设计冻结可替换的单服务器 Compose 拓扑和运维规则，但生产云厂商、服务器型号、容量与最终日志/指标保留值仍需依据 MVP 性能、增长和恢复测试另行评审。
- CloudBase 仅作为 MVP 核心闭环完成后、集成测试阶段的部署 PoC 候选，不构成生产技术基线；PoC 结果不得替代生产安全、容量、RPO/RTO 和合规评审。

## Historical Roadmap Snapshot — 2026-07-29

以下为 2026-07-29 Development Planning 阶段形成的历史路线，不代表当前项目 Next Phase；当前 Gate 以上方 Current Phase / Next Phase 为准。

Development / Sprint 0：项目与环境初始化、技术 ADR、将已确认 ER 落实为 MySQL DDL/Alembic、形成 OpenAPI 与事件 JSON Schema、建立 Design Token 管线、验证 DeepSeek 连通性和 Flow 可行性 Gate。仅在用户明确启动后执行。

## Stage Roadmap

Project Initialization → Product Design Consolidation（已完成）→ Interaction Design（已完成）→ State Machine（已完成）→ Wireframe（已完成）→ UI Design（已完成）→ High-fidelity Prototype（已完成并验收）→ Development Planning（已完成并确认）→ Data Tracking & Database Design（已完成并确认）→ AI Capability Design（已完成并确认）→ Technical Solution Design（已完成并确认）→ Development（历史待启动状态）→ Testing → Iteration
