# 提示词 · 实习反馈受限整理与教学改进辅助系统（v5）

> 用法：§0–§12 是提示词正文，整段复制给编码 Agent。文末「附录」不要复制。
> 依据：`docs/` 下 36 条访谈事实（education-f00…f55）、业务挖掘报告、现场调研报告、FDE 九阶段记录、现状流程图、`知行-实习反馈-业务机会/业务机会清单.html`。
> v5 变更：模型固定为 Ollama 本地部署的 **Qwen3-8B**（`qwen3:8b`）；新增 thinking 开关、显存预算、8B 能力边界与故障模式表（§4.3）。

---

## 0. 元规则（违反任一条即停下问我）

1. 这是**受控执行系统**：Harness 给能力边界，知识库与知识图谱给事实与关系，人工闸门给最终决定权。三者缺一，它就退化成"一个会写建议的聊天框"。
2. 不得替换技术栈、不得引入清单外依赖、不得加中间件。有更好的方案，用一行写在回复末尾申请，不要直接改。
3. **拿不到的信息不许猜**。缺字段写 `TODO(待确认: …)`，交付里汇总；不许用默认值、示例值、mock 数据悄悄补上。假数据只允许进 `tests/fixtures/`，文件名带 `synthetic`。
4. 我的要求与 §7 红线冲突时，停下来问，不许折中、不许"先实现后提醒"。
5. 回答用中文；代码、表名、字段名、工具名用英文。不要输出"我已完成"而不给可运行命令。
6. **现在不要写代码**，按 §12 先对齐。

---

## 1. 项目背景（来自已完成调研，不要重新发明）

- 客户：知行职业学院 · 产教协同办公室。样本：机电专业 + 5 家企业。预算 12 万元。周期：4 周最小验证，先历史回放、再并行试点，**不关停现有人工流程**。
- 客户原话："企业说学生能力不够，老师觉得评价太笼统。希望用 AI 整理实习反馈、发现教学改进需求。"
- 已确认诊断：客户以为病在"整理慢"，实际三处病根——**换岗后反馈发错人**、**企业说不出哪个岗位任务没做好**、**建议落不到具体课程**。三处不修，整理得越快，糊涂账抄得越整齐。
- 顺序固定：先修管道（口径 → 岗位任务模板字段 → 换岗重关联 → 双周节拍 → 只读 ID 映射），再装泵（受限 AI 整理）。**首期不做自动评价、不做成绩写回**。
- `fNN` = 访谈证据编号，可写进代码注释与报告，不要改写、不要新增编号。

### 1.1 事实清单与代码硬含义

| 编号 | 事实（访谈口径，未按样本验证） | 落到代码上的硬含义 |
| --- | --- | --- |
| f00 | 600 人/学期；完整率 54%，目标 85% | 阈值进 config 并标注"待业务签发"；分母由口径卡定义，禁止硬编码 |
| f01 | 链路：企业评分→教师回访→教务汇总→专业组评审；建议常没落到课程 | "落到课程"= 建议必须能连到 `course_id`；连通性由图谱 Q1 判定 |
| f10 | 企业只写"沟通能力不足"，不落到岗位任务 | 岗位任务必填；候选任务来自 KB-K1；缺失即 `needs_review` |
| f11 | 换岗/延期后仍关联旧导师，反馈发错人 | `assignments` 有效期 + 变更记录；换岗未确认 → 闸门停 |
| f12 | 30 人/师，每月约 10 小时整理三渠道 | 工时拆四类（搬运/核对/回访/其他），不许只记总数 |
| f13 | 现有终端，不能要求重复登录 | 单入口；不做多系统跳转 |
| f14 | 群聊、个人表补录后再回系统 | 必须提供结构化"待补说明 + 最后同步时间" |
| f15 | 每条辅助结果须显示原记录；未经教务核对不得覆盖 | `evidence_ref` + append-only + `confirmed_by/at` |
| f20 | 确认岗位与导师 → 收集任务表现/事实例子/改进建议 → 专业组确认 | 状态机三段；专业组确认是终态 |
| f22 | 改培养方案须教务委员会；模型不能决定成绩 | 无 grade/score 字段；不做培养方案审批流 |
| f23 | 交接六项 + 接手人确认才结束；发消息≠责任转移 | `handoffs` 六字段 + 显式 accept |
| f24 | 规则由业务负责人维护，存生效日期与适用范围；争议记版本由教学质量负责人确认 | `rule_versions`/KB/KG 全链路带版本与 `effective_from` |
| f25 | 异常分派须写处理人/截止/退回原因；超时交产教融合负责人 | `review_tasks` 三字段非空 + 超时升级 |
| f30 | 学籍/实习/课程三套 ID 不通 | `mappings` 表；未映射不得进入抽取 |
| f31 | 历史反馈缺岗位任务字段；空值不能当"没问题" | 禁止默认值；`null` + `needs_review` |
| f32 | 仅只读批量导出；成绩写回不在范围 | 红线 R1 |
| f33 | 校验主编号/事件时间/来源/版本；缺字段进修复队列，不猜值 | 四项校验器 + `repair_queue` |
| f34 | 双周刷新；超一周期标待刷新；历史快照不伪装现状 | `period_id` + `fetched_at` + `stale`；KB/KG 均需快照 |
| f35 | 接口失败走原人工流程；留快照+时间戳；恢复后按业务编号去重 | 模型/接口不可用 → 转人工，不 500 |
| f40 | 个体记录限访问；不向其他企业公开 | 红线 R7 租户隔离；图谱不建学生节点（R12） |
| f41 | 能力推断须有行为实例；不以家庭背景、性别解释 | 红线 R2 字段白名单 |
| f42 | 30 条建议 ≥24 条可对应课程、任务、改进负责人 | 24/30 做成自检：**图连通 + 三字段齐备** |
| f43 | 试点记录暂留 90 天，到期确认删除或归档 | 红线 R9 |
| f44 | 五类情形停止自动建议，标明原因、接手人、人工确认时间 | Harness L2 闸门必须返回这三字段 |
| f45 | 审核日志须能重建当次处理 | Harness 每步落 trace，含模型 digest 与快照 id |
| f50 | 双周提交具体任务例子；长问卷会拖到期末 | 反馈表单字段 ≤8 |
| f51 | 企业重设备点检与交接、学校偏理论，口径需共同校准 | 图谱 Q3 把"口径断裂"变成可计算数字 |
| f52 | AI 只整理事实与建议；最终评价由导师确认 | 建议只能是 draft |
| f53 | 分母/周期/排除规则由业务负责人固定；不用消息量代替完成量 | 完整率分子只取"提交且通过校验的反馈" |
| f54 | 投诉须关联原业务编号与版本 | P2，结构预留 |
| f55 | 每周复盘误判与未解决项；复测达标后才更新规则 | 复盘报表：误判类型、未解决项、规则版本 |

