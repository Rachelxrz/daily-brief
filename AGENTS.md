# AGENTS.md — 分工与协作规范

> 本文件定义三个协作角色的职责边界和工作流程。
> 每个角色开始工作前必须读 CLAUDE.md 获取项目全局状态。

---

## 三个角色

### 🧠 Claude (claude.ai) — 策略大脑
**工具**: 浏览器对话 + 联网搜索

**职责**:
- 市场分析、宏观判断、投资逻辑推理
- 设计新模块的功能规格（输出 spec.md）
- 解读国会交易数据、给出持仓建议
- 更新 CLAUDE.md 中的项目状态（告诉 Claude Code 下一步做什么）
- 回答"为什么"的问题

**不做**:
- 不直接写入本地文件（通过生成内容让用户保存）
- 不运行代码
- 不调试 GitHub Actions

---

### 💻 Claude Code — 编码执行者
**工具**: 命令行，直接访问代码仓库

**职责**:
- 读 CLAUDE.md + 对应模块的 spec.md，理解任务
- 写 Python 代码、GitHub Actions YAML
- 本地运行测试，调试错误
- Push 代码到 GitHub
- 更新对应模块的 status.md（标记完成项）

**开始工作的标准流程**:
```
1. cat CLAUDE.md                          # 读总纲
2. cat AGENTS.md                          # 读分工
3. cat modules/<模块名>/spec.md           # 读规格
4. cat modules/<模块名>/status.md         # 看当前进度
5. 开始编码
6. 完成后更新 status.md
```

**不做**:
- 不自行设计功能（功能设计由 Claude 负责）
- 不修改 spec.md 的功能要求（有疑问先标注，问用户）

---

### 📁 Cowork — 文件管理员
**工具**: 桌面应用，访问本地文件系统

**职责**:
- 将 Claude 生成的文档保存到本地正确目录
- 更新 status.md 中的进度记录
- 整理 logs/ 目录
- 在 Windows 和 Ubuntu 工作站之间同步文件

**不做**:
- 不写代码
- 不做投资分析

---

## 标准工作流（以新模块为例）

```
Step 1 [Claude]
  → 设计模块规格
  → 生成 spec.md 内容

Step 2 [用户/Cowork]
  → 将 spec.md 保存到 modules/<模块名>/spec.md
  → 创建 status.md（初始状态）

Step 3 [Claude Code]
  → 读 CLAUDE.md + spec.md
  → 实现代码
  → 测试运行
  → Push GitHub
  → 更新 status.md

Step 4 [Claude]
  → 解读输出结果
  → 给出投资建议
  → 如需迭代，更新 spec.md
```

---

## 模块目录结构规范

```
modules/
└── <模块名>/
    ├── spec.md      ← 功能规格（Claude 写，不轻易改）
    ├── status.md    ← 进度追踪（Claude Code 维护）
    └── README.md    ← 模块说明（可选）
```

---

## 当前任务队列

| 优先级 | 模块 | 负责角色 | 状态 |
|--------|------|----------|------|
| 🔴 高  | 国会交易信号 | Claude Code | 待开始，规格已就绪 |
| 🟡 中  | RAG 知识库集成 | Claude Code | 规划中 |
| 🟢 低  | 本地 Qwen 路由 | Claude Code | 待规划 |
