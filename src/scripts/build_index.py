"""从业务文档构建知识库索引与知识图谱。

用法（在项目根目录执行）：
    .venv\\Scripts\\python.exe scripts\\build_index.py [源文档目录]

默认源目录：优先用仓库内的 ../docs，找不到再退回本机开发路径。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import core  # noqa: E402

DEFAULT_SRC = r"C:\Users\Lenovo\Desktop\代码集合\教育\docs"


def resolve_source() -> str:
    """按优先级找业务文档：命令行参数 > 仓库内 ../docs > 本机开发路径。"""
    for cand in (os.path.join(ROOT, "..", "docs"), DEFAULT_SRC):
        if os.path.isdir(cand):
            return os.path.abspath(cand)
    return DEFAULT_SRC

FACT_RE = re.compile(r"\[education-(f\d+)\]\s*([^：:\n]{1,12})[：:]\s*([^\n（(]{5,200})")
REQ_RE = re.compile(r"^###\s*\d+\.\s*(.+?)\s*\[(P\d)\]", re.M)

ROLES = {
    "顾明岚": ("role:gu", "产教融合负责人", "业务发起人与立项牵头人；定范围、节奏、口径"),
    "林亦舟": ("role:lin", "实习指导教师", "一线使用者；回访、归拢、复核现场"),
    "唐映秋": ("role:tang", "教务管理员", "交接与材料责任；异常分派"),
    "秦芮": ("role:qin", "校园信息工程师", "只读接口、ID 映射、刷新与故障预案"),
    "傅景": ("role:fu", "教学质量负责人", "风险否决与验收签字；24/30 硬线"),
    "叶书": ("role:ye", "企业实习导师", "企业侧提交、投诉受理；参与验收"),
}

METRICS = [
    ("metric:complete_rate", "反馈完整率", "现状 54%，目标 85%；分母与排除规则待业务负责人固定"),
    ("metric:teacher_hours", "教师整理工时", "约 10 小时/人·月；未拆分搬运与核对"),
    ("metric:actionable", "建议可对应率", "专业组审阅 30 条至少 24 条可对应课程/任务/负责人"),
    ("metric:review_minutes", "复核耗时", "教务核对 + 专业组评审 + 质量签核的条数与分钟"),
    ("metric:misroute", "换岗错发与补录", "错发条数、群聊补录次数；目前只有定性描述"),
    ("metric:traceability", "追溯合格率", "可点回原文与版本、且标注确认人的比例"),
]

DECISIONS = [
    ("decision:l1", "立项与范围", "顾明岚牵头立项，傅景有风险否决权"),
    ("decision:l3", "口径固定", "完整率与可对应率的分母、周期、排除规则由业务负责人固定"),
    ("decision:l9", "试点验收", "专业组审阅，傅景不签字即不通过"),
    ("decision:l11", "培养方案变更", "只能走教务委员会，模型不得介入"),
]


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def chunk_docs(files):
    chunks = []
    for path in files:
        text = load_text(path)
        name = os.path.basename(path)
        lines = text.splitlines()
        buf, heading, start = [], "", 1
        for idx, line in enumerate(lines, 1):
            is_head = line.startswith("#")
            if is_head and buf:
                body = "\n".join(buf).strip()
                if body:
                    chunks.append({"path": name, "heading": heading or "(开头)",
                                   "line": start, "text": body,
                                   "facts": sorted(set(re.findall(r"education-(f\d+)", body)))})
                buf, start = [], idx
            if is_head:
                heading = line.lstrip("# ").strip()
            buf.append(line)
            if sum(len(x) for x in buf) > 1200:
                body = "\n".join(buf).strip()
                chunks.append({"path": name, "heading": heading or "(开头)", "line": start,
                               "text": body, "facts": sorted(set(re.findall(r"education-(f\d+)", body)))})
                buf, start = [], idx + 1
        if buf:
            body = "\n".join(buf).strip()
            if body:
                chunks.append({"path": name, "heading": heading or "(开头)", "line": start,
                               "text": body, "facts": sorted(set(re.findall(r"education-(f\d+)", body)))})
    for i, c in enumerate(chunks):
        c["id"] = f"chunk_{i:03d}"
        c["chars"] = len(c["text"])
    return chunks


def build_graph(files):
    nodes, edges = [], []
    node_ids = set()

    def add_node(nid, ntype, label, summary="", ref=""):
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({"id": nid, "type": ntype, "label": label, "summary": summary, "source_ref": ref})

    def add_edge(src, dst, rel, ref=""):
        if src in node_ids and dst in node_ids:
            edges.append({"source": src, "target": dst, "relation": rel, "source_ref": ref})

    for name, (rid, title, summary) in ROLES.items():
        add_node(rid, "role", f"{title} · {name}", summary, "教育·角色资料")

    report = [f for f in files if f.endswith("discovery-report.md")]
    text = load_text(report[0]) if report else ""
    facts = {}
    for line in text.splitlines():
        m = FACT_RE.search(line)
        if m:
            fid, speaker, body = m.group(1), m.group(2).strip(), m.group(3).strip()
            facts[fid] = (speaker, body)
    for fid, (speaker, body) in sorted(facts.items()):
        rid = ROLES.get(speaker, (None,))[0]
        add_node(f"fact:{fid}", "fact", f"f{fid[1:]} · {body[:34]}", body, f"education-{fid}")
        if rid:
            add_edge(f"fact:{fid}", rid, "spoken_by", f"education-{fid}")

    for i, m in enumerate(REQ_RE.finditer(text), 1):
        title, prio = m.group(1).strip(), m.group(2)
        add_node(f"req:r{i}", "requirement", f"R{i} · {title[:40]}", f"优先级 {prio}", "discovery-report#需求")

    for mid, label, summary in METRICS:
        add_node(mid, "metric", label, summary, "discovery-report#验收")
    for did, label, summary in DECISIONS:
        add_node(did, "decision", label, summary, "业务机会清单#决策链")

    for r in [n for n in nodes if n["type"] == "requirement"]:
        for f in [n for n in nodes if n["type"] == "fact"]:
            if f["id"].split(":")[1][1:] in r["summary"]:
                add_edge(r["id"], f["id"], "based_on", r["source_ref"])

    add_edge("metric:complete_rate", "decision:l3", "fixed_by", "f53")
    add_edge("metric:actionable", "decision:l9", "gated_by", "f42")
    add_edge("metric:traceability", "decision:l9", "gated_by", "f45")
    add_edge("decision:l1", "role:gu", "owned_by", "f04")
    add_edge("decision:l9", "role:fu", "owned_by", "f42")

    return {"version": "kg-v1", "generated_at": core.now(), "nodes": nodes, "edges": edges}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else resolve_source()
    if not os.path.isdir(src):
        sys.exit(f"源目录不存在：{src}")
    core.ensure_dirs()
    dest = core.path_of("docs")

    copied = []
    for name in sorted(os.listdir(src)):
        if name.lower().endswith((".md", ".html")):
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))
            copied.append(os.path.join(dest, name))
    print(f"已复制 {len(copied)} 个文档到 {dest}")

    chunks = chunk_docs(copied)
    print(f"切片：{len(chunks)}（平均 {sum(c['chars'] for c in chunks) // max(1, len(chunks))} 字）")
    with open(os.path.join(core.path_of("runtime"), "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": core.now(), "chunks": chunks}, fh, ensure_ascii=False, indent=1)

    graph = build_graph(copied)
    with open(core.path_of("graph"), "w", encoding="utf-8") as fh:
        json.dump(graph, fh, ensure_ascii=False, indent=1)
    print(f"图谱：{len(graph['nodes'])} 节点 / {len(graph['edges'])} 边")

    types = {}
    for n in graph["nodes"]:
        types[n["type"]] = types.get(n["type"], 0) + 1
    print("节点类型：", types)


if __name__ == "__main__":
    main()
