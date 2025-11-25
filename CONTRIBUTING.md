#贡献指南 (Contributing to Py-Proxy / DZView)

感谢你愿意为本项目做出贡献。以下流程与约定帮助保持代码质量与一致性。

## 快速开始
1. Fork 仓库并创建个人分支 (避免直接在 main 上开发)。
2. 克隆你的 Fork：`git clone <your-fork-url>`。
3. 创建虚拟环境：`python -m venv venv && source venv/bin/activate` (Windows 使用 `venv\Scripts\activate`).
4. 安装依赖：`pip install -r test/py_proxy.egg-info/requires.txt`。
5. 本地运行：`python test/main.py` 或 `uvicorn test.main:app --reload`。

## 分支策略
- main: 稳定分支，仅合并测试通过的功能。
- feat/xxx: 新功能 (例如: `feat/rate-limit-refactor`).
- fix/xxx: 缺陷修复。
- docs/xxx: 文档改进。
- refactor/xxx: 重构（不改变外部行为）。

## 提交信息规范
提交使用前缀 + 简述 (推荐英文)：
- feat: 新功能
- fix: 修复问题
- docs: 文档更新
- refactor: 重构
- perf: 性能优化
- test: 测试相关
- chore: 杂项（构建脚本、依赖更新等）
示例：`feat: add websocket push for admin metrics`。

##代码规范
- Python版本建议 >=3.10。
- 使用 ruff 做静态检查：`pip install ruff && ruff check .`。
- 保持函数短小、单一职责；新增模块放入 `test/`目录中与现有结构保持一致。
- 避免引入未使用的依赖；如需新增第三方库，请在 PR 中说明理由。

##目录说明
- `test/main.py` 应用入口。
- `test/proxy.py` 核心代理逻辑与速率限制实现。
- `test/admin.py` 管理后台与配置接口。
- `test/metrics.py` 流量统计。
- `test/security.py` 安全与域名匹配逻辑。
- `static/` 可选前端页面。

## 功能开发建议
如实现扩展功能（例如改进速率限制为令牌桶、增加 Redis 支持）：
1.先提交 Issue说明动机与设计概要。
2. 获得认可以后再开发，以免重复工作。
3. 编写最小可行代码并附带使用说明。

## 测试
- 基础逻辑单元测试可放置于 `tests/`目录（若不存在可创建）。
- 异步函数测试使用 `pytest` + `pytest-asyncio`。
- 对关键路径 (代理成功 / 超时 /429 /403 /413) 编写测试用例。

## 文档
- 修改行为的 PR 应同步更新 `README.md`。
- 如果新增配置项，说明其环境变量或 API 调整。

##速率限制模块注意事项
当前为固定时间窗口简单计数：
- 不适用于多进程/多实例分布式场景。
- 如需横向扩展，可新增 Redis 后端或在 PR 中引入可插拔接口层。
- 在 `proxy.py` 中保持旧接口兼容 (`get_rate_limit_config`, `update_rate_limit_config`).

## 提交 PR 流程
1.通过 `git fetch origin && git rebase origin/main` 保持分支最新。
2. 执行本地测试与静态检查。
3. 填写 PR 描述：变更目的 /主要修改点 / 是否有破坏性变化。
4. 标注关联 Issue：`Closes #<issue-number>`（如适用）。
5. 等待 Review，通过后再合并（一般使用 Squash & Merge 保持历史整洁）。

## Issue 指引
创建 Issue 时请包含：
- 环境信息 (OS, Python版本)
-复现步骤
-期望结果 vs 实际结果
- 日志片段或堆栈 (如有)

## 行为准则
请保持尊重与专业，避免人身攻击。遵守通用开源社区交流礼仪。

## License贡献说明
提交代码默认视为与项目现有 License (MIT) 一致并同意其分发条款。

## 联系
如需讨论架构或重大调整，请先在 Issue 中提出，再进入实现阶段。

欢迎你的贡献！