---

## 2. 系统定位

一句话：把企业反馈整理成**可追溯到原文、经人确认、且能在"岗位任务→能力→课程"图上连通的改进建议**。系统不产出任何评价结论。

四个部件，各管一件事，不许互相顶替：

| 部件 | 职责 | 不负责 |
| --- | --- | --- |
| Harness（§5） | 工具白名单、步数与预算上限、两级策略、全链路 trace | 不决定"该不该建议"，只决定"能不能执行" |
| 知识库（§6.1–6.6） | 岗位任务模板、课程口径、规则版本；切片检索 | 不判关系、不存学生个体数据 |
| 知识图谱（§6.7–6.8） | 课程—任务—能力—岗位的实体与关系；可对应性判定 | 不做检索、不替代原文引用 |
| 人工闸门（§3） | 确认、退回、停止、签发口径、否决 | 不手工搬数据 |

**目录结构（照此建，不要自创层级）：**

```
src/
  app/
    config.py            # config.yaml 读取与必填校验
    contracts/           # Pydantic：统一响应、领域对象、错误码
    db/                  # SQLAlchemy 模型、Alembic 迁移
    harness/             # 受控执行骨架（§5）
    kb/                  # 知识库（§6.1–6.6）：ingest/chunk/index/retrieve/cite/snapshot
    kg/                  # 知识图谱（§6.7–6.8）：extract/normalize/validate/publish/query
    llm/                 # 模型适配（§4.3）：ollama/openai_compat、健康、降级
    ingest/              # 批量导入、批次登记、幂等、stale
    mapping/             # 三套 ID 映射、四项校验、修复队列
    extract/             # 三字段抽取、原文定位
    review/              # 人工确认队列、交接、异常分派
    suggest/             # 建议草稿、绑定、24/30 自检
    gates/               # f44 停止条件（被 harness L2 调用）
    audit/               # append-only 审计、重建
    metrics/             # 完整率/工时/可执行率/图质量
    web/                 # FastAPI 路由 + Jinja2 页面
    cli.py               # import / kb-ingest / kg-build / refresh / replay / export / retention
  tests/
  scripts/               # verify_m0..m4.py、check_readonly.py、kb_eval.py、kg_eval.py
  config.yaml            # 唯一配置入口
```

**里程碑总览（详见 §10）：**

| 里程碑 | 内容 | 业务门 |
| --- | --- | --- |
| M0 | 契约 + Harness 骨架 + KB/KG schema + Ollama 适配 + 口径卡 v1 + 复算脚本 | G0 |
| M1 | 只读导入 + ID 映射 + 四项校验 + KB-K1 入库建初图 + stale | G3 |
| M2 | 三字段抽取 + 闸门 + 图归一/审核/发布 + 检索与图评测 | G2 前半 |
| M3 | 建议草稿 + 图连通判定 24/30 + `kg_ref`/`evidence_ref` + 审计重建 | G2 判定 |
| M4 | 指标复算 + 30 条回放报告 + 影响面/覆盖率报表 + 导出 | G4 |

**明确不做（写了就是错）：**

- 成绩/学分写回；任何对外部系统的写请求（POST/PUT/PATCH/DELETE）。
- 自动评分、能力定性、学生画像、排名、淘汰或推荐结论。
- 培养方案变更、通用审批流引擎。
- 通用知识图谱平台：不做多模态、不做全网爬取、不做自由问答、不做图神经网络/链接预测。**图只服务 §6.8 的五个查询。**
- 自由对话式入口（要做放 P2，每句强制带引用）。
- 课程改进台账（P2）、投诉工单（P2）、移动端、微服务、K8s、容器编排、消息队列、Redis、图数据库（Neo4j 等）、LangChain/LangGraph、前端构建链。

---

## 3. 用户与权限

| 角色 | 可看 | 可做 | 明确不能 |
| --- | --- | --- | --- |
| 顾明岚 · 产教融合负责人 | 聚合指标、试点看板、口径卡版本、图覆盖率 | 签批口径卡、指定改进负责人、决定扩大或暂停、审核 K3/图 | 不能改评价内容；不能绕过风险否决（f04）；不能追加预算 |
| 林亦舟 · 实习指导教师 | 本人所带学生的反馈与建议 | 确认/退回/补说明、触发停止、审核 K1 与图节点 | 不能越过教务核对；不能定评分口径（f15） |
| 唐映秋 · 教务管理员 | 本批次全部记录 | 签发交接单、异常分派、核对确认、投诉核实 | 不能改成绩与培养方案（f22） |
| 秦芮 · 校园信息工程师 | 字段级元数据、映射表、导入任务、系统指标、模型健康 | 执行导入、修映射、故障快照与去重、执行 KB/KG 构建 | 默认看不到评价正文（脱敏视图）；不做写回（f32） |
| 傅景 · 教学质量负责人 | 全部记录（含个体）、图冲突清单 | 风险否决、验收签核、90 天处置审批、口径争议裁定、审核 K2/K3 | 不能定范围与预算 |
| 叶书 · 企业实习导师 | 本企业学生记录 + 本企业 KB/KG 分区 | 提交双周反馈、受理投诉、核定岗位任务口径 | 不看其他企业记录（f40）；不参与立项；不替导师定性 |
| 专业组 · 评审（只读） | 待审建议 + 依据 + 原文 + 引用片段 + 图路径 | 标记可执行/不可执行并写原因 | 不能改原文、建议正文、KB、KG |
| 学生 · 数据主体（P2） | 本人记录 | 申请更正 | 不能看他人记录 |

实现要求：

1. FastAPI 依赖注入统一出 `Principal{user_id, role, enterprise_id, batch_scope}`，路由里不许自己查角色。
2. 作用域过滤落在**查询层**（SQL where + KB/KG 分区）；不是前端隐藏按钮。
3. 默认拒绝；越权尝试写审计，并进 `E_AUTH_DENIED` 测试。
4. **图的可见性跟随来源文档分区**：企业私有文档抽出的边，只对本企业可见。

---

