# 学习支持与辅导协作 MVP

> 知行职业学院「实习反馈里的能力缺口」案例的可运行实现：**FastAPI ＋ Harness ＋ 知识库（RAG／知识图谱）＋ 分层权限 ＋ 本地部署**。
> 全部数据来自 `docs/` 下的合成训练资料，结论均为待验证假设，不含真实学生信息。

## 一分钟跑起来

```powershell
cd D:\learning-support-mvp
.\run.ps1            # 首次会自动准备环境、装依赖、构建索引，然后打开浏览器
```

项目自带 Python 运行时（`runtime\python`，3.12.14），**不需要事先安装 Python，也不依赖任何外部环境**。首次运行会就地创建 `.venv` 并安装 FastAPI/uvicorn（约 20 秒，需要联网）。

手动启动（环境已就绪时）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

重建知识库（改过 `docs/` 之后）：

```powershell
.\.venv\Scripts\python.exe scripts\build_index.py
```

打开 <http://127.0.0.1:8010>，用下面任一账号登录：

| 账号 | 口令 | 角色 | 能做什么 |
| --- | --- | --- | --- |
| `teacher` | `teacher123` | 实习指导教师 | 检索、起草建议，**不能**确认、不能读审计 |
| `reviewer` | `review123` | 教学质量负责人 | 检索、确认建议、读审计与校验链，**不能**起草 |
| `coordinator` | `coord123` | 产教融合负责人 | 起草 + 确认 + 审计 |
| `admin` | `admin123` | 管理员 | 全部 + 用户管理 |
| `student` | `student123` | 学生 | 只能检索与看图谱 |

## 白板五项，对应到代码

| 白板 | 实现 | 位置 |
| --- | --- | --- |
| ① FastAPI | 应用工厂 + 20 个路由，统一异常返回 | `app/main.py` |
| ② Harness | 逐用例隔离的端到端断言（14 组 / 30 条），含篡改检测 | `tests/harness.py` |
| ③ 知识库 RAG / 知识图谱 | BM25 检索（中文按字 + 二元组切分）＋ 63 节点知识图谱 + Wiki 页面 | `app/kb.py`、`scripts/build_index.py` |
| ④ 权限：管理员 / 分层用户 | 角色-动作矩阵，**默认拒绝**、deny 优先、本人签核禁止 | `app/core.py`（`can` / `permissions_of`） |
| ⑤ 本地部署 | `run.ps1` / `run.bat` / `Dockerfile`，默认 8010 端口 | 项目根目录 |

## 目录

```
learning-support-mvp/
├── app/
│   ├── main.py      # FastAPI 路由与鉴权依赖
│   ├── core.py      # 配置、口令、令牌、RBAC、事件、审计链、脱敏
│   ├── kb.py        # BM25 检索 + 知识图谱查询 + Wiki
│   └── advice.py    # 建议生成（规则打底，LLM 可选）、人工确认
├── runtime/python/  # 自带 Python 运行时（151 MB，与外部环境无关）
├── scripts/build_index.py   # 从业务文档生成 index.json 与 graph.json
├── data/
│   ├── docs/        # 从教育仓库复制来的业务文档（构建时生成）
│   ├── graph.json   # 知识图谱（63 节点 / 37 边）
│   └── runtime/     # 运行时：users.json、advice.json、events.jsonl、audit.jsonl、index.json
├── web/index.html   # 单页前端（检索 / Wiki / 建议 / 审计）
├── tests/harness.py # 端到端测试
├── config.json      # 端口外的全部可调项：RBAC、阈值、模型
└── run.ps1 / run.bat / Dockerfile
```

## 关键设计（为什么不是“一个会写建议的聊天框”）

**1. 缺证据就不生成。** 没有行为实例、或文本里出现「家庭背景」「性别」这类敏感属性、或检索不到依据，`/advice` 直接返回 `blocked` 并列出原因，不产出任何建议。

**2. 起草与确认必须两个人。** 教师起草，质量负责人确认；`created_by == 确认人` 时返回 403（`self_sign_denied`），管理员可覆盖。

