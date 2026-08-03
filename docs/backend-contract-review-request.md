# Sprint 1 前端后端契约审查请求

状态：Review 冻结 OpenAPI 已生成 Client；静态请求映射可验证，真实 MySQL 8.4 与 MinIO/S3 联调 Gate 尚未完成。

冻结输入：`packages/contracts/openapi/openapi.json`，SHA-256 `765085b584de8bf22b1a2724b0e4745fa3c8b2db7c16a7ead77c38d736917f1e`。

| 页面/任务 | 已接入 | 尚缺契约或运行条件 | 阻塞影响 |
|---|---|---|---|
| FE-101 登录/注册 | register、login、refresh、logout、session；Cookie 与 Bearer 边界；统一错误/trace | CSRF 开启时 token 的浏览器读取来源尚未说明 | 开启 double-submit CSRF 后 refresh/logout 需补 header 获取方式 |
| PC-01～03 项目 | list、create、detail；V1 成功跳转；幂等键；数字 optimistic version | 项目概览的 next step/blocker 没有对应响应字段 | 真实概览只展示契约已有字段，不猜测 blocker |
| PC-06～08 版本 | list/detail、set-working；历史查看与工作版本操作分离 | `change_type` 与 `inheritance_choices` 的允许语义值未冻结 | 真实模式阻止 derive，避免提交猜测值 |
| PC-04～05 文件 | init、签名 PUT、complete、abort；SHA-256；失败条目与重试 | 项目级文件列表端点缺失；`object_type`、`relation_type` 允许值未冻结；真实 MinIO/S3 Gate 未通过 | 刷新后无法恢复列表；真实模式阻止关联；不能宣称端到端上传通过 |

## 请求 Review/后端确认

1. 冻结版本派生 `change_type` 与 `inheritance_choices` 的允许值及含义。
2. 冻结文件关联 `object_type` 与 `relation_type` 的允许值，并确认 PC-05 可选项来源。
3. 提供项目文件列表/恢复端点，或明确 PC-04 刷新后的恢复策略。
4. 明确部署启用 double-submit CSRF 时 `X-CSRF-Token` 的安全获取方式。
5. 完成真实 MySQL 8.4 与 MinIO/S3 Gate 后提供联调环境；此前仅报告静态契约与 Mock 验证。