## 4. 技术栈（不许替换）

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 运行时 | **Python 3.11+** | `requires-python = ">=3.11"`；允许用 3.11 特性，不许写降级兼容代码 |
| Web | **FastAPI** + Uvicorn | 全项目唯一 HTTP 入口 |
| 校验 | Pydantic v2 | 入参、模型输出、KB 命中、图三元组都过 schema |
| 持久化 | SQLAlchemy 2.x + Alembic | 开发 SQLite，试点 PostgreSQL 16；**同一套迁移** |
| 执行骨架 | **Harness（自建，§5）** | 不引第三方 Agent 框架；`HarnessPort` 预留外部运行时适配 |
| 知识库 | **KB（自建，§6.1–6.6）** | 默认字符 bigram BM25；可选 embedding |
| 知识图谱 | **KG（自建，§6.7–6.8）** | 三元组表 `kg_nodes`/`kg_edges` + 递归 CTE；**不引图数据库** |
| 模型运行时 | **Ollama 本地部署（§4.3）** | 默认本地、默认零外发；`llm.provider` 可切 `openai_compat` |
| 前端 | Jinja2 + 原生 HTML/CSS/少量 JS | 不引入 React/Vue/npm 构建链 |
| 鉴权 | 自建 Session + users/roles 表 | 不引入 OAuth/Keycloak |
| 导入 | openpyxl(XLSX)、csv、python-docx(DOCX)、pypdf(PDF) | pandas 只允许在 `scripts/` |
| 测试 | pytest + httpx TestClient | 每个错误码、红线、工具策略、图查询都有用例 |
| 日志 | stdlib logging，JSON 行 | 不引 ELK/OTel |
| 调度 | 不引调度器 | 刷新/建图做成 CLI，交给系统计划任务 |
| 依赖 | 单一 `requirements.txt` 锁版本 | 新增依赖必须先申请 |

### 4.1 FastAPI 约定

1. 所有路由返回 `ApiResponse`，`response_model` 显式声明；全局 `exception_handler` 兜 `E_INTERNAL`，不出 500 堆栈。
2. 配置在 `lifespan` 加载校验，缺项退出码 2；禁止导入期读环境变量。
3. `Annotated[T, Depends(...)]`，不裸写 `Depends`；依赖里不做业务判断。
4. 路由只做：取 Principal → 调 service → 包 `ApiResponse`。业务逻辑禁止写在路由。
5. `/healthz` 必须报告 `{db, llm, kb, kg}` 四态；任何一项 down 时应用**照常启动**、相关能力降级（f35），不许启动失败。
6. 后台任务用 `BackgroundTasks` 且幂等；长任务（建图、回放、导出）一律走 CLI，不挂 HTTP。

### 4.2 Python 3.11+ 约定

1. 枚举用 `enum.StrEnum`；类型用 `typing.Self`；时区用 `datetime.UTC`。
2. `match` 只用于封闭枚举（状态机、错误码、工具名、关系类型），不拿来做业务分支。
3. 递归 CTE 必须用 `sqlalchemy.text()` + `bindparams` 传参；**禁止 f-string 拼 SQL**（含递归深度、起点 id）。
4. 不用 pydantic v1 兼容层；不写 `from __future__ import annotations` 规避真实类型问题。

### 4.3 本地模型部署（Ollama + Qwen3-8B）

**目的**：学生反馈不出校。f40/R6 要求最小化与隔离，最省事的做法就是模型也跑在本地。

1. `llm.provider: ollama`（默认）/ `openai_compat`（仅在获批时启用）；`llm.base_url: http://127.0.0.1:11434`。**不许出现任何公网模型地址。**
2. **模型固定，写进 config，不许硬编码**：
   ```yaml
   llm:
     provider: ollama
     chat_model: "qwen3:8b"        # Q4_K_M 约 5.2GB；本机若装的是 qwen3.5:8b / qwen2.5:8b，只改这一行
     embed_model: "bge-m3"         # 约 1.2GB；qwen3:8b 不是 embedding 模型，别拿它算向量
     num_ctx: 8192                 # Ollama 默认 4096，长反馈会截断，必须显式设
     num_predict: 1024
     temperature: 0
     top_p: 0.9
     seed: 42
     keep_alive: "30m"
     think: false                  # 抽取任务必须关，见第 3 条
     allow_remote: false           # 默认零外发
   ```
3. **必须关 thinking**。Qwen3 是混合推理模型，默认会先输出"好的，我来分析…"，`format` 约束也挡不住思维链文本，JSON 解析必挂。三处同时做，缺一不可：
   - 请求体传 `think: false`（Ollama ≥0.9）；
   - prompt 末尾追加 `/no_think`；
   - 解析层**不做修复**：只要输出不是以 `{` 开头，直接判 `E_LLM_INVALID_OUTPUT`，重试 1 次后转人工。禁止用正则"抠出 JSON"——那是掩盖问题，会让脏数据进库。
   - 例外：生成改进建议时可 `think: true` 提升质量，但必须把 `message.thinking` 与 `message.content` **分开处理**：只有 `content` 进 schema 校验；`thinking` 不入库（里面常带学生原文，违反 R6），最多存 hash 用于排查。
4. **结构化输出用受约束解码**：`/api/chat` 传 `format=<JSON Schema>`，schema 与 Pydantic 模型**同源生成**，禁止两处各写一份。`rel_type`、`node_type`、`field` 一律用 `enum`，模型没有自由发挥空间。
5. **8B 的真实能力边界**（不写清就会反复返工）：
   - 一个 chunk **≤400 字**，一次最多抽 **8 条三元组**、**6 个字段**；
   - 超了就切小 chunk、分批跑，**不要加大 `num_predict`**——8B 输出越长越容易漏字段、串行、把两条记录揉成一条；
   - 抽取用 `temperature 0`；判定"该建议是否可执行"**不许交给模型**，只走 §6.7 的确定性图查询。8B 不具备稳定裁决能力，这是把判定权从模型手里拿走的技术理由，不只是合规理由。
6. **显存预算要算，不要猜**：`qwen3:8b` Q4 + 8k 上下文约 6–7GB，`bge-m3` 约 1.2GB。8GB 卡上两者不要同时常驻：
   - `OLLAMA_NUM_PARALLEL=1`（默认并发会让同一模型加载两次，直接 OOM）；
   - embedding 用完即卸（短 `keep_alive`），或把 `bge-m3` 放 CPU（`num_gpu: 0`）；
   - 启动日志必须打印 `ollama ps` 的显存占用，方便我一眼看出有没有被换出。
   - 若本机无 GPU：8B Q4 在 CPU 上约 4–8 tok/s，**必须先接受"回放过夜"**，不要为了跑通改架构。
7. **版本固定**：`qwen3:8b` 是滚动 tag，今天 pull 的和下周 pull 的可能不是同一份权重。
   - 首次拉取后把 digest 写进 `config.yaml` 的 `llm.model_digest_pin`；
   - 启动时比对，不一致只告警不阻断，但**必须写审计**；回放强制用 pin 的 digest，否则结论不可复算；
   - 每条 `audit_logs` 与 `harness_runs` 都要记 `model` + `model_digest`。
