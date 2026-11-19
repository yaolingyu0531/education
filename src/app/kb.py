"""知识层：文档切片 + BM25 检索 + 知识图谱查询。

只用标准库。中文按「字 + 二元组」切分，英文/数字按词切分。
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from . import core

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-\.]*|\d+(?:\.\d+)?|[\u4e00-\u9fa5]")
STOP = set("的了和是在有为与及等这那个一我你他她它们中上下于对不也就都而及或如果因此但是".split())


def tokenize(text: str) -> List[str]:
    raw = TOKEN_RE.findall(text.lower())
    tokens: List[str] = []
    prev_cjk = ""
    for tok in raw:
        if "\u4e00" <= tok <= "\u9fa5":
            if tok not in STOP:
                tokens.append(tok)
            if prev_cjk and prev_cjk != tok:
                tokens.append(prev_cjk + tok)
            prev_cjk = tok
        else:
            prev_cjk = ""
            tokens.append(tok)
    return tokens


class BM25:
    def __init__(self, docs: List[Dict[str, Any]], k1: float = 1.4, b: float = 0.72):
        self.docs = docs
        self.k1, self.b = k1, b
        self.freqs: List[Counter] = [Counter(tokenize(d["text"])) for d in docs]
        self.lens = [sum(f.values()) for f in self.freqs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for f in self.freqs:
            df.update(f.keys())
        n = len(docs) or 1
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int = 6) -> List[Tuple[float, Dict[str, Any]]]:
        q = Counter(tokenize(query))
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for i, f in enumerate(self.freqs):
            if not f:
                continue
            score = 0.0
            for term, qn in q.items():
                if term not in f:
                    continue
                idf = self.idf.get(term, 0.0)
                tf = f[term]
                denom = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1))
                score += idf * tf * (self.k1 + 1) / denom * qn
            if score > 0:
                scored.append((round(score, 4), self.docs[i]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]


# ------------------------------------------------------------------ 图谱
class Graph:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.nodes = {n["id"]: n for n in data.get("nodes", [])}
        self.edges = data.get("edges", [])
        self.out: Dict[str, List[Dict[str, Any]]] = {}
        self.inc: Dict[str, List[Dict[str, Any]]] = {}
        for e in self.edges:
            self.out.setdefault(e["source"], []).append(e)
            self.inc.setdefault(e["target"], []).append(e)

    def stats(self) -> Dict[str, Any]:
        types: Counter = Counter(n.get("type", "?") for n in self.nodes.values())
        return {"nodes": len(self.nodes), "edges": len(self.edges), "types": dict(types),
                "version": self.data.get("version"), "generated_at": self.data.get("generated_at")}

    def node(self, nid: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(nid)

    def neighbors(self, nid: str, depth: int = 1) -> Dict[str, Any]:
        if nid not in self.nodes:
            return {"id": nid, "found": False, "nodes": [], "edges": []}
        seen = {nid}
        edges: List[Dict[str, Any]] = []
        frontier = [nid]
        for _ in range(max(1, depth)):
            nxt = []
            for cur in frontier:
                for e in self.out.get(cur, []) + self.inc.get(cur, []):
                    other = e["target"] if e["source"] == cur else e["source"]
                    if e not in edges:
                        edges.append(e)
                    if other not in seen:
                        seen.add(other)
                        nxt.append(other)
            frontier = nxt
        return {"id": nid, "found": True,
                "nodes": [self.nodes[n] for n in seen if n in self.nodes],
                "edges": edges}

    def search(self, query: str, k: int = 8) -> List[Dict[str, Any]]:
        q = query.lower()
        hits = []
        for n in self.nodes.values():
            text = " ".join(str(n.get(key, "")) for key in ("id", "label", "type", "summary"))
            if q in text.lower():
                hits.append(n)
        hits.sort(key=lambda n: (n.get("type", ""), n["id"]))
        return hits[:k]

    def wiki(self) -> List[Dict[str, Any]]:
        pages = []
        for n in sorted(self.nodes.values(), key=lambda x: (x.get("type", ""), x["id"])):
            out_edges = self.out.get(n["id"], [])
            in_edges = self.inc.get(n["id"], [])
            pages.append({
                "id": n["id"], "type": n.get("type"), "label": n.get("label"),
                "summary": n.get("summary", ""), "ref": n.get("source_ref", ""),
                "out": len(out_edges), "in": len(in_edges),
                "links": sorted({(e["relation"], e["target"] if e["source"] == n["id"] else e["source"])
                                 for e in out_edges + in_edges}),
            })
        return pages


# ------------------------------------------------------------------ 索引
_INDEX: Optional[Dict[str, Any]] = None
_BM25: Optional[BM25] = None
_GRAPH: Optional[Graph] = None


def index_path() -> str:
    return os.path.join(core.path_of("runtime"), "index.json")


def graph_path() -> str:
    return core.path_of("graph")


def load_index() -> Dict[str, Any]:
    global _INDEX, _BM25
    if _INDEX is None:
        with open(index_path(), "r", encoding="utf-8") as fh:
            _INDEX = json.load(fh)
        _BM25 = BM25(_INDEX["chunks"])
    return _INDEX


def load_graph() -> Graph:
    global _GRAPH
    if _GRAPH is None:
        with open(graph_path(), "r", encoding="utf-8") as fh:
            _GRAPH = Graph(json.load(fh))
    return _GRAPH


def search(query: str, k: int = 6) -> List[Dict[str, Any]]:
    load_index()
    assert _BM25 is not None
    return [{"score": s, **doc} for s, doc in _BM25.search(query, k)]


def retrieve_context(query: str, k: int = 4) -> Dict[str, Any]:
    """检索 + 图谱一轮扩散，作为建议生成的证据包。"""
    chunks = search(query, k)
    graph = load_graph()
    fact_ids: List[str] = []
    for c in chunks:
        fact_ids.extend(c.get("facts", []))
    seen, neighbors = set(), []
    for fid in fact_ids[:6]:
        nb = graph.neighbors(fid, depth=1)
        for n in nb.get("nodes", []):
            if n["id"] not in seen and n["id"] != fid:
                seen.add(n["id"])
                neighbors.append({"id": n["id"], "type": n.get("type"), "label": n.get("label")})
    return {"chunks": chunks, "facts": sorted(set(fact_ids)),
            "related": neighbors[:12], "query": query}
