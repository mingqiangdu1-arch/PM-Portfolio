# Sprint 规划

> 文档状态：当前有效（2026-07-29 已确认）
> 规划版本：V1.0
> 建立日期：2026-07-29
> Sprint 周期：两周
> MVP：Sprint 0～5；Sprint 6 为增强版本

## 1. 规划假设

- 团队配置：1 名前端、1 名后端、1 名 AI/数据工程师；测试共同承担。
- 每个 Sprint 保留约 20% 容量处理联调、缺陷、文档和不可预见工作。
- 任何跨端能力必须先有版本化 OpenAPI/事件契约，再并行开发。
- 未满足前置 Gate 的条件功能不得挤占 MVP 关键路径。
- Sprint 评审以可运行证据为准，不以“代码已完成”代替可验收结果。

## 2. 通用工作节奏

### 2.1 Sprint 开始

- 读取当前有效产品、交互、页面状态机、UI 和开发规划。
- 检查依赖任务已完成，接口/事件 Schema 已可用。
- 每项任务明确负责人、验收标准、测试证据和降级方式。
- 未冻结的产品问题不得由开发任务自行决定。

### 2.2 Sprint 结束

- 完成代码审查、单元/集成/契约测试和必要 E2E。
- 数据库迁移可重复执行，回退或恢复路径已说明。
- 用户可感知状态与页面状态机一致。
- 新增事件、AI 记录和审计记录可查询验证。
- 演示成功路径、失败路径、权限路径和恢复路径。
- 文档、OpenAPI、事件字典和运行手册与实现同步。

## 3. Sprint 0：项目初始化与开发环境

### 目标

建立可重复的开发、测试和部署基础，冻结字段级技术规则，验证 DeepSeek 与 Flow 两项高风险能力。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | 初始化 Next.js 16/TypeScript；接入 Token 管线；建立 App Shell、路由、错误边界和 API Client |
| 后端 | 初始化 FastAPI 模块化单体；冻结 REST、错误、分页、幂等、并发与鉴权规范；形成 ER/迁移基线 |
| AI | 初始化独立 AI API、Celery Worker；实现 OpenAI-compatible Gateway；验证 DeepSeek 连接、流式/非流式、错误和用量 |
| 数据 | 建立事件字典、AI 追溯 Schema、审计与 Outbox 方案；明确 MySQL/Redis/MinIO 责任 |
| Flow | 使用固定样本验证文本 → Mermaid → `.drawio` → PNG/SVG、双重 Review、逻辑校验和版本保存可行性 |
| 测试 | 建立单元、组件、API、契约、迁移、E2E、性能和安全测试入口 |
| 运维 | 建立 Local/CI/Staging/Production Compose、环境变量模板、健康检查、日志、备份与恢复脚本框架 |

### 交付物

- 可启动的空应用拓扑和 CI 基线。
- 技术 ADR、字段级 ER、OpenAPI 基础契约、事件 Schema 和错误码规则。
- DeepSeek Provider 验证报告。
- Flow Gate 报告：`pass` 或 `fail`，附固定样本与证据。
- 设计 Token 构建/校验产物。

### 退出条件

- 一条命令可启动 Web、API、AI Worker、MySQL、Redis、MinIO。
- 数据库从空库迁移成功，重复运行不会产生漂移。
- Web 能调用 API 健康端点并显示统一错误。
- DeepSeek 测试请求可记录 trace、模型、Token 和错误映射，且无密钥进入日志。
- Flow Gate 有明确结论；未通过时 `flow_enabled=false`。

## 4. Sprint 1：项目中心与基础用户体系

### 目标

用户可安全登录、创建项目和 V1，查看/设置工作版本并管理基础项目上下文。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | 登录/注册、项目列表/创建/概览、版本管理、历史只读、派生入口、上下文条和基础文件面板 |
| 后端 | 用户与会话、固定项目角色、Project/Project Version/Project Context、版本命令、审计、文件元数据与签名 URL |
| AI | 暂不扩展业务生成；提供任务服务健康与鉴权联通 |
| 数据 | 项目、版本、权限、文件和审计事件；验证 ID/时间/trace 规范 |
| 测试 | 登录、令牌刷新/撤销、权限矩阵、创建 V1、历史查看、并发设置工作版本和派生版本 |
| 运维 | Staging 部署、每日 MySQL/对象存储备份、日志轮转和基础告警 |