8. 健康与降级：`GET /api/tags` 探活；Ollama 不在线 → `E_LLM_UNAVAILABLE`，该条转人工队列，接口返回 `ok:false` 而**不是 500**（f35）。
9. **默认零外发**：`llm.allow_remote: false`。改 true 需要我书面同意，且必须脱敏 + 逐次审计；`openai_compat` 适配器必须支持"配了但不启用"。
10. **性能与预算**（按 8B 实测口径，别照抄 7B 数字）：单 chunk 抽取输出约 400–800 token，GPU（8G）约 15–30s/次，CPU 约 60–150s/次。因此 `harness.max_steps=8`、单步 90s、单条 240s、回放 `--workers 1` 夜间批跑。超时按顺序降级：`num_ctx 8192→4096` → chunk `400→300 字` → `top_k 8→5`；**不许调大步数、不许换更小的模型凑数**（会让 30 条回放的结论没意义）。
11. 部署脚本：`scripts/setup_ollama.ps1` / `.sh`，内容固定四步：`ollama pull qwen3:8b`、`ollama pull bge-m3`、`ollama run qwen3:8b "/no_think 只回复 OK"` 自检、打印 digest 与 `ollama ps`；不写 Docker。
12. **故障模式表**（8B + Ollama 常见，按顺序试，不许跳步）：

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 输出以"好的/我来分析"开头，JSON 解析失败 | thinking 未关 | `think:false` + `/no_think`；判 `E_LLM_INVALID_OUTPUT` 重试 1 次 |
| `format` 生效但必填字段缺失 | schema 太宽 | 全字段列 `required`、`additionalProperties: false`；chunk 降到 300 字 |
| 三元组只抽到前 2–3 条就停 | 输出被 `num_predict` 截断 | chunk 切小、批量拆多次；**不要**加大 `num_predict` |
| 同一输入两次结果不同 | think 开着 / seed 没固定 | 关 think、固定 seed 与温度 0 |
| 显存 OOM、模型反复换出 | chat 与 embed 同时常驻 | `OLLAMA_NUM_PARALLEL=1`、串行、embed 降 CPU |
| 长文本后半段丢失 | `num_ctx` 用了默认 4096 | 显式 8192；chunk ≤400 字 |
| 中文全角标点/引号导致解析失败 | 模型未转义 | 严格 `json.loads`，**不修复、不猜**，直接转人工 |

---

## 5. Harness（受控执行骨架）

**定位**：Harness 不是让 AI 更自由，而是让它的能力有确切边界且可复核。绕过 Harness 直接调模型或直接写库的代码，视为缺陷。

### 5.1 模块与接口

```
app/harness/
  contract.py   # ToolSpec, ToolCall, ToolResult, Step, Trace, Policy, HarnessPort(Protocol)
  registry.py   # 工具白名单注册表（只读/起草/入队；写库类一律不注册）
  policy.py     # L1 before_tool、L2 before_commit
  loop.py       # 有界循环：步数、超时、token 预算、重试上限
  trace.py      # 每步落 audit_logs，支持按 run_id 重建
  builtin.py    # 默认实现（HarnessPort 的 builtin adapter）
  replay.py     # 用同一 harness 跑 30 条回放，产出可复算报告
```

`HarnessPort` 必须含：`run(record_id, goal, budget) -> RunResult`、`tools() -> list[ToolSpec]`、`trace(run_id) -> list[Step]`。外部运行时（你指定的具体 Harness 产品）通过 adapter 切换，业务代码不许感知。

### 5.2 工具白名单（只允许这些）

| 工具 | 类别 | 入参 | 出参 | 触发方 | 副作用 |
| --- | --- | --- | --- | --- | --- |
| `kb.search` | 读 | `query, scope, top_k≤8` | `hits[{chunk_id, doc_id, version, span, score}]` | 系统 | 记 `kb_queries` |
| `kg.path` | 读 | `from_task, to_course?, max_hops≤3` | `paths[{edges[], nodes[], doc_refs[]}]` | 系统 | 记 `kg_queries` |
| `kg.neighbors` | 读 | `node_id, rel_types, depth≤2` | `subgraph` | 系统 | 记 `kg_queries` |
| `feedback.get` | 读 | `feedback_id` | `{raw_text, channel, period_id, version}` | 系统 | 审计 |
| `mapping.resolve` | 读 | `student_id \| intern_id` | `{course_id, batch_id, checks}` | 系统 | 审计 |
| `task_template.match` | 读 | `post_id, text` | `[{task_id, score}]` | 系统 | — |
| `evidence.locate` | 读 | `feedback_id, quote` | `{span_start, span_end}` | 系统 | — |
| `suggestion.draft` | 写(draft) | 建议字段 | `{suggestion_id, status=draft}` | 系统 | 落库 draft |
| `review.enqueue` | 写(queue) | `record_id, reason, assignee` | `{review_task_id}` | 系统/教师 | 建待办 |
| `gate.check` | 判定 | `record_id` | `{pass, stops[]}` | 系统 | 审计 |

**禁止注册**（写进测试，调用即 `E_TOOL_NOT_ALLOWED`）：改 `feedbacks`/`evidences`、改 KB/KG（建图只能走 CLI 流水线，不能由模型在会话中改图）、任何外部写请求、任何 grade/score 字段、任何 approve、任何跨企业查询。

**特别说明**：模型**不能**在运行时新增图节点或边。图的写入只发生在 `kg-build` 离线流水线，且必须经过审核。否则"自己建边、自己判可执行"就成了自证循环。

### 5.3 两级策略检查

- **L1 before_tool**：参数合法性、Principal 作用域、`stale` 拦截、只读白名单、KB/KG 分区匹配。失败 → 不执行，返回 `E_SCOPE_VIOLATION` / `E_STALE_DATA` / `E_TOOL_NOT_ALLOWED`。
- **L2 before_commit**：`R2` 字段白名单 → `R3` ≥1 个 `evidence_ref` → `R4` 空值必须 `needs_review` → `R11` 课程/任务/口径表述必须带 `kb_ref` → `R13` 图上结论必须带 `kg_ref` 且路径边全为 `active` → `f44` 五类停止条件。任一失败 → **不落库**，返回 `E_GATE_STOPPED`，并强制带 `{reason, assignee, confirm_at}`（缺一即实现失败）。

### 5.4 循环边界

