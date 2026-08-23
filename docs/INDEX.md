# 项目文档索引

> 最后更新：2026-08-23
> 说明：索引只记录文档位置与效力，不能替代领域主责文档

## MVP2 Accepted Baseline and Completion Closeout

- Freeze: `RC-02-FREEZE-11-20260821-MVP2-PRD-REVIEW-V1`; OpenAPI `packages/contracts/openapi/openapi.json` SHA256 `80c5060dad07e02c3092303fa479ca73428ce44f1d9d8e0dc640c6249b15b01e` (50 paths / 56 operations); migration head `20260821_0005`; AI is OUT.
- Accepted source sequence: `2499d7a` Backend Package 1, `28e904e` Backend Package 2, `00511ae` Frontend Package, and `201a53e` source-binding fix.
- `MVP2_INTEGRATION_REVIEW=ACCEPT`, PRD happy path PASS, and post-push closeout PASS on `origin/codex/backend-mvp2-package1-local` at `201a53e`.
- The later `GET design-reviews` 405 is `VERIFICATION_PROCEDURE_OUT_OF_SCOPE_NOT_IMPLEMENTATION_FAILURE`.
- `MVP2_STATUS=COMPLETED_IN_MAIN`; `MVP2_MAIN_PROMOTION=PASS`.
- `BACKEND_PACKAGE_1=ACCEPTED`; `BACKEND_PACKAGE_2=ACCEPTED`; `FRONTEND_PACKAGE=ACCEPTED`; `SOURCE_BINDING_FIX=ACCEPTED`; `MVP2_INTEGRATION_REVIEW=ACCEPT`; `PRD_HAPPY_PATH=PASS`.
- Accepted reconciliation merge: `32e8d7e1395ddb90395f146d06ac29a99ebbd011`, preserving parents `14bc14ea8af1cdd85d82556271dfe0a0957cc5af` and `201a53ec40d3eb7c6e62025355c0a7806ff524de`; this merge is in Main ancestry. The governance closeout is a later child and does not claim `32e8d7e` remains the future remote tip.
- Current Gate: `MVP2-COMPLETE`; next gate: `AWAITING_NEW_USER_AUTHORITY`. No further MVP2 action is authorized by this closeout.
- `RELEASE_AUTHORITY=NOT_GRANTED`; `TAG_AUTHORITY=NOT_GRANTED`; `DEPLOYMENT_AUTHORITY=NOT_GRANTED`; `PRODUCTION_CHANGED=NO`.

P1's `1be1aec` runtime, `portfolio-p1-v1-accepted-main` tag, and `20260729_0004` migration are historical only. The baseline above does not replace the domain authority of the existing product, interaction, visual, development-planning, data-design, AI-capability, or technical-design documents.

## 当前正式产品设计基线

正式产品设计位于 `产品设计体系整理/`：

- `产品设计总览.md`
- `产品功能架构.md`
- `核心业务流程.md`
- `版本管理规则.md`
- `产品设计决策记录.md`
- `产品数据闭环设计.md`
- `数据指标体系.md`
- `AI质量评价指标.md`
- `版本优化指标.md`

以上九份文档状态为“当前有效”；如与下游交互设计冲突，以正式产品设计为准。

## Interaction Design

目录：`交互设计与页面状态机/交互设计/`

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `交互设计方案.md` | 用户任务、端到端流程、AI 前中后、Review/版本与数据反馈原则 | 当前有效（2026-07-27 已验收） |
| `信息架构.md` | 一级导航、页面树、页面编号、MVP/增强边界 | 当前有效（2026-07-27 已验收） |
| `页面结构设计.md` | 页面骨架、核心页面结构、组件清单和低保真交互 | 当前有效（2026-07-27 已验收） |
| `页面跳转关系.md` | 页面入口、出口、返回、失败恢复和跨页面流程 | 当前有效（2026-07-27 已验收） |
| `异常与空状态设计.md` | 加载、失败、空数据、权限、只读、冲突和恢复 | 当前有效（2026-07-27 已验收） |

这些文档构成当前有效交互设计基线，但不得反向修改正式产品设计。

## Page State Machine

目录：`交互设计与页面状态机/页面状态机/`

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `页面状态机.md` | 全局与核心页面族状态、事件、守卫、转换、权限、异常恢复和端到端验收路径 | 当前有效（2026-07-27 已验收） |

该基线使用 Personal Skill `page-state-machine-design` 形成，作为 Wireframe、UI、原型和前端开发的直接输入；若与正式产品设计或已验收交互设计冲突，按既定权威层级修订状态机。

