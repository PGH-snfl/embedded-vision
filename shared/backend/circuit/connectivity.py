"""Only confirmed edges form confirmed nets. Geometry intersections do not join nets."""
from .schema import Graph, Status


def derive_nets(graph: Graph, include_inferred: bool = False):
    parents = {t.id: t.id for c in graph.components for t in c.terminals}

    def root(t):
        while parents[t] != t:
            t = parents[t]
        return t

    for link in graph.links:
        eligible = link.connection.status == Status.CONFIRMED or (
            include_inferred and link.connection.status == Status.INFERRED)
        if eligible:
            a, b = root(link.from_terminal), root(link.to_terminal)
            parents[max(a, b)] = min(a, b)
    groups = {}
    for t in sorted(parents):
        groups.setdefault(root(t), []).append(t)
    return [{"id": "NET_" + key, "terminals": value} for key, value in sorted(groups.items())]


def validation(graph: Graph):
    unknown = [w.id for w in graph.links if w.connection.status == Status.UNKNOWN]
    inferred = [w.id for w in graph.links if w.connection.status == Status.INFERRED]
    unmapped = [t.id for c in graph.components for t in c.terminals if t.pin_mapping.status != Status.CONFIRMED]
    return {
        "input_revision": graph.revision,
        "schema": "PASS",
        "connectivity": "BLOCKED" if unknown or inferred or not graph.links else "REVIEWED",
        "unknown_links": unknown,
        "inferred_links": inferred,
        "unverified_pin_mappings": unmapped,
        "electrical_safety": "NOT_RUN",
        "datasheet": "NOT_RUN",
        "kicad": "BLOCKED",
        "erc": "NOT_RUN",
        "drc": "NOT_RUN",
        "spice": "NOT_RUN",
        "export_blockers": ["카탈로그 핀 매핑·부품 값·연결 확인을 완료한 뒤 KiCad 생성을 실행하세요."],
    }