`max_steps=8`、单步 90s、单条总 240s（按 qwen3:8b 的实测速度定，见 §4.3 第 10 条）、token 上限 8000/条、重试 1 次且仅限 `E_LLM_TIMEOUT`/`E_LLM_INVALID_OUTPUT`。超限 → `E_HARNESS_BUDGET` + 转人工，**不抛 500、不静默截断**。回放时同样生效——不许因为"回放要跑完"就把预算放大，否则回放测的不是线上那条路径。

标准执行链（固定 6 步，允许提前终止，不许加第 7 个业务步骤）：

```
feedback.get → mapping.resolve → task_template.match(+kb.search) → kg.path → evidence.locate → suggestion.draft → review.enqueue
```

> 注：`kg.path` 与 `evidence.locate` 在实现上可并行；顺序写成 6 步是为了让 trace 好读，不是要求串行阻塞。

### 5.5 trace 与"在线/回放同构"

每步落 `audit_logs(object_type='harness_step')`：`run_id, step_no, tool, args_hash, result_hash, latency_ms, model, model_digest, prompt_version, kb_snapshot_id, kg_snapshot_id, policy_result`。给定 `run_id` 必须能重建全流程（f45）。

**硬要求**：回放与在线跑同一个 `HarnessPort`、同一套工具、同一套策略。禁止为回放写第二套流程——评估与生产不同构，24/30 的结论就无效。

---

## 6. 知识库（KB）与知识图谱（KG）

### 6.1 三类知识，分开治理

| 编号 | 知识 | 来源 | 形态 | 审核人 |
| --- | --- | --- | --- | --- |
| K1 | 岗位任务模板（岗位 → 任务 → 行为观察点） | 岗位说明书、林亦舟/叶书核定 | 结构化表 + 版本 | 林亦舟 + 叶书 |
| K2 | 课程—任务—能力口径映射 | 培养方案、课程标准 | 文档切片 + 映射 | 顾明岚 + 傅景 |
| K3 | 制度、规则、口径卡（C1–C4） | 访谈确认的规则文本 | 版本化文本 | 顾明岚签发 |

**不入库**：学生个体评价、行为实例原文、企业私有敏感资料（除本企业分区）、口令、家庭背景/性别等敏感属性（f41/R6）。

### 6.2 入库与版本

1. 每条文档带 `doc_id, title, scope(公共|专业|企业), owner, version, effective_from, effective_to, checksum, status(draft|active|retired)`。
2. 审核确认后 `draft → active` 才可检索；`retired` 保留但默认不命中。
3. 变更写审计；版本只增不改。
4. `kb_snapshots`：把一组 `doc_id+version` 的 hash 固化；回放必须指定 `kb_snapshot_id`（f34）。

### 6.3 切片与检索

- 切片：按标题层级切，单片 200–400 字，重叠 15%；表格按行切；保留 `page/paragraph` 供"点开原文段落"。
- 检索：`kb.retriever: bigram_bm25 | vector | hybrid`，默认 `bigram_bm25`（字符 bigram 倒排，中文免分词，纯 stdlib）。`vector` 走本地 Ollama `bge-m3`，向量存 SQLite BLOB；`hybrid` 用 RRF 融合。**不引向量数据库**；分片超 10 万再申请。
- 过滤：`scope` + `enterprise_id` + `status='active'` + `effective_from ≤ now`。
- 命中阈值进 config；低于阈值视为未命中。

### 6.4 引用强制（R11）

涉及课程、岗位任务、口径的表述必须带 `kb_ref = {doc_id, version, chunk_id, span}`：

- 命中但版本过期 / 无 `effective_from` → 标"仅供参考"，**不得作依据**（`E_KB_STALE`）。
- 未命中 → 字段 `null` + `needs_review`，**不许用模型常识补**（`E_KB_MISS`）。
- 前端点 `kb_ref` 必须能打开对应文档对应段落；打不开视为引用造假。

### 6.5 检索质量可测

`scripts/kb_eval.py`：30 条回放样本人工标注"应命中的任务模板/课程条目"，计算 `Recall@5`（M2 门槛 ≥0.80）、`MRR@5`、引用正确率（抽检 30 条，须 100% 能定位段落）。未达标不许进 M3。**不要用"看起来搜得挺准"替代这三个数。**

### 6.6 冷启动

K1 可从 30 条历史反馈反推候选任务，需林亦舟/叶书核定；K2 需培养方案/课程标准电子版；K3 可先用 `docs/` 里的规则事实（f24/f53/f42）人工录入。缺项列 `TODO(待确认: 语料)`，**不许编造任务清单**。

### 6.7 知识图谱：只服务五个查询，其余不建

图的唯一价值是回答"这条建议到底能不能落到课上"。因此只允许为下列查询建节点和边；某个字段如果五个查询都用不上，就不要画进图。

| 编号 | 查询 | 业务用途 | 对应证据 |
| --- | --- | --- | --- |
| Q1 | `task → 能力 → 课程单元 → 课程`（≤3 跳） | 判定建议"可对应课程"，即 24/30 的可执行性 | f01 / f42 |
| Q2 | `course → 受影响任务/能力`（反向） | 改一门课影响哪些岗位任务，支撑课程改进 | f01 / f55 |
| Q3 | `enterprise → 岗位 → 任务` 的"能连到课程"比例 | 把 f51 的"企业与学校口径对不齐"变成可计算数字 | f51 |
| Q4 | 冲突边：同一 `(from, to)` 同时存在 `COVERS` 与 `NOT_COVERS` | 口径矛盾待裁决，避免把矛盾写进建议 | f24 / f44 |
| Q5 | 孤立节点、无来源边 | 图质量告警，防止图悄悄烂掉 | — |

**节点白名单**（10 类，多一个都不行）：

`Major`（专业）`Course`（课程）`CourseUnit`（课程单元：章/节/实训项目）`Post`（岗位）`Task`（岗位任务）`ObservationPoint`（行为观察点）`Competency`（能力项）`Enterprise`（企业）`Rule`（规则/口径）`Doc`（来源文档）

**边白名单**（8 类，禁止自由命名关系）：

`OFFERS`（企业→岗位）、`BELONGS`（任务→岗位）、`REQUIRES`（任务→能力）、`MAPPED_TO`（课程单元→能力）、`PART_OF`（课程单元→课程）、`COVERS`（课程→任务）、`CONSTRAINED_BY`（任务/指标→规则）、`NOT_COVERS`（课程→任务，冲突用）

**禁止建节点**：`Student` `Feedback` `Evidence` `Mentor`。学生与反馈只作为边的 `provenance` 引用存在（R12），查询时按权限解析。这条不写死，f40 一定会被图绕过。

### 6.8 图谱构建、发布与查询

**流水线（离线 CLI，幂等，按文档版本增量）：**