### 交付物与演示

用户注册/登录 → 创建项目自动生成 V1 → 查看项目概览 → 查看历史版本 → 设置工作版本或安全派生。必须演示无权限、会话失效和并发冲突。

### 退出条件

- 查看历史、设置工作版本、基于历史派生是三个独立动作。
- 权限变化后关键写操作实时拒绝，未提交内容可复制。
- 文件内容、元数据和业务关联分离保存。
- 项目/版本事件和审计记录可按 trace 查询。

## 5. Sprint 2：需求输入与 AI 需求分析

### 目标

Requirement 从输入/导入到确认形成正式版本，AI 结果始终先作为可追溯候选。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | Requirement 工作台、资料导入、AI 生成前配置、全局任务中心、候选差异审核、采用/修改/拒绝 |
| 后端 | Requirement 领域、导入与对象关联、AI Task API、SSE、候选正式化命令和权限守卫 |
| AI | Requirement 分析图、上下文选择、DeepSeek 调用、结构校验、重试/取消和候选生成 |
| 数据 | AI Task/Call/Context/Result、采用状态、修改强度、拒绝原因和 Requirement 事件 |
| 测试 | T02 资料接续、T03 AI 生成审核、失败/取消/过期、离页恢复和 Provider 故障 |

### 交付物与演示

输入或导入资料 → 配置 AI 范围 → 后台生成 → 离开页面 → 从任务中心恢复 → 审核候选 → 修改后采用 → 保存正式 Requirement。

### 退出条件

- `ready` 候选不会自动成为正式内容。
- 采用、修改后采用、拒绝和未审核可区分、可统计。
- 正式结果追溯 Skill/Prompt/Template/Model/Context 完整率达到 100%。
- AI 不可用时仍可人工录入、上传和确认 Requirement。

## 6. Sprint 3：PRD 生成、编辑与版本保存

### 目标

形成 PRD 生成、结构化编辑、候选审核、正式版本和历史比较闭环；按 Flow Gate 决定是否启用完整 Flow。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | PRD 工作台、Tiptap 编辑器、段落/整篇候选审核、版本历史与比较；条件性 Flow 页面 |
| 后端 | PRD/PRD Version、主 PRD、正式化和版本比较；条件性 Flow/Flow Version/Export |
| AI | PRD 生成与结构检查；Flow Gate 通过时实现文本/Mermaid/`.drawio` 生成和校验 |
| 数据 | PRD/Flow 生成、版本、评审前置、采用与质量事件 |
| 测试 | 编辑离开保护、并发冲突、历史不可覆盖、候选过期；条件性 Flow 全链路和导出 |

### Flow 分支

- `pass`：本 Sprint 必须交付完整 Flow Review/版本链；任一层失败返回上一可编辑层。
- `fail`：保持 `flow_enabled=false`，只保存“跳过/未开放”事实，不创建半完成业务对象。

### 退出条件

- PRD 正式版本可定位来源 Requirement、AI 结果和操作者。
- Tiptap 保存结构化 JSON，并生成受控派生文本；导入/导出不静默丢失核心章节。
- 历史版本只读，新修改形成草稿或新版本。
- Flow 若启用，文本和 Mermaid 均须人工通过后才能进入下一层。

## 7. Sprint 4：Review、实现方案与实现确认

### 目标

完成设计评审、Implementation Plan 和多轮实现确认，使验证只从有效确认轮次进入。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | 评审发起/详情/反馈处置、Plan 工作台与候选审核、确认轮次、差异审核、就绪检查和历史轮次 |
| 后端 | Design Review/Feedback、Plan/版本引用、Confirmation Round、Difference Record、就绪检查和当前有效轮次约束 |
| AI | Implementation Plan 生成、来源引用和结构/必填项检查；不得自动通过评审或确认 |
| 数据 | 评审返轮、反馈处置、Plan、差异、就绪与确认事件 |
| 测试 | T04 评审循环、T05 实现确认、提交失败、权限变化、阻断差异和旧有效轮次保护 |

### 退出条件