## Wireframe 与 UI 设计

目录：`Wireframe与UI设计/`

页面状态机前置基线、低保真 Wireframe、视觉规范和全量高保真原型均已确认。当前以 Penpot 官方 MCP 作为主要可编辑设计工具；Phase 1 核心样板与全量高保真原型已升格为 V1 正式视觉与开发输入基线。Figma 暂停，未来仅在官方额度或权限恢复后同步核心展示页面。

计划产出位置：

| 子目录 | 计划产出 | 当前状态 |
|---|---|---|
| `Wireframe/低保真Wireframe.md` | 11 个页面族模板、页面布局、组件、状态和响应式规则 | 已确认，当前设计输入 |
| `UI设计/UI设计方案.md` | 视觉关键词、密度、浅色非蓝色方向、明暗模式、字体、AI 表达和样板策略 | V1 正式视觉基线（2026-07-28 已验收） |
| `UI设计/设计系统规范.md` | Token、样式、基础组件 API 与三层设计源结构 | V1 正式设计系统基线（2026-07-28 已验收） |
| `UI设计/design-tokens.json` | Penpot 98 个活动变量 Token、字体与阴影的机器可读副本 | 当前有效（V1） |
| `高保真原型/Penpot MCP配置与验证.md` | 官方来源、版本、连接、Phase 1 与全量写入校验记录 | 当前有效 |
| `高保真原型/高保真原型说明.md` | 11 个页面族、43 个页面编号、代表状态、AI 生命周期、T01～T07 原型与验收入口 | 当前有效（2026-07-29 已验收） |
| `高保真原型/V1视觉方向参考-PRD候选审核合并稿.png` | 核心页面视觉方向参考 | 已确认方向参考；非 Penpot 正式导出件 |
| `高保真原型/` | 高保真页面、原型说明、设计源记录、导出件与验收记录 | V1 全量高保真基线已完成并验收；正式 SVG/PNG 文件包待按需补交 |

## Development Planning

目录：`开发规划/`

Development Planning 已于 2026-07-29 通过用户确认。Sprint 0～5 为十二周 MVP，Sprint 6 为不阻塞 MVP 的知识中心与 AI 能力增强版本；五份文档共同构成当前有效 V1.0 开发规划基线。

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `项目开发规划与MVP路线.md` | 技术基线、公共契约、MVP 边界、阶段、上线、风险与降级 | 当前有效（V1.0） |
| `Sprint规划.md` | Sprint 0～6 的目标、任务、交付物、退出条件和跨 Sprint Gate | 当前有效（V1.0） |
| `开发任务清单.md` | FE、BE、AI、DATA、QA、OPS 共 79 个唯一任务及验收证据 | 当前有效（V1.0） |
| `模块依赖关系.md` | 模块拓扑、接口责任、关键路径、功能旗标和故障降级 | 当前有效（V1.0） |
| `验收标准.md` | Sprint、T01～T07、API、数据、性能、安全、无障碍和发布 Gate | 当前有效（V1.0） |

This paragraph recorded the 2026-07-29 design-freeze stage state. Current implementation and MVP2 completion status is governed by the MVP2 completion closeout section above; the historical design documents retain their domain authority.

## 数据埋点与数据库设计

目录：`数据埋点与数据库设计/`

数据埋点与数据库设计已于 2026-07-29 通过用户确认。五份文档构成当前有效 V1.0 数据设计基线，覆盖 MVP、Sprint 6 与未来阶段；设计达到 DDL-ready，但不包含可执行 SQL、Alembic、OpenAPI、JSON Schema、分析后台页面或业务代码。

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `数据埋点设计.md` | 43 个页面、10 个页面族状态机、179 个转换的采集分类，事件目录、触发时机、公共信封与分析后台需求 | 当前有效（V1.0，2026-07-29 已确认） |
| `数据库详细设计.md` | MySQL 8.4 表模型、写入责任、约束、索引、归档、迁移分期与历史草案对照 | 当前有效（V1.0，2026-07-29 已确认） |
| `数据字典.md` | 77 张表的字段、类型、空值、主外键、唯一约束、索引与枚举 | 当前有效（V1.0，2026-07-29 已确认） |
| `ER图.md` | 总体、业务主链、AI 追溯、文件版本、知识预留和事件指标六类 Mermaid ER 视图 | 当前有效（V1.0，2026-07-29 已确认） |
| `指标计算逻辑.md` | 59 个指标的唯一计算登记、血缘、去重、迟到、N/A、质量门槛与刷新规则 | 当前有效（V1.0，2026-07-29 已确认） |