**3. 审计链可自证。** 每条审计记录带前一条的哈希；`/audit/verify` 重算全链，改一个字节就报错并指出第几条断。

**4. 权限默认拒绝。** `config.json` 里 deny 优先于 allow；学生连 `/advice` 的 POST 都进不去，教师读审计也是 403。

**5. 模型可插拔，失败不静默。** `config.json` 的 `llm.enabled` 默认 `false`，走确定性规则；开启后调用本地 Ollama（`qwen3:8b`），失败会把 `llm_error` 带回记录，不会假装成功。

## 接口一览

| 方法 | 路径 | 说明 | 所需权限 |
| --- | --- | --- | --- |
| POST | `/auth/login` | 换取令牌（8 小时） | — |
| GET | `/health` | 索引与图谱状态 | — |
| GET | `/kb/search?q=&k=` | BM25 检索，返回出处与证据编号 | `kb:search` |
| GET | `/kb/context?q=` | 检索 + 图谱一跳扩散 | `kb:search` |
| GET | `/graph/stats` `/wiki` `/graph/neighbors/{id}` | 图谱与 Wiki | `graph:read` |
| POST | `/advice` | 起草建议（含红线拦截） | `advice:draft` |
| GET | `/advice` `/advice/{id}` | 查询 | `advice:read` |
| POST | `/advice/{id}/confirm` | 人工确认/驳回 | `advice:confirm` |
| GET | `/audit` `/audit/verify` `/events` | 审计与事件 | `audit:read` |
| GET/POST | `/admin/users` | 用户管理 | `admin:users` |

交互式文档：<http://127.0.0.1:8010/docs>

## 测试

```powershell
# 服务先跑起来，然后
.\.venv\Scripts\python.exe tests\harness.py
```

覆盖：健康检查、登录与角色、检索出处、正常起草、缺实例拦截、敏感属性拦截、本人签核拒绝、学生越权、审计越权、人工确认、审计链校验、篡改检测、用户管理、图谱与 Wiki。当前 **30/30 通过**。

## 模型层（可选）

默认 `config.json` 里 `llm.enabled = false`，全部能力走确定性规则，**不装模型也能完整演示**。

本机已装好并启用：Ollama 0.40.16（`D:\Ollama`）+ `qwen3:4b`（2.5 GB，模型目录 `D:\ollama-models`）。实测在 **Intel Arc 核显**上约 **20 tok/s**，一次建议生成约 5 秒；模型 100% 加载到 GPU（37/37 层），加载耗时约 12 秒。

接本地模型：

```powershell
# 1. 安装 Ollama（安装包在 D:\installers\OllamaSetup.exe）
# 2. 拉模型
ollama pull qwen3:8b
# 3. 打开 config.json，把 llm.enabled 改成 true
```

模型生成的建议必须**引用一条真实观察记录**（`evidence_index` 指向 O1..On）；模型编造记录、输出空话、或提到被禁表述时，该条建议会被丢弃；全部丢弃则回落规则引擎，并在记录里写明 `llm.reason`，不会假装是模型产出的。

`GET /llm/status` 可以随时看模型是否在线、目标模型是否已拉取；页面右上角也有同样的状态标记。

显存/内存不够时可以把 `model` 换成 `qwen3:4b` 或 `qwen3:1.7b`，代码不用改。

## 部署

本地直接 `run.ps1`。容器：

```bash
docker build -t learning-support-mvp .
docker run -p 8000:8000 learning-support-mvp
```

放到公网需要一台能访问的机器或平台账号（Render / Railway / 阿里云函数计算等），把 `--host` 改成 `0.0.0.0` 并映射端口即可；`config.json` 里没有密钥，只有模型地址。

## 已知边界

- 检索是 BM25 字面匹配，不是向量检索；同义改写（「掉队」→「跟不上」）命中率有限。
- 知识图谱由脚本从文档抽取，节点规模 63，尚未做实体消歧。
- 规则引擎只覆盖本案例的三类红线，未做通用的策略引擎。
- 4B 模型在 CPU/核显上可用，但复杂推理仍会出错；`qwen3:8b` 未安装（规格书原定），需要时 `ollama pull qwen3:8b` 并在 `config.json` 改一行。
