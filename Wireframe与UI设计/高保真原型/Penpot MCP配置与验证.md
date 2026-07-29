# Penpot MCP 配置与验证记录

## 决策

- 当前设计主路径：Penpot 官方 MCP。
- Figma 路径：暂停；未来仅在官方额度或权限恢复后同步核心展示页面。
- 不使用第三方 Penpot MCP，不绕过 Figma 套餐或调用限制。
- 不修改已确认的产品、交互、页面状态机和 Wireframe。

## 官方来源

- 官方帮助文档：https://help.penpot.app/mcp/
- 官方产品页：https://penpot.app/penpot-mcp-server
- 官方源码：https://github.com/penpot/penpot/tree/develop/mcp
- 官方 npm 包：https://www.npmjs.com/package/@penpot/mcp

## 版本与许可证

- npm 包：`@penpot/mcp`
- 稳定通道：`@stable`
- 核验版本：`2.15.4`
- 许可证：MPL-2.0
- 核验日期：2026-07-27

## 环境检查

- 安装前未发现 Penpot MCP 工具或配置。
- Node.js：`v24.14.1`。
- npm / npx：`11.11.0`。
- Codex 用户配置：`C:\Users\10238\.codex\config.toml`。

## 官方本地模式评估

- 启动命令：`npx.cmd -y @penpot/mcp@stable`
- MCP 端点：`http://localhost:4401/mcp`
- 插件清单：`http://localhost:4400/manifest.json`
- 本地模式不使用 MCP Key，依赖当前 Penpot 浏览器会话。
- 结果：包下载完成，启动失败。
- 失败原因：pnpm 11 阻止 `esbuild` 与 `sharp` 构建脚本，返回 `ERR_PNPM_IGNORED_BUILDS`。
- 安全处理：未执行 `pnpm approve-builds`，未放宽全局依赖脚本策略，未改用第三方实现。
- 官方兼容性说明：Penpot 文档声明 Node.js v22 为已测试版本；当前环境为 Node.js v24。

## 官方远程模式评估

- 官方 SaaS：https://design.penpot.app/
- 远程端点格式：`https://design.penpot.app/mcp/stream?userToken=<MCP_KEY>`
- 当前状态：已登录，已启用官方 MCP Server，已生成 MCP Key。
- 安全约束：MCP Key 不写入项目文件、日志或 Git；仅保存到 Codex 用户级 MCP 配置。

## Codex 用户级配置

- 配置节：`[mcp_servers.penpot]`
- 配置文件：`C:\Users\10238\.codex\config.toml`
- 官方 URL 前缀校验：通过。
- 配置节唯一性校验：通过，仅 1 个 Penpot MCP 配置。
- 配置备份：`C:\Users\10238\.codex\config.toml.penpot-backup-20260727`
- 临时凭据文件：已删除。
- Key、完整 URL：不记录在项目文件中。

## 测试文件与连接

- 测试文件名称：`新建文件 1`。
- 文件 ID：`bd31e32d-d69f-81e2-8008-6403c41c6a83`
- 页面 ID：`bd31e32d-d69f-81e2-8008-6403c41c6a84`
- Product UI 工作区：https://design.penpot.app/#/workspace?team-id=bd31e32d-d69f-81e2-8008-63fe4b53bfae&file-id=bd31e32d-d69f-81e2-8008-6403c41c6a83&page-id=0b6cce22-0755-8065-8008-64eb314e889c
- Penpot 页面状态：已登录，官方 MCP 连接成功。
- Penpot Plugin API 版本：`2.17.1`。
- Codex 工具注册：通过，已识别 `execute_code`、`high_level_overview`、`penpot_api_info` 和 `export_shape`。

## 计划配置

完成 Penpot 登录并在 `Your account → Integrations → MCP Server` 启用后，将官方远程 URL 配置为用户级 `penpot` MCP。配置完成后重新加载 Codex 工具，并验证官方工具：

- `execute_code`
- `high_level_overview`
- `penpot_api_info`
- `export_shape`
- `import_image`（远程模式能力受限）

## 最小写入验证

验证日期：2026-07-28。

验证结果：通过。执行范围严格限定为：

1. 复用已创建的测试文件，并核对文件 ID 与页面 ID；
2. 创建临时画板 `MCP_MIN_WRITE_20260728`；
3. 在画板中创建测试文字 `Penpot MCP 最小写入验证` 和矩形；
4. 将矩形填充色从 `#D8D5CF` 修改为 `#E6D9C7`；
5. 读取节点结构、文字内容和修改后的颜色，验证成功；
6. 精确删除本次临时画板及其子节点；
7. 清理后查询同前缀节点，剩余数量为 `0`；
8. 页面原有 `Board` 未修改；未创建 Token、组件或正式页面。

最小验证停止点已于 2026-07-28 经人工确认解除，随后进入 Phase 1 核心样板搭建。

## Phase 1 核心样板写入

执行日期：2026-07-28。

### 三层页面结构

| Page | Page ID | 已写入内容 |
|---|---|---|
| `Foundations` | `bd31e32d-d69f-81e2-8008-6403c41c6a84` | Cover & Guide、Color & Semantics、Type & Metrics |
| `Components` | `0b6cce22-0755-8065-8008-64eb31495a84` | Button、Input、Tabs、Modal、AI Status 五类核心组件样板 |
| `Product UI` | `0b6cce22-0755-8065-8008-64eb314e889c` | PRD Candidate Review 核心页面样板 |

Starter 三 Pages 限制通过 Page 内 Board/Section 分区处理；未继续尝试创建第 4 个 Page。

### Foundations 与 Token