`产品设计体系整理/数据指标体系.md` 的 VO-03～09 已同步为专项 `版本优化指标.md` 的唯一编号和公式口径。“Development / Sprint 0 尚未启动”属于 2026-07-29 数据设计冻结时的阶段状态；当前 MVP2 实现与完成状态以本文顶部“MVP2 Accepted Baseline and Completion Closeout”章节为准，数据设计文档的领域效力保持不变。

## AI 能力体系设计

目录：`AI能力体系设计/`

AI 能力体系设计已于 2026-07-29 通过用户确认。六份文档构成当前有效 V1.0 基线，冻结 AI 任务分类、Agent 逻辑架构、Task Router、Skill/Prompt/Template/Context 管理、Experience/Checklist 检索、调用追溯、评价反馈和版本机制，但不包含代码或可执行技术契约。

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `AI能力设计文档.md` | AI 任务分类、Task Envelope、Task Router、Capability Bundle/指纹、调用记录与评价反馈 | 当前有效（V1.0，2026-07-29 已确认） |
| `Agent架构设计.md` | Agent 组件职责、执行状态、重试/取消/恢复、可观测性、安全与故障降级 | 当前有效（V1.0，2026-07-29 已确认） |
| `Skill体系设计.md` | 平台 Skill 查询匹配、隔离安装、安全审核、版本、发布、停用和阶段边界 | 当前有效（V1.0，2026-07-29 已确认） |
| `模板管理设计.md` | Template 类型、结构、变量、兼容、校验、版本和正式产物边界 | 当前有效（V1.0，2026-07-29 已确认） |
| `Prompt管理设计.md` | Prompt 分层、变量、版本、测试、发布、回退和注入安全 | 当前有效（V1.0，2026-07-29 已确认） |
| `Context管理设计.md` | Context Strategy、动态组合、Experience/Checklist 检索、权限、Token 与追溯 | 当前有效（V1.0，2026-07-29 已确认） |

本阶段文档是 Development / Sprint 0 中 AI 服务行为与能力管理的直接设计输入；如与正式产品设计、已验收交互/页面状态、开发规划或数据设计冲突，按领域主责和既定权威层级修订本阶段文档，不得反向静默覆盖上游基线。

## 技术方案设计

目录：`技术方案设计/`

技术方案设计已于 2026-07-29 通过用户确认。六份文档构成当前有效 V1.0 技术设计基线，冻结 Development / Sprint 0 所需的服务边界、字段级接口、权限、部署、可观测性、风险与三人团队并行规则，但不包含代码、可执行 DDL/Alembic、OpenAPI/JSON Schema、Compose 或部署脚本。

| 文档 | 主责内容 | 当前状态 |
|---|---|---|
| `技术架构设计.md` | 前端、业务后端、AI、数据/文件/缓存、错误、测试、团队主责和端到端追踪 | 当前有效（V1.0，2026-07-29 已确认） |
| `接口设计.md` | `/api/v1` 与 `/internal/v1` 字段级 Markdown 契约、SSE、错误、幂等、并发与契约兼容 | 当前有效（V1.0，2026-07-29 已确认） |
| `部署方案.md` | Compose 环境拓扑、网络、Secret、镜像、发布、备份恢复、容量与 CloudBase PoC 隔离 | 当前有效（V1.0，2026-07-29 已确认） |
| `权限设计.md` | 身份会话、固定角色矩阵、对象/版本权限、内部服务身份、审计与安全测试 | 当前有效（V1.0，2026-07-29 已确认） |
| `日志与监控设计.md` | 结构化日志、trace 传播、Loki/Prometheus/Alertmanager/Grafana、SLI、告警和排障 | 当前有效（V1.0，2026-07-29 已确认） |
| `技术风险清单.md` | 24 项风险的概率、影响、触发、预防、降级、DRI 与关闭 Gate | 当前有效（V1.0，2026-07-29 已确认） |

Sprint 0 必须以本基线和上游正式文档生成机器可执行契约、迁移、配置、容器与测试证据；发现冲突时回到对应主责文档确认，不得静默改变已冻结业务语义。

## 跨阶段入口

- `PROJECT_MEMORY.md`：稳定长期结论与维护规则。
- `PROJECT_STATUS.md`：当前阶段、任务、禁区和阻塞。
- `AGENTS.md`：项目执行规则和 Skill 调用边界。