```
kg-build --docs <ids> --snapshot <id>
  1 extract    # 对每个 chunk 调 Ollama，format=JSONSchema，输出候选三元组
  2 normalize  # 别名表归一（去空格/全半角/同义词）；相似度>阈值只进"待合并"队列，不自动合并
  3 validate   # 类型白名单、端点存在、无自环、无重复边(upsert)、必须有 provenance
  4 review     # 新边 draft → 人工审核 → active；审核人按 K1/K2/K3 分区
  5 publish    # 生成 kg_snapshot，写入版本与 hash
```

1. **抽取**用受约束解码（§4.3 第 3 条），schema 里 `rel_type` 与 `node_type` 均为 `enum`，模型没有自由发挥空间。
2. **归一不自动合并**：合并错会污染整张图，且很难回溯。相似度高只产出"候选合并"进人工队列，动作写审计。
3. **每条边必须有 `provenance`**：`doc_id + chunk_id + span + extractor_version + confidence`。无来源的边不得 `active`（R13）。
4. **判定只用 `active` 边、只用已发布快照**。回放时必须 pin `kg_snapshot_id`，否则"可执行"结论不可复算。
5. **防自证循环**：建图与判定分离。建图离线且经人审核；运行时模型只能读图，不能改图（§5.2）。

**存储与规模：**

- 表：`kg_nodes(node_id, type, name, aliases, scope, status)`、`kg_edges(edge_id, from_id, to_id, rel_type, provenance, confidence, status)`、`kg_aliases`、`kg_snapshots`、`kg_queries`、`kg_conflicts`。
- 路径查询用 SQLite 递归 CTE（`WITH RECURSIVE`，深度上限 3，参数绑定）；热点子图做进程内 LRU 缓存。
- 规模上限：节点 5 万、边 30 万。超过再谈图数据库，**现在不许引 Neo4j/JanusGraph**。
- 导出：`scripts/kg_export.py --format dot|mermaid|json`；`/kg` 页面只做"以某任务为中心的子图 + 边悬浮显示来源段落"。

**质量门槛（M2 必过，数值进 config）：**

| 指标 | 门槛 |
| --- | --- |
| 边 provenance 覆盖率 | 100% |
| 孤立节点占比 | ≤5% |
| Q1 路径覆盖率（回放中可识别任务能找到 ≤3 跳到课程的路径） | ≥80%（否则 24/30 必然做不到） |
| 未裁决冲突边 | 0（或全部有裁决记录与裁决人） |
| 节点/边类型越界 | 0 |

`scripts/kg_eval.py` 输出上述表，退出码非 0 即未达标。

---

## 7. 数据红线（硬约束，代码必须能自证）

| 编号 | 约束 | 落地要求 |
| --- | --- | --- |
| R1 | 只读 | 外部系统仅 GET 与导出文件；`check_readonly.py` 扫 `app/` 内 httpx 方法与 SQL 写语句，命中退 1，挂进 pytest |
| R2 | 不判定 | 无 `grade/score/level/rank/verdict`；Suggestion 白名单 `{observation, evidence_refs, kb_refs, kg_refs, task_id, course_id, owner_id, proposed_action}` |
| R3 | 可追溯 | 每条建议 ≥1 个 `evidence_ref`（record_id + span + 版本 + 采集时间）；0 引用 → schema 失败，不落库 |
| R4 | 不猜值 | 缺失 = `null` + `needs_review`；禁止默认值、推断补全、空串转"无问题" |
| R5 | 不覆盖 | 原文 append-only；修正 = 新增 revision + reason + operator；原文表禁 UPDATE/DELETE |
| R6 | 最小化 + 本地优先 | 不落地口令/身份证/家庭背景；性别与家庭背景不进能力推断；样例一律合成；**默认零外发（Ollama 本地）**，远程端点须显式开启、脱敏、逐次审计 |
| R7 | 隔离 | 企业导师作用域=本企业；查询强制 `enterprise_id`；跨企业 → 403 + 审计 |
| R8 | 时效 | `period_id` + `fetched_at`；超 `stale_days`（默认 14）→ `stale`，不得进入建议生成 |
| R9 | 留存 | `retention_days` 从 config 读（默认 90，标"仅限本轮合成试点"）；到期出清单，须教学质量负责人确认后执行；先删正文，留审计摘要 |
| R10 | 审计 | append-only；who/when/role/action/object_type/object_id/before_ref/after_ref/reason/prompt_version/model/model_digest/kb_snapshot_id/kg_snapshot_id/request_id；不记明文密钥、不记完整正文（记 hash + 定位） |
| R11 | 引用即依据 | 课程/任务/口径表述必须带 `kb_ref`；KB 过期或未命中不得作依据（§6.4） |
| R12 | KB/KG 不含个体数据 | 只存组织级知识；不得建 `Student`/`Feedback` 节点；企业分区默认私有（§6.7） |
| R13 | 图可证 | 每条 `active` 边必须有 `provenance`（doc+chunk+span）；判定只走 `active` 边与已发布快照；无来源边、跨快照混用即缺陷 |

补充：每条红线用 `# R13` 注释；pytest 至少一条对应用例；交付给"红线 × 用例"映射表。为赶工放宽红线 = 未完成。

---

## 8. 统一契约

**响应体（所有对外接口，含页面 API 与 CLI 的 JSON 输出）：**

```json
{"ok": true, "data": {}, "error": null}
```

```json
{"ok": false, "data": null, "error": {"code": "E_GATE_STOPPED", "msg": "换岗未重关联：该批次停止自动建议", "detail": {"reason": "assignment_stale", "assignee": "唐映秋", "confirm_at": "2026-11-13T09:00:00+08:00"}}}
```

约定：`ok=false` 时 `data` 必须 `null`；`msg` 中文可读；`code` 英文常量。分页 `{"items","total","page","page_size"}`。时间存 UTC、展示 `Asia/Shanghai`，ISO8601 带时区。ID 前缀：`stu_ bat_ fb_ evd_ sug_ rvk_ aud_ hof_ run_ doc_ chk_ kgn_ kge_`。

**错误码（每个都要有测试）：**

`E_CONFIG_MISSING` `E_AUTH_REQUIRED` `E_AUTH_DENIED` `E_SCOPE_VIOLATION` `E_NOT_FOUND` `E_CONFLICT` `E_DUPLICATE` `E_SCHEMA_INVALID` `E_MAPPING_UNRESOLVED` `E_STALE_DATA` `E_EVIDENCE_MISSING` `E_GATE_STOPPED` `E_LLM_TIMEOUT` `E_LLM_INVALID_OUTPUT` `E_LLM_UNAVAILABLE` `E_RETENTION_BLOCKED` `E_READONLY_VIOLATION` `E_TOOL_NOT_ALLOWED` `E_HARNESS_BUDGET` `E_KB_MISS` `E_KB_STALE` `E_KB_UNVERIFIED` `E_KG_INVALID` `E_KG_NO_PATH` `E_KG_CONFLICT` `E_INTERNAL`

