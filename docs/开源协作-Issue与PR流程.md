# 开源协作：Issue 与 Pull Request 流程

> 本文件记录参与开源项目的标准动作，以及本项目实际提交时的取舍。命令以 Git Bash / PowerShell 为例。

## 一、准备：Fork → Clone → 建分支

```bash
# 1. 在 GitHub 上 Fork 目标仓库到自己账户（页面右上角 Fork）
# 2. 克隆自己账户下的副本
git clone https://github.com/<你的用户名>/<项目名>.git
cd <项目名>

# 3. 基于主分支建一个语义明确的分支
git checkout -b fix-login-bug
```

分支命名约定：

| 前缀 | 用途 | 例子 |
| --- | --- | --- |
| `fix/` | 修缺陷 | `fix/login-redirect-loop` |
| `docs/` | 文档 | `docs/add-readme` |
| `feat/` | 新功能 | `feat/export-csv` |
| `test/` | 测试 | `test/cover-empty-input` |

建议再挂一个 upstream，方便同步上游：

```bash
git remote add upstream https://github.com/<原作者>/<项目名>.git
git fetch upstream
```

## 二、Issue：先检索，再描述

**提交前必须做的一步是查重**——重复的 Issue 会被直接关闭，还会消耗维护者的注意力。

1. 用错误信息、功能名、模块名做关键词搜索（GitHub 搜索框或项目 Issues 页）。
2. 浏览 Issue 列表与已关闭的 Issue；找到同类就**在原有 Issue 下补充信息或表态支持**，不要新开。
3. 标题写成「**标签 + 具体描述**」，例如 `[Bug] 解析空文件时抛 IndexError`，而不是 `出错了`。
4. 正文按「现象 → 复现步骤 → 期望结果 → 实际结果 → 环境 → 影响面」组织。
5. 选对类型：Bug（不符合预期的行为）/ Feature（新需求）/ Task（具体工作项）。选错类型常被直接关掉。

**一个反例值得记住**：排查 `aboutcode-org/scancode-toolkit` 的 Markdown 链接时，脚本给出 30 处「失效链接」，但全部落在
`tests/licensedcode/data/datadriven/` 下——那是喂给许可证检测器的**测试夹具**，里面的相对链接本来就是断的。
把它当 bug 提，维护者会当作噪音关闭。**能自动扫出来的问题，先人工判断它是不是问题。**

## 三、Pull Request：小步、可读、可回滚

- **一个 PR 只做一件事**。顺手重构、顺手改格式会让评审无法聚焦。
- 提交信息用「类型(范围): 描述」，例如 `docs: 补充 README 的收录状态说明`。
- PR 描述写清四件事：改了什么 / 为什么改 / 怎么验证 / 影响面。
- 关联 Issue：在描述里写 `Closes #12`，合并时会自动关闭该 Issue。
- 冲突处理用 rebase 而不是 merge 上游，保持历史线性：

```bash
git fetch upstream
git rebase upstream/main
git push --force-with-lease
```

## 四、评审与合并

- 等待 review；需要修改时**在同一个分支追加提交**，PR 会自动更新。
- 被要求 squash 时按维护者的方式处理，不要争论提交历史风格。
- 合并后删除分支：

```bash
git push origin --delete <分支名>
```

## 五、本项目的实际记录

**案例：向同学仓库提交 PR（`18121152132/learning-support-project`）**

| 步骤 | 实际动作 |
| --- | --- |
| Fork | `yaolingyu0531/learning-support-project` |
| 分支 | 从 `main` 拉 `docs/add-readme` |
| 改动 | 只新增 `README.md`，+44 行、−0 行 |
| PR | `yaolingyu0531:docs/add-readme → 18121152132:main` |

**遇到的一个非标准情况**：该仓库关闭了 Issues 功能，创建 Issue 时接口返回 `410 Issues has been disabled`。
处理方式是**把 Issue 正文改写成 PR 评论**贴在 PR 下方，而不是换用别的通道刷存在感。如果对方之后开启 Issues，
再把评论转成正式 Issue 并互相引用。

**取舍原则**：改动尽量小、可解释、可一键关闭。对方不接受时，直接关掉 PR 即结束，不需要来回拉扯。

## 六、提 PR 前的自查清单

- [ ] 分支基于上游最新主分支
- [ ] 只做了一件事，没有夹带无关改动
- [ ] 提交信息符合项目约定
- [ ] PR 描述能让人不看代码就明白动机
- [ ] 关联了 Issue（若有）
- [ ] 本地跑过项目的测试或至少跑通改动的路径
- [ ] 没有提交本地配置、密钥、编译产物
- [ ] 已知的行为变化写进描述（尤其是不兼容改动）