- 已创建 `Primitives`、`Semantic Light`、`Metrics` 三组共 98 个活动 Token。
- 色彩语义：Sage 为主操作；Apricot 仅表示 AI 身份与候选差异；Amber 表示一般提醒；Red 表示错误、拒绝和删除。
- 已写入颜色、字体、间距、圆角、控件尺寸、布局和阴影的可视化样板。
- 项目内同步导出 `../UI设计/design-tokens.json`，作为可追踪的机器可读副本。

### 首批五类组件样板

- Button：Primary 的 Default、Hover、Disabled、Loading；Secondary；段落级接受/编辑/拒绝；整篇级拒绝。
- Input：Default、Focus、Error，并统一 40px 高度、8px 圆角和 1px 边框。
- Tabs：Default、Hover、Selected、Disabled。
- Modal：Medium 确认样板，包含影响说明、Amber 提醒、取消和唯一确认主操作。
- AI Status：Queued、Generating、Ready、Blocked、Failed、Stale；状态同时使用文字和语义色，不只依赖颜色。

本阶段只建立样板和五个本地库组件入口，未批量扩展全部 16 个组件家族。

### 核心页面样板

- Board：`V1 / Core Sample / PRD Candidate Review`
- Board ID：`0980eda0-aca4-80c0-8008-651e7e42d50d`
- 画板：1440 × 1024，共 169 个一级子节点。
- 顶部保留段落级 `接受本段 / 编辑 / 拒绝本段`；底部保留整篇级 `拒绝全部 / 保存候选草稿 / 修改后采用`，其中 `修改后采用` 为唯一主按钮。
- 任务条明确显示 `当前正在审核：1.1 背景与目标` 与 `第 1/12 段`。
- 对比区只对真正变化的词句使用局部标识，并区分 `新增 / 修改 / 删除`。
- 右侧栏保持“来源可追溯”展开、“质量检查”摘要、“业务规则命中”折叠。
- 视觉参考保存在 `V1视觉方向参考-PRD候选审核合并稿.png`；该图片是方向参考，不是 Penpot 导出件。

### 验证结果与限制

- `penpot.currentFile.validate()`：通过，返回空问题集。
- 页面根节点越界检查：通过，无越界节点。
- 重复名称检查：通过，无重复名称。
- Penpot PNG 与 SVG 自动导出：本次网络调用均在 30 秒超时，未获得正式导出件。
- 浏览器截图：网络超时，未完成自动视觉截图 QA；不能据此宣称像素级视觉验收通过。
- 文件名称仍为 `新建文件 1`；当前 Plugin API 的文件名称为只读，需在 Penpot 界面人工重命名为 `AI 产品设计与验证平台 — Design System & UI`。

验收结果：用户于 2026-07-28 确认该核心样板可升格为 V1 正式视觉基线。后续页面沿用其布局、颜色语义、操作层级和组件规则。

当前停止点已于 2026-07-28 由用户“开始全量设计”指令解除。

## 全量高保真写入与校验

### 设计源规模

| Page | 顶层 Board | 节点数 | 主要内容 |
|---|---:|---:|---|
| `Foundations` | 4 | 216 | Cover、颜色语义、字体与度量、Grid/Accessibility/Delivery |
| `Components` | 25 | 850 | 16 个基础组件家族、14 个业务 Pattern 的样板与库入口 |
| `Product UI` | 22 | 2130 | 核心样板、11 个页面族模板、页面覆盖、状态画廊、AI 生命周期、原型与全局覆盖层 |

本地组件库共 30 个组件入口：16 个基础组件和 14 个业务 Pattern。页面设计继续复用 Phase 1 的 Sage / Apricot / Amber / Red 语义、40px 常用控件、8px 常用圆角和暖灰边框。

### 页面、状态与原型

- `V1 / Page Coverage / 43 Pages` 明确覆盖 PC01～08、PD01～15、IC01～06、PV01～05、KC01～04、SS01～05，共 43/43 个页面编号。
- 11 个高保真页面族模板与已确认低保真 Wireframe 的模板复用规则一致。
- 3 个 Page States Board 共展示 43 个代表状态；不把 134 个状态机械复制为 134 张整页。
- `V1 / AI Lifecycle / Before, During & After` 展示 AI 生成前配置、生成中反馈、生成后差异审核与保存入口。
- `V1 / Prototype Flows / T01-T07` 提供 7 个流程入口；文件内共验证到 16 条 `click → navigate-to` 交互。
- Review 与 Implementation Confirmation 保留阻断守卫，未把未满足条件的动作设计为可点击主操作。

### 最终结构校验

- `penpot.currentFile.validate()`：通过，返回空问题集。
- 同级重复名称检查：通过，0 项。
- 本地组件计数：30。
- 原型交互计数：16。
- Penpot PNG/SVG 正式导出：再次尝试仍在 30 秒网络窗口超时，未生成可登记的正式导出件。
- 浏览器可连接并显示当前文件，但远程截图在桌面视口切换后超时；因此本记录不宣称全量稿已完成像素级自动 QA，阶段验收仍需人工查看 Penpot 源文件。

全量高保真稿当前为待人工验收候选；验收通过后再更新 `PROJECT_MEMORY.md` 并决定是否进入开发规划。

## 后续设计结构

- Foundations
- Components
- Product UI

## 最终交付

- Penpot 可编辑设计源文件
- `design-tokens.json`
- SVG
- PNG
- 高保真原型
- `UI设计方案.md`
- `设计系统规范.md`

当前交付状态：Penpot 可编辑源文件、`design-tokens.json`、V1 正式视觉基线、全量高保真候选和原型入口已具备；正式 SVG、PNG 仍受网络超时阻塞，阶段人工验收待完成。
