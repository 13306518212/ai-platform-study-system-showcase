# 人工智能平台产品实现（初级）学习系统 · 公开展示

项目标识：`ai-platform-study-system-showcase`

这是“人工智能平台产品实现（初级）学习系统”的公开展示和可运行学习版本，包含完整理论学习助手，以及一套题量精简但功能完整的 JupyterLab 实操训练。

> <span style="color:#b91c1c"><strong><u>重要提醒：本项目是学习辅助工具，不代表官方考试题库或评分标准。</u></strong></span>
>
> 理论题和实操练习用于知识点复习、代码理解和答题方法训练，不能替代官方考试要求，也不能据此保证通过考试。

## 项目定位

系统面向中国大陆地区的人工智能工程技术人员（人工智能平台产品实现-初级）备考场景，形成“理论理解 → 实操填空 → JupyterLab 运行验证”的本地学习流程。

完整题库版本：

- Private 仓库：[ai-platform-study-system](https://github.com/13306518212/ai-platform-study-system)
- 公开展示仓库保留理论全量内容和 13 道实操题；Private 仓库保留完整实操题库。

## 功能概览

- 理论学习助手：约 800 道理论题，包含知识梳理、题目练习、解析和学习记录。
- JupyterLab 实操训练：公开版包含 13 道实操题，使用完整的填空判分、代码运行验证、Tab 补全和学习记录功能。
- 学习记录：今日练习、专项练习、错题复习和模拟考试。
- 学习导航：理论助手与实操 Notebook 之间互相跳转。
- 本地优先：题库、判分和学习记录在本机运行。

## 页面与架构预览

![系统架构](docs/architecture.svg)

### 理论学习助手

![理论学习助手](docs/screenshots/theory-assistant.png)

### JupyterLab 实操训练

![JupyterLab 实操训练](docs/screenshots/practical-jupyterlab.png)

### 代码注释与学习提示

![代码注释与学习提示](docs/screenshots/practical-commented-code.png)

### 填空提示与原生补全

![填空提示与原生补全](docs/screenshots/practical-fill-hints.png)

## 直接体验理论学习助手

理论学习助手文件位于 [`theory/index.html`](theory/index.html)，下载仓库后可直接在浏览器打开。

macOS / Linux：

```bash
open theory/index.html
```

Windows：双击 `theory/index.html`，或在浏览器中选择“打开文件”。

理论页面中的“进入实操训练”入口指向本地 JupyterLab 地址。使用前请先启动实操入口。

## 启动公开版实操训练

公开版实操训练位于 [`practical/`](practical/)：

1. 安装 Python 3.9+ 和 JupyterLab。
2. 在仓库根目录安装依赖：

   ```bash
   python3 -m pip install -r requirements.txt
   ```

3. macOS 双击 [`practical/打开考试.command`](practical/%E6%89%93%E5%BC%80%E8%80%83%E8%AF%95.command)，或在终端运行：

   ```bash
   python3 practical/start_jupyter.py
   ```

4. 打开终端显示的本机地址，进入 Notebook 后运行唯一启动单元。

详细说明见 [`practical/使用说明.md`](practical/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)。

## 公开版实操题库

公开版实操题库包含 13 道题、60 个填空位，分类为：

- Python：5 道；
- Pandas：3 道；
- 机器学习：1 道；
- 系统运维：4 道。

这些题目使用完整的题目数据、答案校验、语法检查、运行验证、学习记录、复测和模拟考试逻辑；只是题目数量少于 Private 完整版本。题目不会进入单独的“样题模式”，启动后直接按普通实操系统运行。

## 公开仓库与完整仓库的边界

本仓库公开：

- 完整理论学习助手及理论题集；
- 13 道实操题及其完整判分和运行验证逻辑；
- Notebook、补全脚本、启动脚本和使用说明；
- 项目说明、系统架构图和界面截图。

Private 仓库额外保留完整实操题库和内部维护材料。公开仓库和 Private 仓库使用同一套实操系统逻辑，差异主要是题目数量。

## 内容与法律说明

- 本项目不是官方考试平台，也不代表任何考试组织、培训机构或题库平台。
- 题目、解析和学习说明是用于学习的整理与改编内容，不保证与实际考试题面、留空方式或评分标准完全一致。
- 理论题及实操题公开前，维护者应确认拥有相应的整理、改编和再分发权限；第三方教材、试卷、商标和参考材料的权利归原权利人所有。
- 如发现内容涉及侵权或不适合公开，请通过 [GitHub Issue](https://github.com/13306518212/ai-platform-study-system-showcase/issues) 联系维护者，说明具体文件和原因，以便核查、删除或更正。

公开展示内容的使用范围见 [CONTENT-LICENSE.md](CONTENT-LICENSE.md)，第三方内容说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 版本与状态

公开展示仓库与完整训练仓库相互独立。本仓库提供可运行的公开学习版本；Private 完整训练仓库保留全量实操题库。