**数据表（最小集，字段名照用）：**

业务：`students` `enterprises` `batches` `teachers` `mentors` `posts` `task_templates(version)` `assignments(effective_from, effective_to, change_reason)` `feedbacks(channel, submitted_at, period_id, version, raw_text, hash)` `evidences(feedback_id, span_start, span_end, quote)` `mappings(student_id, intern_id, course_id, check_result)` `import_batches(idempotency_key, stats)` `handoffs(六项字段, accepted_by, accepted_at)` `review_tasks(assignee, due_at, return_reason, status)` `suggestions(status)` `suggestion_evidences` `suggestion_kb_refs` `suggestion_kg_refs` `revisions` `audit_logs` `rule_versions(effective_from, scope)` `metric_definitions(version, numerator, denominator, window, exclusions)` `metric_snapshots` `retention_jobs`

Harness：`harness_runs(run_id, record_id, mode(online|replay), kb_snapshot_id, kg_snapshot_id, model, model_digest, prompt_version, steps, status, cost)`

KB：`kb_documents` `kb_chunks(span, text, token_len)` `kb_versions` `kb_queries(query, top_k, hits)` `kb_snapshots`

KG：`kg_nodes(type, name, aliases, scope, status)` `kg_edges(from_id, to_id, rel_type, provenance_json, confidence, status)` `kg_aliases` `kg_snapshots(created_at, node_count, edge_count, hash)` `kg_queries(kind, params_hash, result_hash, snapshot_id)` `kg_conflicts(edge_a, edge_b, status, resolved_by)`

**状态机（非法迁移 `E_CONFLICT` + 审计）：**

- feedback：`imported → parsed → needs_review → confirmed | rejected → stale`
- suggestion：`draft → gated → pending_review → approved | rejected → archived`
- review_task：`open → assigned → returned → closed | escalated`
- kb_document / kg_edge：`draft → active → retired`

---

## 9. 代码规范

1. 命名英文，docstring/注释/错误信息中文。
2. 每个公开函数 docstring 三行式：**入参**（类型与约束）、**出参**（结构）、**失败时的行为**（抛什么 / 返回哪个 `code` / 写不写审计）。缺一项视为未完成。
3. 关键分支写**为什么**：`# R4/f33：缺岗位任务字段不许猜，进人工修复队列`。不要每行都写注释——赋值、循环、`return` 上的复述式注释会被要求删掉。
4. 禁止：裸 `except`、`print` 调试、字符串拼接 SQL（含 f-string 进递归 CTE）、`# type: ignore` 掩盖真实错误、路由里写业务逻辑、harness 外调模型、运行时改图。
5. 单文件 ≤400 行，单函数 ≤50 行，圈复杂度 >10 必拆。
6. 配置只从 `config.yaml` 读。代码里出现 URL、密钥、模型名、阈值字面量 = 失败。启动校验缺项 → 打印缺失清单 + 退出码 2。
7. 阈值进 config 并注明来源：`complete_rate_target: 0.85  # 访谈口径 f00，待业务签发`。f42/f43/f44 相关阈值不得有默认"安全值"。
8. 每个模块顶部 3 行说明"守哪条红线、依赖哪个部件"。
9. Alembic 迁移可回滚 + 中文说明；KB 与 KG 的 schema 变更各单独一条迁移。
10. 模型调用：超时/重试/降级集中在一处，失败降级人工队列（f35），不得 500；输出必须过 Pydantic schema，不合法 `E_LLM_INVALID_OUTPUT`，重试一次后转人工。

---

## 10. 里程碑与验收（按顺序，不许跳）

| 里程碑 | 交付物 | 通过门槛 |
| --- | --- | --- |
| M0 | config、统一响应与错误码、RBAC 骨架、审计表、Harness 契约/注册表/策略/trace、KB 与 KG schema、Ollama(qwen3:8b) 适配与健康检查、口径卡 v1、复算脚本、`setup_ollama.*` | 缺配置退 2；错误码全覆盖；越权工具 `E_TOOL_NOT_ALLOWED`；trace 可按 run_id 重建；**固定 5 条样本断言 think 已关（输出以 `{` 开头、无思维链前缀）且 schema 校验通过**；Ollama 停机时应用正常启动、`/healthz` 报 `llm=down`、抽取转人工；digest 与 pin 不一致时告警且写审计；固定样本两方复算误差=0 |
| M1 | 导入 CLI、批次登记、ID 映射、四项校验、KB-K1 入库、K1 建初图（岗位-任务-观察点）、幂等、stale | 同批次导入两次记录数不变；四项校验逐行结果+通过率；缺字段进修复队列不猜值；`draft` 文档/边不可检索；1 篇文档 Ollama 抽取成功且三元组全过白名单 |
| M2 | 三字段抽取、span 定位、人工队列、f44 闸门、KB 检索接入、KG 归一/审核/发布、端到端 6 步 | 30 条回放每条有 span+版本；闸门三字段齐；`Recall@5 ≥ 0.80`；图五项质量指标全达标（§6.8）；模型超时降级且不 500 |
| M3 | 建议草稿、`kg.path` 连通判定、`kb_ref`+`kg_ref`+`evidence_ref` 强制、24/30 自检、append-only 修正 | 三字段齐全且图连通方可 approved；24/30 自检输出可读表（含每条不达标的具体原因）；修正后原文 hash 不变；审计可重建一次完整处理；引用可点开原段落 |
| M4 | 完整率/工时/可执行率复算、图覆盖率与影响面报表、30 条回放报告、CSV/XLSX 导出 | 完整率分母=学生×双周、排除规则可配；工时四类拆分；报告含可追溯率、KB 命中率、图路径覆盖率、确认耗时 |

"完成"的定义：pytest 全绿 + `scripts/verify_mN.py` 退出码 0 + 红线自查表全绿 + 我确认。三者缺一不算完成。

---

## 11. 交付格式（每个里程碑固定六段，不要加长文）

