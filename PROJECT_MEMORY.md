# PROJECT MEMORY

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

物理设计目标为 MySQL 8.0、InnoDB、utf8mb4、BIGINT UNSIGNED 主键、DATETIME 时间、VARCHAR(32) 状态、JSON 配置；向量数据库初期建议 Chroma、后期 Milvus，MySQL 的 vector_embedding 仅作逻辑映射。

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

## 10. API 设计记忆

API 采用 REST，统一前缀 `/api/v1/`，统一返回 `{code, message, data}`；常规能力以资源式 API 为主，评审提交、确认、版本派生等使用显式业务命令。查看版本、设置当前工作版本和基于历史派生必须分离。业务调用由 Frontend → Business API → Service → MySQL，AI 调用由 Business API → AI Agent API → Skill/Context/Knowledge/LLM → Result → Database。

已覆盖用户、项目/项目版本、Requirement、PRD、Review、Flow、Implementation、Test/Issue/Bug/Optimization、File、Agent、Skill、Experience/Checklist、Template、Context 和 Module Config。现有设计是资源清单级草案，字段级请求/响应、鉴权、分页、幂等、错误码和异步协议仍待后续阶段确认。

## 11. 页面功能结构记忆

当前基线只定义功能信息架构，尚未进入交互或 UI：

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
| 埋点与数据方案 | `数据埋点与数据库设计方案.docx`（0 字节） | 正式数据闭环四文档 | 产品层已补齐；字段级技术方案仍为后续资料缺口 |

后续按“当前领域主责文档 → PROJECT_MEMORY 摘要 → PROJECT_STATUS 阶段状态”的单向引用维护，不再由历史开发交接文档反向定义当前口径。

## 14. 文档维护规范

- 新任务先读 `PROJECT_STATUS.md`，再读本文，并回到 `产品设计体系整理/` 对应领域主责文档核实细节。
- `PROJECT_MEMORY.md` 只保存稳定结论、跨文档关系和长期规则，不替代字段级设计。
- `PROJECT_STATUS.md` 只记录阶段、完成项、当前任务、禁区、阻塞和下一阶段。
- 新增或调整设计时，先识别唯一主责文档，再更新所有引用/汇总文档和状态。
- 决策记录中“暂定/待决定”的事项不得在实现中自行冻结。
- 阶段完成后同步更新状态；涉及 Git 文件时结束前检查提交条件并征求 Commit/Push 确认。

## 15. 当前资料限制

- `数据埋点与数据库设计方案.docx` 和 `项目开发规划与MVP路线.docx` 为 0 字节，无法读取。
- 项目内不保留通用 Skill 副本；3 个产品设计 Skill 已归入用户级 External Skill 库。Template/Prompt 目录仍未建立；通用 `project-base` 模板未用于重建本项目。
- 历史 Word 文档的内容已完成结构化全量读取；因环境缺少 LibreOffice，未做页面视觉核对。本阶段正式输出均为 Markdown。