- 评审通过不自动使产物生效，正式保存仍需有权用户确认。
- Confirmation Round 不可变，可有多轮且仅一轮当前有效。
- 提交失败或并发冲突不改变旧有效轮次。
- Test Record 的创建前置可定位到有效确认轮次。

## 8. Sprint 5：产品验证与 MVP 上线

### 目标

完成 Test Record、Issue 处置和版本回流，验证 T01～T07，并发布可恢复的私有部署 MVP。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | 验证概览、Test Record、Issue 列表/详情、Bug/Optimization 扩展、去向和派生版本 |
| 后端 | Test Record、Issue 主对象、类型扩展、处置命令、当前版本修正和派生版本 |
| AI | 完成 Provider 回归、限流/重试/熔断和失败诊断；不新增非必要生成能力 |
| 数据 | 核心指标离线查询、事件质量检查、AI 追溯检查和版本归因报告 |
| 测试 | T01～T07、浏览器/键盘/无障碍、20 并发性能、安全、备份恢复和降级演练 |
| 运维 | Staging 演练、生产 Compose、TLS、监控、告警、发布/回滚/恢复手册 |

### 退出条件

- T01～T07 全部通过且无阻断缺陷。
- AI 正式结果追溯完整率 100%，核心事件完整率 ≥99%，重复率 <0.5%。
- 20 并发用户下非 AI API P95 ≤500ms；AI 任务受理 ≤1s、状态传播 ≤3s。
- 无未处置 Critical/High 安全问题。
- 备份恢复演练满足 RPO 24 小时、RTO 4 小时目标。
- Staging 与 Production 使用同版本镜像和迁移，生产冒烟通过。

## 9. Sprint 6：知识中心与 AI 能力增强

### 目标

在不修改 MVP 主链事实归属的前提下，增加受控知识闭环、Qdrant RAG 和多 Provider 扩展。

### 任务

| 领域 | 主要任务 |
|---|---|
| 前端 | Knowledge Center、Experience Candidate/Experience、Scenario/Checklist、Skill/Prompt/Template 只读或管理入口 |
| 后端 | 候选审核、知识版本、状态和引用关系；`knowledge_center_enabled` 控制开放 |
| AI | Qdrant 索引/检索、重建、引用证据；增加第二 Provider Adapter 的契约框架 |
| 数据 | 知识调用、引用、审核和检索质量明细；不提前建设完整看板 |
| 测试 | 候选不得自动入库、权限、索引重建、Qdrant 降级、Provider 回归和引用可追溯 |
| 运维 | Qdrant 私有部署、认证、备份、恢复和托管云迁移说明 |

### 退出条件

- 知识候选必须经人工审核后生效，历史版本保留。
- Qdrant 不可用时降级为结构化/关键词检索。
- 向量索引可从 MySQL/对象存储中的权威来源重建。
- Sprint 6 失败不影响已发布 MVP。

## 10. 跨 Sprint Gate

| Gate | 检查点 | 不通过处理 |
|---|---|---|
| G0 技术基线 | Sprint 0：ER、OpenAPI、事件、DeepSeek、Flow、Compose | 不进入相关业务实现；缩小或关闭条件功能 |
| G1 核心上下文 | Sprint 1：身份、项目、版本、审计、文件 | 不进入 Requirement 正式化 |
| G2 AI 候选 | Sprint 2：任务、追溯、人工确认、恢复 | 不进入 PRD AI 生成 |
| G3 正式产物 | Sprint 3：PRD 版本与历史保护 | 不发起正式 Design Review |
| G4 验证前置 | Sprint 4：评审、Plan、有效确认轮次 | 不创建正式 Test Record |
| G5 MVP 发布 | Sprint 5：T01～T07、NFR、备份恢复 | 不上线或回退到上一个候选版本 |
| G6 增强发布 | Sprint 6：知识审核、Qdrant 降级 | 保持增强旗标关闭 |

## 11. 变更控制

- Sprint 内发现正式设计冲突时，任务转为 blocked，并记录来源、影响和候选处理；不得自行重写产品口径。
- 新功能进入 MVP 必须说明替换掉的工作量；禁止只增加范围不调整容量。
- Flow、知识中心、分析与多 Provider 均使用功能旗标，不允许以半完成状态进入主链。
- Sprint 5 后新增功能进入后续版本，发布候选只接受阻断缺陷、安全和数据完整性修复。