**① 变更文件清单**：路径 + 一句话作用 + 新增/修改。
**② 启动与自测命令**：可直接复制，含依赖安装、迁移、`ollama pull`、KB/KG 构建。
**③ 验证脚本**：`scripts/verify_mN.py`，真跑，输出 PASS/FAIL 表，失败退出码非 0。
**④ 本阶段最可能出问题的 3 处**：写具体触发条件与现象（例："岗位名带括号后缀时别名归一漏掉，导致 Q1 路径断裂、24/30 虚高"），不写"注意安全"。
**⑤ 红线自查表**：R1–R13 × 通过/未覆盖/不适用，每格给证据（用例名或命令）。
**⑥ 未覆盖项与下一阶段前置**：缺哪份证据/语料、等谁确认、影响哪个门槛。

不要贴大段代码，直接改文件。不要写"总结""优点""心得体会"。我要能跑的代码。

---

## 12. 开工前（现在这一步）

先不写代码。先回答：

**（1）用五句话复述你对项目的理解**，必须覆盖：病根不是"整理慢"、只读与不判定、24/30 靠图连通判定、追溯与人工确认、先修管道再装泵。

**（2）你打算先做的三件事**：每条给一句话目标 + 产出物 + 涉及文件。

**（3）对下面 10 项给判断或提问**：

1. 技术栈是否照 §4 执行？若你已有栈，只改这一节，FastAPI / Python 3.11+ / Harness / KB / KG / Ollama 六项保留。
2. **Harness 指哪个**：自建受控骨架（默认），还是某个具体产品或框架（给名字与文档，我按 `HarnessPort` 适配）。
3. **Ollama 那台机器的规格**：有没有 GPU、显存多少、内存多少？`ollama show qwen3:8b` 的 digest 是多少？——决定 embedding 走 GPU 还是降 CPU，也决定 30 条回放是几小时还是过夜。
4. 是否允许远程模型兜底？默认**不允许**（R6 零外发），要开请明说。
5. 知识库语料：培养方案 / 课程标准 / 岗位说明书有没有电子版？没有的话 K1 用什么兜底？
6. **"课程单元"的粒度**：章、节、还是实训项目？这决定图能不能连通、24/30 算不算得出来，必须由专业组定。
7. 开发库用 SQLite 还是直接上 PostgreSQL？
8. 30 条回放的历史反馈样本谁提供？什么格式？有没有岗位任务字段？
9. 首期是否需要 Web UI？若只做 CLI + 报告，可省约 40% 工期。
10. 口径卡 C1–C4（完整率、可执行率、工时、返修）的四个分母由谁签发？

等我确认后再动代码。这 10 项里若有没答案的，先只做不依赖它的部分，并在交付里标出来。

---

---

# 附录（不是提示词正文，粘贴时不要带上）

## A. 变更记录

### A1. v4 → v5（模型定版）

| 改动 | 原因 |
| --- | --- |
| 模型定版 `qwen3:8b` | 你指定；同时把 embedding 单独定为 `bge-m3`——`qwen3:8b` 不是 embedding 模型，拿它算向量是常见错误 |
| 新增「必须关 thinking」 | Qwen3 默认混合推理，思维链会混进输出，`format` 也挡不住，JSON 解析必挂。这是 8B 上最容易踩、且最难自查的坑 |
| thinking 与 content 分开存 | 思维链里会带学生原文，入库即破 R6 |
| 新增 8B 能力边界（chunk ≤400 字、三元组 ≤8 条） | 8B 输出越长越容易漏字段、串行；靠"加大 num_predict"救不回来 |
| 判定权从模型移到图查询 | 8B 不具备稳定裁决"可执行"的能力；这也正好和 §6.7 的确定性判定对上 |
| 新增显存预算（6–7GB + 1.2GB，`NUM_PARALLEL=1`） | 8G 卡上 chat 与 embed 同时常驻会 OOM，Ollama 会静默换出模型，表现为"突然变慢"而不是报错 |
| 新增 digest pin | `qwen3:8b` 是滚动 tag，不同时间 pull 的权重不同，回放结论会漂 |
| 新增故障模式表 | 把这 7 类问题变成"照着查"，而不是每次从头 debug |
| 预算改 90s/240s | 按 8B 实测速度重算；原来的 60s/180s 是按 7B 估的，会天天超时 |

### A2. v3 → v4（图谱与本地化）

| 改动 | 原因 |
| --- | --- |
| 新增 §6.7–6.8 知识图谱 | f01/f42 的"建议落到课程"本质是多跳关系，关系表比字段堆砌更能判定；同时把 f51 的口径断裂变成可计算数字 |
| 图只服务 Q1–Q5 | 防"为了有图而建图"。每个节点/边必须回答一个查询，否则不建 |
| 节点/边白名单 + 禁建 `Student`/`Feedback` | 不写死这条，f40 一定被图绕过（图谱天生爱把一切连起来） |
| 建图离线 + 运行时只读 + 只用 active 边 | 防自证循环：模型不能一边建边一边判"可执行" |
| 新增 §4.3 Ollama | 本地推理让 f40/R6 的"数据不出校"真正成立，而不是靠承诺 |
| `format=JSONSchema` 受约束解码 | 比"请输出 JSON"可靠一个量级；schema 与 Pydantic 同源，避免两处漂移 |
| R13 图可证 | 无 provenance 的边等于编造依据 |
| 24/30 判定升级 | 从"三字段齐备"→"三字段齐备 + 图连通"，才算真能落到课 |
| 错误码 22 → 26 | 增 `E_LLM_UNAVAILABLE` `E_KG_INVALID` `E_KG_NO_PATH` `E_KG_CONFLICT` |
| §12 问题 8 → 10 | 增"Ollama 跑在哪/有无 GPU""课程单元粒度"——后者是图能否成立的前提 |

## B. 三个仍需你点头的判断

1. **"每行代码必须加注释"** 仍建议保持 §9 第 3 条写法；要还原就把该条换回原句。
2. **Harness 若指具体产品**，给名字即可，只换 adapter。
3. **图表规模**：我按"5 万节点/30 万边以内、SQLite 递归 CTE"设计。若你预期全校培养方案全量入图（可能到百万级），现在就说，我改成 PostgreSQL + pgvector/materialized path，别等到 M2 再返工。

## C. 还缺的输入（影响 M1–M3）

- 30 条历史反馈样本（决定 M2 能否验收）。
- 培养方案 / 课程标准 / 岗位说明书电子版（决定 K2 与整张图是否为空）。
- **课程单元粒度定义**（决定 Q1 路径是否成立，最关键）。
- 口径卡 C1–C4 的四个分母与排除规则（f53）。
- 12 万元四块成本拆分（f03）。
- 换岗案例清单与 N（f11）。
- 运行 Ollama 的机器规格（显存/内存 → 决定 `bge-m3` 走 GPU 还是 CPU、回放是否过夜）。
- `ollama show qwen3:8b` 的 digest（写进 `model_digest_pin`，否则回放结论不可复算）。
