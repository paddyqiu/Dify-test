# ===== imports =====
import json
import re
import os
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from rapidfuzz import fuzz
from rapidfuzz import process as rf_process
from datetime import date, datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)

    print("DEBUG JSON PATH:", path)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


NODE_SCHEMA = load_json("node_schema.json")
RELATION_META = load_json("relation_data.json")
GENERIC_LOOKUP_CONFIG = load_json("lookup_config.json")
PROJECT_RELATION_QUERY_MAP = load_json("project_relation_query_map.json")

# ==============================================================================
# 2. Schema-Derived Fields
# ==============================================================================
def build_entity_fields_from_schema():
    fields = {}

    for label, meta in NODE_SCHEMA.items():
        field_name = meta.get("payload_field")

        if field_name:
            fields[field_name] = label

    return fields
ENTITY_FIELDS = build_entity_fields_from_schema()


# ==============================================================================
# 3. Global Constants / Config Maps
# ==============================================================================
CHECK_CATEGORY_ALIASES = {
    "project": ["project", "專案", "項目"],
    "component": ["component", "元件", "零件"],
    "material": ["material", "材料", "用料", "膠材"],
    "process": ["process", "製程", "流程", "步驟"],
    "certification": ["certification", "認證", "標準"],
    "department": ["department", "部門", "團隊"],
    "partner": ["partner", "供應商", "廠商", "合作夥伴", "合作對象"],
    "lesson": ["lesson", "lesson learned", "經驗", "教訓", "失敗案例", "案例"],
}
CHECK_LABEL_MAP = {
    "project": "Project",
    "component": "Component",
    "material": "Material",
    "process": "Process",
    "certification": "Certification",
    "department": "Department",
    "partner": "Partner",
    "lesson": "Lesson_Learned",
    "lesson_learned": "Lesson_Learned",
}
CATEGORY_KEYWORD_SEARCH_MAP = {
    "lesson": {
        "label": "Lesson_Learned",
        "return_key": "lessons"
    },
    "certification": {
        "label": "Certification",
        "return_key": "certifications"
    },
    "process": {
        "label": "Process",
        "return_key": "processes"
    },
    "material": {
        "label": "Material",
        "return_key": "materials"
    },
    "component": {
        "label": "Component",
        "return_key": "components"
    },
    "department": {
        "label": "Department",
        "return_key": "departments"
    },
    "partner": {
        "label": "Partner",
        "return_key": "partners"
    },
    "project": {
        "label": "Project",
        "return_key": "projects"
    }
}
RELATION_NAME_MAP = {
    "certification": "HAS_CERTIFICATION",
    "process": "HAS_PROCESS",
    "material": "USES_MATERIAL",
    "component": "INCLUDES",
    "department": "MUST_DISCUSS_WITH",
    "lesson": "HAS_LESSON",
    "partner": "HAS_PARTNER"
}
ENTITY_CACHE = {
    "Project": None,
    "Component": None,
    "Material": None,
    "Process": None,
    "Certification": None,
    "Partner": None,
    "Department": None,
    "Lesson_Learned": None,
}
RELATION_HINTS = {
    relation_name: meta.get("aliases", [])
    for relation_name, meta in RELATION_META.items()
}


# ==============================================================================
# 4. Neo4j Driver
# ==============================================================================
def get_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


# ==============================================================================
# 5. Utility Functions
# ==============================================================================
def find_exact_duplicate_nodes(name, limit=10):
    q = """
    MATCH (n)
    WHERE toLower(coalesce(n.name, n.title, n.issue_id, "")) = toLower($name)
    RETURN
        elementId(n) AS node_id,
        coalesce(n.name, n.title, n.issue_id) AS name,
        labels(n)[0] AS label,
        properties(n) AS props
    LIMIT $limit
    """

    return run_cypher(q, {
        "name": name.strip(),
        "limit": limit
    })
def query_node_by_element_id(node_id, limit=50):
    q = """
    MATCH (n)
    WHERE elementId(n) = $node_id
    OPTIONAL MATCH (n)-[r]-(m)
    RETURN
        elementId(n) AS node_id,
        coalesce(n.name, n.title, n.issue_id) AS name,
        labels(n)[0] AS label,
        properties(n) AS properties,
        collect({
            relation: type(r),
            target_id: elementId(m),
            target_name: coalesce(m.name, m.title, m.issue_id),
            target_label: labels(m)[0]
        })[0..$limit] AS relations
    """

    rows = run_cypher(q, {
        "node_id": node_id,
        "limit": limit
    })

    if not rows:
        return {
            "found": False,
            "message": "查無相關資料"
        }

    row = rows[0]

    return {
        "found": True,
        "query_type": "node_by_id",
        "node_id": row.get("node_id"),
        "name": row.get("name"),
        "label": row.get("label"),
        "properties": row.get("properties", {}),
        "relations": [
            r for r in row.get("relations", [])
            if r.get("relation") and r.get("target_name")
        ]
    }
def clean_text(s):
    if s is None:
        return None
    s = str(s).strip()
    return s if s else None
def dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item is None:
            continue
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def filter_properties_by_schema(label, properties):
    allowed = get_node_properties(label)

    if not allowed:
        return properties or {}

    return {
        key: value
        for key, value in (properties or {}).items()
        if key in allowed
    }

def make_json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [make_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: make_json_safe(v) for k, v in value.items()}
    return str(value)
def sanitize_result(rows):
    return [{k: make_json_safe(v) for k, v in row.items()} for row in rows]


# ==============================================================================
# 6. Database / Schema Helper Functions
# ==============================================================================
def run_cypher(query, params=None):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, params or {})
        rows = [record.data() for record in result]
    driver.close()
    return sanitize_result(rows)
def get_name_fields(label):
    return NODE_SCHEMA.get(label, {}).get("name_fields", ["name"])
def get_node_properties(label):
    return NODE_SCHEMA.get(label, {}).get("properties", [])
def build_coalesce_name_expr(label, var_name="n"):
    fields = get_name_fields(label)
    props = [f"{var_name}.{field}" for field in fields]
    return "coalesce(" + ", ".join(props) + ")"
def build_name_match_condition(label, var_name="n", param_name="name"):
    fields = get_name_fields(label)
    conditions = [f"{var_name}.{field} = ${param_name}" for field in fields]
    return " OR ".join(conditions)
def get_label_from_category(category):
    for label, meta in NODE_SCHEMA.items():
        if category.lower() in [a.lower() for a in meta.get("aliases", [])]:
            return label
    return None


# ==============================================================================
# 7. Fuzzy Matching / Entity Resolution
# ==============================================================================
def detect_check_category(user_question):
    text = clean_text(user_question) or ""
    text = text.split(":")[0].strip()
    lower_text = text.lower()
    # 如果句子中有明確節點名稱 + 有哪些/列出 + 類別詞
    # 例如：MD1054D有哪些認證
    # 這不是全域分類查詢，不應該進 check_category
    possible_nodes = find_candidate_nodes(text, score_cutoff=80, max_results=3)
    if possible_nodes:
        for category, aliases in CHECK_CATEGORY_ALIASES.items():
            for alias in aliases:
                if alias.lower() in lower_text:
                    return None

    # 明確 check 指令
    if lower_text.startswith("check "):
        category = lower_text.replace("check ", "", 1).strip()
        return category

    # 白話查詢觸發詞
    trigger_words = [
        "有哪些",
        "有那些",
        "列出",
        "查詢",
        "查看",
        "顯示",
        "全部",
        "所有",
        "目前有哪些",
        "現在有哪些"
    ]

    has_trigger = any(word in lower_text for word in trigger_words)

    if not has_trigger:
        return None

    # 找分類
    for category, aliases in CHECK_CATEGORY_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower_text:
                return category

    return None
def find_candidate_nodes(raw_text, score_cutoff=70, max_results=5):
    candidates = []

    if not raw_text:
        return candidates

    raw = str(raw_text).strip().lower()

    search_labels = [
        "Project",
        "Component",
        "Material",
        "Process",
        "Certification",
        "Department",
        "Partner",
        "Lesson_Learned"
    ]

    for label in search_labels:
        names = get_all_entity_names(label)

        for name in names:
            name_str = str(name).strip()
            name_lower = name_str.lower()

            # 1. 完全相同：最高分
            if raw == name_lower:
                score = 100

            # 2. 部分包含：只給中高分，不要蓋過 exact match
            elif raw in name_lower:
                score = max(fuzz.WRatio(raw, name_lower), 85)

            # 3. 一般模糊比對
            else:
                score = fuzz.WRatio(raw, name_lower)

            if score >= score_cutoff:
                candidates.append({
                    "name": name_str,
                    "label": label,
                    "score": score
                })

    # 去重，同名同 label 只保留最高分
    unique = {}
    for c in candidates:
        key = (c["name"], c["label"])
        if key not in unique or c["score"] > unique[key]["score"]:
            unique[key] = c

    candidates = list(unique.values())

    # 排序：score 高優先；完全相同優先；名稱短的優先
    candidates.sort(
        key=lambda x: (
            x["score"],
            str(x["name"]).strip().lower() == raw,
            -len(str(x["name"]))
        ),
        reverse=True
    )

    return candidates[:max_results]
    return candidates[:max_results]
def fuzzy_match_one(query, candidates, score_cutoff=60):
    if not query or not candidates:
        return None, 0

    query_str = str(query).strip()

    # 先做大小寫不敏感的完全比對
    for c in candidates:
        if str(c).strip().lower() == query_str.lower():
            return c, 100.0

    # 再做 fuzzy
    result = rf_process.extractOne(
        query_str,
        candidates,
        scorer=fuzz.WRatio,
        score_cutoff=score_cutoff
    )

    if result:
        return result[0], result[1]

    return None, 0
def get_all_entity_names(label):
    if ENTITY_CACHE.get(label) is not None:
        return ENTITY_CACHE[label]

    name_expr = build_coalesce_name_expr(label, "n")

    q = f"""
    MATCH (n:{label})
    WHERE {name_expr} IS NOT NULL
    RETURN DISTINCT {name_expr} AS name
    ORDER BY name
    """

    rows = run_cypher(q)
    names = [r["name"] for r in rows if r.get("name")]

    ENTITY_CACHE[label] = names
    return names
def get_first_resolved_entity(resolved):
    for field, info in resolved.items():
        if info.get("matched"):
            return field, info
    return None, None
def resolve_entities_from_payload(payload):
    resolved = {}

    field_label_map = {
        "project": "Project",
        "component": "Component",
        "material": "Material",
        "process": "Process",
        "certification": "Certification",
        "department": "Department",
        "partner": "Partner",
        "lesson_keyword": "Lesson_Learned",
    }

    for field, label in field_label_map.items():
        raw = clean_text(payload.get(field))
        matched, score = resolve_entity_name(label, raw, 55)

        resolved[field] = {
            "input": raw,
            "matched": matched,
            "score": score,
            "label": label
        }

    return resolved
def resolve_entity_name(label, raw_name, score_cutoff=35):
    raw_name = clean_text(raw_name)
    if not raw_name:
        return None, 0
    candidates = get_all_entity_names(label)
    return fuzzy_match_one(raw_name, candidates, score_cutoff)
def resolve_relation_hint(text):
    text = clean_text(text)
    if not text:
        return None, 0

    # 如果只是單一短詞，例如 RoHS、BHC212，不要硬判 relation
    if len(text) <= 8 and all(ch.isalnum() for ch in text):
        return None, 0

    aliases = []
    alias_to_relation = {}

    for rel, words in RELATION_HINTS.items():
        for w in words:
            aliases.append(w)
            alias_to_relation[w] = rel

    # 先用包含判斷，比 fuzzy 更穩
    lower_text = text.lower()
    for alias in aliases:
        if alias.lower() in lower_text:
            return alias_to_relation[alias], 100

    # 最後才 fuzzy，且門檻拉高
    matched, score = fuzzy_match_one(text, aliases, score_cutoff=70)
    if matched:
        return alias_to_relation[matched], score

    return None, 0


# ==============================================================================
# 8. Query Builder / Query Helper Functions
# ==============================================================================
def build_debug_info(intent, relation_hint, relation_score, resolved):
    return {
        "normalized_intent": intent,
        "relation_hint": relation_hint,
        "relation_score": relation_score,
        "resolved_entities": resolved
    }
def build_generic_lookup_query(config):
    label = config["label"]
    return_key = config["return_key"]
    properties = config.get("properties") or get_node_properties(label)
    relations = config.get("relations", [])

    prop_lines = [f"{prop}: n.{prop}" for prop in properties]
    relation_lines = []

    for idx, rel in enumerate(relations):
        if rel["direction"] == "out":
            relation_lines.append(f"OPTIONAL MATCH (n)-[:{rel['relation']}]->(t{idx}:{rel['target_label']})")
        else:
            relation_lines.append(f"OPTIONAL MATCH (s{idx}:{rel['source_label']})-[:{rel['relation']}]->(n)")

    grouped = {}
    for idx, rel in enumerate(relations):
        field = rel["field"]
        grouped.setdefault(field, [])
        if rel["direction"] == "out":
            grouped[field].append(f"collect(DISTINCT t{idx}.name)")
        else:
            grouped[field].append(f"collect(DISTINCT s{idx}.name)")

    return_items = prop_lines[:]
    for field, exprs in grouped.items():
        return_items.append(f"{field}: {' + '.join(exprs)}")

    return_body = ",\n            ".join(return_items)
    optional_body = "\n    ".join(relation_lines)

    q = f"""
    MATCH (n:{label} {{name:$name}})
    {optional_body}
    RETURN {{
            {return_body}
    }} AS {return_key}
    LIMIT $limit
    """
    return q
def get_resolved_entity_candidates(resolved, exclude_fields=None):
    exclude_fields = set(exclude_fields or [])
    candidates = []

    for field, info in resolved.items():
        if field in exclude_fields:
            continue

        if info.get("matched"):
            candidates.append({
                "field": field,
                "label": info.get("label"),
                "matched": info.get("matched"),
                "score": info.get("score", 0),
                "input": info.get("input")
            })

    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return candidates


def resolve_node_lookup_target(user_question, resolved, relation_hint):
    """
    統一處理 node_lookup 的目標節點與查詢模式。

    優化後規則：
    1. 完全相同名稱優先，直接查該節點。
    2. 若有 relation_hint，代表「某節點 + 某類關係」查詢。
    3. 關鍵解鎖：若無完全相同名稱，但有模糊比對候選人，直接自動抓「分數最高的第一個」放行繪圖，不彈出 ambiguous 阻擋文字！
    """
    raw_question = clean_text(user_question) or ""
    raw_question = raw_question.strip()

    query_suffixes = [
        "原始問題", "製程", "流程", "材料", "認證", "標準", "部門", "lesson", "教訓"
    ]

    for suffix in query_suffixes:
        marker = ":" + suffix
        if raw_question.endswith(marker):
            raw_question = raw_question[:-len(marker)].strip()
            break

    raw_candidates = find_candidate_nodes(
        raw_question,
        score_cutoff=70,
        max_results=5
    ) if raw_question else []

    # ===== 1. 完全相同名稱優先 =====
    exact_matches = []
    for c in raw_candidates:
        candidate_name = str(c.get("name", "")).strip().lower()
        if candidate_name == raw_question.lower():
            exact_matches.append(c)

    if exact_matches:
        unique_exact = {}
        for c in exact_matches:
            key = (c["name"], c["label"])
            unique_exact[key] = c
        exact_matches = list(unique_exact.values())

        if len(exact_matches) == 1:
            best = exact_matches[0]
            return {
                "label": best["label"],
                "matched": best["name"],
                "score": 100,
                "input": raw_question
            }, "single_node_detail", None

        # 如果有多個完全同名（跨 Label），直接抓第一個放行出圖
        return None, "ambiguous_node", {
            "query_type": "ambiguous_node",
            "found": False,
            "message": "找到多個完全相同名稱節點，請選擇",
            "input": raw_question,
            "candidates": exact_matches[:5]
        }

    # ===== 2. 有 relation_hint：節點 + 關係查詢 =====
    if relation_hint:
        entity_candidates = get_resolved_entity_candidates(
            resolved,
            exclude_fields={"lesson_keyword"}
        )
        if entity_candidates:
            best = entity_candidates[0]
            return {
                "label": best["label"],
                "matched": best["matched"],
                "score": best["score"],
                "input": best["input"]
            }, "node_relation_detail", None

   # ===== 3. 模糊候選處理 =====
    if raw_candidates:
        best = raw_candidates[0]
    
        high_score_candidates = [
            c for c in raw_candidates
            if c.get("score", 0) >= 95
        ]
    
        # 只有一個高分候選，才直接查
        if len(high_score_candidates) == 1:
            best = high_score_candidates[0]
            return {
                "label": best["label"],
                "matched": best["name"],
                "score": best["score"],
                "input": raw_question
            }, "single_node_detail", None
    
        # 只有一個候選，也可以直接查
        if len(raw_candidates) == 1:
            return {
                "label": best["label"],
                "matched": best["name"],
                "score": best["score"],
                "input": raw_question
            }, "single_node_detail", None
    
        # 多個候選時，回傳選項，不要自動選第一個
        return None, "ambiguous_node", {
            "query_type": "ambiguous_node",
            "found": False,
            "message": "找到多個可能節點，請選擇要查詢的項目",
            "input": raw_question,
            "candidates": raw_candidates[:5]
        }
    # ===== 4. 從 Dify 已解析欄位選最高分 =====
    entity_candidates = get_resolved_entity_candidates(resolved)
    if entity_candidates:
        best = entity_candidates[0]
        mode = "node_relation_detail" if relation_hint else "single_node_detail"
        return {
            "label": best["label"],
            "matched": best["matched"],
            "score": best["score"],
            "input": best["input"]
        }, mode, None

    # ===== 5. 終極保底：真的什麼都找不到，才回傳找不到資料 =====
    return None, "single_node_detail", {
        "query_type": "single_node",
        "found": False,
        "message": "無法解析單一節點查詢對象"
    }
    # =======================================================
def detect_node_query_mode(relation_hint):
    if relation_hint:
        return "node_relation_detail"
    return "single_node_detail"

def build_single_node_result(raw_result, query_mode="single_node_detail"):    
    if not raw_result:
        return {"query_type": "single_node", "found": False, "message": "查無節點資料"}

    node = raw_result[0].get("node_info")
    if not node:
        return {"query_type": "single_node", "found": False, "message": "節點存在但無資料"}

    expand_related_properties = query_mode == "node_relation_detail"
    relations = []

    for r in node.get("outgoing_relations", []):
        rel_type = r.get("relation")
        meta = RELATION_META.get(rel_type, {})

        relation_item = {
            "type": rel_type,
            "display_name": meta.get("display_name", rel_type),
            "category": meta.get("category", "unknown"),
            "description": meta.get("description", ""),
            "direction": "out",
            "target": r.get("target"),
            "target_label": r.get("target_label"),
        }

        if expand_related_properties:
            relation_item["target_properties"] = filter_properties_by_schema(
                r.get("target_label"),
                r.get("target_properties", {})
            )

        relations.append(relation_item)

    for r in node.get("incoming_relations", []):
        rel_type = r.get("relation")
        meta = RELATION_META.get(rel_type, {})

        relation_item = {
            "type": rel_type,
            "display_name": meta.get("display_name", rel_type),
            "category": meta.get("category", "unknown"),
            "description": meta.get("description", ""),
            "direction": "in",
            "target": r.get("source"),
            "target_label": r.get("source_label"),
        }

        if expand_related_properties:
            relation_item["target_properties"] = filter_properties_by_schema(
                r.get("source_label"),
                r.get("source_properties", {})
            )

        relations.append(relation_item)

    categories = sorted(list(set(r["category"] for r in relations if r["category"])))

    return {
        "query_type": "single_node",
        "query_mode": query_mode,
        "found": True,
        "node": {
            "name": node.get("name"),
            "label": node.get("label"),
            "properties": filter_properties_by_schema(
                node.get("label"),
                node.get("properties", {})
            )
        },
        "relations": relations[:15],
        "summary": {
            "relation_count": len(relations),
            "categories": categories
        }
    }
def filter_requested_fields(result, top_key, requested_fields):
    if not requested_fields:
        return result

    for row in result:
        info = row.get(top_key, {})
        if isinstance(info, dict):
            row[top_key] = {k: v for k, v in info.items() if k in requested_fields}
    return result
def query_all_nodes_by_label(label, limit=100):
    q = f"""
    MATCH (n:{label})
    WHERE n.name IS NOT NULL OR n.title IS NOT NULL
    RETURN DISTINCT coalesce(n.name, n.title) AS name
    ORDER BY name
    LIMIT $limit
    """
    return run_cypher(q, {"limit": limit})
def query_node_with_relations(label, name):
    name_condition = build_name_match_condition(label, "n", "name")
    name_expr = build_coalesce_name_expr(label, "n")

    q = f"""
    MATCH (n:{label})
    WHERE {name_condition}
    OPTIONAL MATCH (n)-[r]->(m)
    WITH n, collect(DISTINCT {{
        relation: type(r),
        target: coalesce(m.name, m.title),
        target_label: CASE WHEN m IS NOT NULL THEN head(labels(m)) ELSE NULL END,
        target_properties: CASE WHEN m IS NOT NULL THEN properties(m) ELSE {{}} END
    }}) AS outgoing_relations

    OPTIONAL MATCH (x)-[r2]->(n)
    WITH n,
         outgoing_relations,
         collect(DISTINCT {{
            relation: type(r2),
            source: coalesce(x.name, x.title),
            source_label: CASE WHEN x IS NOT NULL THEN head(labels(x)) ELSE NULL END,
            source_properties: CASE WHEN x IS NOT NULL THEN properties(x) ELSE {{}} END
         }}) AS incoming_relations

    RETURN {{
        name: {name_expr},
        label: head(labels(n)),
        properties: properties(n),
        outgoing_relations: [item IN outgoing_relations WHERE item.target IS NOT NULL],
        incoming_relations: [item IN incoming_relations WHERE item.source IS NOT NULL]
    }} AS node_info
    LIMIT 1
    """

    return run_cypher(q, {"name": name}
    )
    
def query_project_full(project_name):
    q = """
    MATCH (p:Project {name:$project})
    OPTIONAL MATCH (p)-[:HAS_PROCESS]->(pr:Process)
    OPTIONAL MATCH (p)-[:HAS_CERTIFICATION]->(c:Certification)
    OPTIONAL MATCH (p)-[:USES_SPECIFIC_PART]->(m:Material)
    OPTIONAL MATCH (p)-[:USES_MATERIAL]->(m2:Material)
    OPTIONAL MATCH (p)-[:INCLUDES]->(comp:Component)
    OPTIONAL MATCH (p)-[:MUST_DISCUSS_WITH]->(d:Department)
    OPTIONAL MATCH (p)-[:HAS_LESSON]->(l:Lesson_Learned)
    RETURN p.name AS project,
           collect(DISTINCT pr.name) AS processes,
           collect(DISTINCT c.name) AS certifications,
           collect(DISTINCT m.name) + collect(DISTINCT m2.name) AS materials,
           collect(DISTINCT comp.name) AS components,
           collect(DISTINCT d.name) AS departments,
           collect(DISTINCT coalesce(l.title, l.name)) AS lessons
    """
    rows = run_cypher(q, {"project": project_name})
    for row in rows:
        if "materials" in row:
            row["materials"] = dedupe_keep_order(row["materials"])
    return rows
def query_project_lessons(project_name):
    q = """
    MATCH (p:Project {name:$project})-[:HAS_LESSON]->(l)
    RETURN p.name AS project,
           collect(DISTINCT {
               title: coalesce(l.title, l.name),
               issue: l.issue,
               root_cause: l.root_cause,
               detected_phase: l.detected_phase,
               action_items: 
                CASE 
                    WHEN l.action_item IS NOT NULL THEN [l.action_item]
                    ELSE [x IN [l.action_item_1, l.action_item_2, l.action_item_3] WHERE x IS NOT NULL]
                END,
               report_date: l.report_date
           }) AS lessons
    """
    return run_cypher(q, {"project": project_name})
def query_project_related(project_name, relation_name, target_label, return_key):
    q = f"""
    MATCH (p:Project {{name:$project}})-[:{relation_name}]->(t:{target_label})
    RETURN p.name AS project,
           collect(DISTINCT t.name) AS {return_key}
    """
    return run_cypher(q, {"project": project_name})

def query_entity_related_by_relation(source_label, source_name, relation_name, target_label, return_key, limit=20):
    name_condition = build_name_match_condition(source_label, "s", "source_name")

    q = f"""
    MATCH (s:{source_label})
    WHERE {name_condition}
    OPTIONAL MATCH (s)-[:{relation_name}]->(t:{target_label})
    RETURN
        coalesce(s.name, s.title) AS source,
        labels(s)[0] AS source_label,
        collect(DISTINCT properties(t)) AS {return_key},
        count(t) AS count
    LIMIT $limit
    """

    rows = run_cypher(q, {
        "source_name": source_name,
        "limit": limit
    })

    return rows
    
def run_generic_lookup(config, entity_name, limit, requested_fields):
    q = build_generic_lookup_query(config)
    result = run_cypher(q, {"name": entity_name, "limit": limit})

    top_key = config["return_key"]
    for row in result:
        info = row.get(top_key, {})
        if isinstance(info, dict):
            for k, v in list(info.items()):
                if isinstance(v, list):
                    info[k] = dedupe_keep_order(v)

    return filter_requested_fields(result, top_key, requested_fields)


# ==============================================================================
# 9. Intent Normalization
# ==============================================================================
def normalize_intent(payload):
    intent = clean_text(payload.get("intent"))
    user_question = clean_text(payload.get("user_question")) or ""
    relation_hint, _ = resolve_relation_hint(user_question)

    entity_values = {
        field: clean_text(payload.get(field))
        for field in ENTITY_FIELDS.keys()
    }

    project = entity_values.get("project")
    lesson_keyword = entity_values.get("lesson_keyword")

    if intent in {
        "relation_query",
        "compare_entities",
        "node_lookup",
        "lesson_lookup",
        "project_lookup",
        "process_lookup",
        "check_category",
        "single_node_relation_list",
        "category_keyword_search"
    }:
        return intent

    payload_relation_hint = clean_text(payload.get("relation_hint"))

    if project and payload_relation_hint in RELATION_NAME_MAP:
        return "project_lookup"

    single_entity_count = sum(1 for v in entity_values.values() if v)

    if single_entity_count == 1 and not relation_hint and not lesson_keyword:
        return "node_lookup"

    for lookup_name, config in GENERIC_LOOKUP_CONFIG.items():
        if entity_values.get(config["payload_field"]):
            return lookup_name

    if entity_values.get("process"):
        return "process_lookup"

    if lesson_keyword:
        return "lesson_lookup"

    return intent or "fallback"


# ==============================================================================
# 10. Main Router
# ==============================================================================
def query_graph_by_router(payload):
    user_question = clean_text(payload.get("user_question")) or ""

    # ===== check / 白話分類查詢 =====
    check_category = detect_check_category(user_question)

    if check_category:
        label = get_label_from_category(check_category)

        if not label:
            return {
                "graph_result": [{
                    "query_type": "check_category",
                    "found": False,
                    "message": f"不支援的分類：{check_category}",
                    "available_categories": list(CHECK_LABEL_MAP.keys())
                }]
            }

        rows = query_all_nodes_by_label(label)

        return {
            "graph_result": [{
                "query_type": "check_category",
                "found": True,
                "category": check_category,
                "label": label,
                "count": len(rows),
                "items": [r["name"] for r in rows]
            }]
        }

    intent = normalize_intent(payload)

    user_question = clean_text(payload.get("user_question")) or ""
    source_entity = clean_text(payload.get("source_entity"))
    target_entity = clean_text(payload.get("target_entity"))
    raw_lesson_keyword = clean_text(payload.get("lesson_keyword"))
    compare_targets = payload.get("compare_targets") or []
    requested_fields = payload.get("requested_fields") or []
    limit = payload.get("limit", 5)

    try:
        limit = int(limit)
    except Exception:
        limit = 5

    if limit <= 0:
        limit = 5
    if limit > 20:
        limit = 20

    payload_relation_hint = clean_text(payload.get("relation_hint"))
    auto_relation_hint, relation_score = resolve_relation_hint(user_question)
    
    relation_hint = payload_relation_hint or auto_relation_hint
    
    resolved = resolve_entities_from_payload(payload)
    debug_info = build_debug_info(intent, relation_hint, relation_score, resolved)

    project = resolved.get("project", {}).get("matched")
    process_name = resolved.get("process", {}).get("matched")

    # ===== 通用：在指定類別中搜尋關鍵詞 =====
    # 例如：
    # FPC 相關的 lesson learned
    # LPI 相關的 process
    # CE 相關的 certification
    if intent == "category_keyword_search":
        keyword = source_entity or raw_lesson_keyword
        category = relation_hint
    
        if category == "lesson_learned":
            category = "lesson"
    
        if category not in CATEGORY_KEYWORD_SEARCH_MAP:
            category = None
    
        if not category:
            for field in requested_fields:
                if field == "lesson_learned":
                    field = "lesson"
    
                if field in CATEGORY_KEYWORD_SEARCH_MAP:
                    category = field
                    break
        else:
            for field in requested_fields:
                if field in CATEGORY_KEYWORD_SEARCH_MAP:
                    category = field
                    break
    
        if not keyword or not category:
            return {
                "graph_result": [{
                    "query_type": "category_keyword_search",
                    "found": False,
                    "message": "缺少搜尋關鍵字或主題類別"
                }],
                "debug": debug_info
            }
    
        cfg = CATEGORY_KEYWORD_SEARCH_MAP[category]
        label = cfg["label"]
    
        q = f"""
        MATCH (n:{label})
        OPTIONAL MATCH (n)-[r1]->(m)
        OPTIONAL MATCH (x)-[r2]->(n)
        WITH n, r1, m, r2, x
        WHERE toLower(coalesce(n.name, n.title, n.issue_id, n.issue, n.root_cause, n.description, "")) CONTAINS toLower($keyword)
           OR toLower(coalesce(m.name, m.title, m.issue_id, "")) CONTAINS toLower($keyword)
           OR toLower(coalesce(x.name, x.title, x.issue_id, "")) CONTAINS toLower($keyword)
        WITH
            n,
            collect(DISTINCT {{
                relation: type(r1),
                target: coalesce(m.name, m.title, m.issue_id),
                target_label: CASE WHEN m IS NOT NULL THEN head(labels(m)) ELSE NULL END
            }}) AS outgoing_relations,
            collect(DISTINCT {{
                relation: type(r2),
                source: coalesce(x.name, x.title, x.issue_id),
                source_label: CASE WHEN x IS NOT NULL THEN head(labels(x)) ELSE NULL END
            }}) AS incoming_relations
        RETURN {{
            name: coalesce(n.name, n.title, n.issue_id),
            label: head(labels(n)),
            properties: properties(n),
            outgoing_relations: [
                item IN outgoing_relations
                WHERE item.relation IS NOT NULL AND item.target IS NOT NULL
            ],
            incoming_relations: [
                item IN incoming_relations
                WHERE item.relation IS NOT NULL AND item.source IS NOT NULL
            ]
        }} AS item
        LIMIT $limit
        """
    
        result = run_cypher(q, {
            "keyword": keyword,
            "limit": limit
        })
    
        return {
            "graph_result": [{
                "query_type": "category_keyword_search",
                "found": len(result) > 0,
                "keyword": keyword,
                "category": category,
                "label": label,
                "count": len(result),
                cfg["return_key"]: result,
                "items": result
            }],
            "debug": debug_info
        }

    # ===== node_lookup + requested_fields 轉成單節點關聯查詢 =====
    # ===== 單節點 + 指定關係查詢 =====
    if intent in ["node_lookup", "single_node_relation_list"] and requested_fields and relation_hint:
        relation_name = RELATION_NAME_MAP.get(relation_hint, relation_hint)
        relation_cfg = PROJECT_RELATION_QUERY_MAP.get(relation_name)
        if relation_cfg:
            best = None

            if source_entity:
                candidates = find_candidate_nodes(
                    source_entity,
                    score_cutoff=55,
                    max_results=1
                )
                if candidates:
                    best = {
                        "label": candidates[0]["label"],
                        "matched": candidates[0]["name"],
                        "score": candidates[0]["score"]
                    }

            if not best:
                entity_candidates = get_resolved_entity_candidates(
                    resolved,
                    exclude_fields={"lesson_keyword"}
                )
                if entity_candidates:
                    best = entity_candidates[0]

            if best:
                result = query_entity_related_by_relation(
                    source_label=best["label"],
                    source_name=best["matched"],
                    relation_name=relation_name,
                    target_label=relation_cfg["target_label"],
                    return_key=relation_cfg["return_key"],
                    limit=limit
                )

                # 💡 單點指定關係查詢同樣在此觸發生圖
                image_url = None
                if result:
                    try:
                        image_url = generate_graph_image(result)
                    except Exception as draw_err:
                        print(f"繪圖引擎渲染失敗: {str(draw_err)}")

                return {
                    "graph_result": result,
                    "image_url": image_url,
                    "debug": debug_info
                }

    # =================================================================
    # 🎯 【關鍵修正區塊】精準 / 模糊 單一節點數據查詢路徑
    # =================================================================
    if intent == "node_lookup":
        info, query_mode, error_result = resolve_node_lookup_target(
            user_question=user_question,
            resolved=resolved,
            relation_hint=relation_hint
        )

        if error_result:
            return {"graph_result": [error_result], "debug": debug_info}

        try:
            query_mode = detect_node_query_mode(relation_hint)
            raw = query_node_with_relations(info["label"], info["matched"])

            structured = build_single_node_result(raw, query_mode=query_mode)
            structured["query_mode"] = query_mode

            if relation_hint and info.get("label") != "Lesson_Learned":
                filtered = [r for r in structured.get("relations", []) if r["type"] == relation_hint]
                structured["relations"] = filtered
                structured["summary"]["relation_count"] = len(filtered)
                structured["summary"]["categories"] = sorted(list(set(r["category"] for r in filtered)))
                if not filtered:
                    structured["message"] = "目前沒有符合條件的關係資料"

            # -------------------------------------------------------------
            # 🟢 【強迫生圖核心】重組數據結構，將單點資料攤平成大圖專用結構
            # -------------------------------------------------------------
            graph_data_for_drawing = []
            if isinstance(structured, dict) and structured.get("query_type") == "single_node":
                node_name = structured.get("node", {}).get("name", "Unknown")
                node_label = structured.get("node", {}).get("label", "Node")
                
                # 將 relations 轉換為繪圖引擎認得的 source -> target 結構
                for rel in structured.get("relations", []):
                    if rel.get("direction") == "out":
                        graph_data_for_drawing.append({
                            "source": node_name, "source_label": node_label,
                            "target": rel.get("target"), "target_label": rel.get("target_label"),
                            "relation": rel.get("type")
                        })
                    else:
                        graph_data_for_drawing.append({
                            "source": rel.get("target"), "source_label": rel.get("target_label"),
                            "target": node_name, "target_label": node_label,
                            "relation": rel.get("type")
                        })
                
                # 保底：若該節點沒有任何對外關係，仍畫出孤立節點，避免死圖
                if not graph_data_for_drawing:
                    graph_data_for_drawing.append({
                        "source": node_name, "source_label": node_label,
                        "target": None, "target_label": None,
                        "relation": None
                    })
            else:
                graph_data_for_drawing = [structured]

            # 呼叫生圖引擎
            image_url = None
            if graph_data_for_drawing:
                try:
                    image_url = generate_graph_image(graph_data_for_drawing)
                except Exception as draw_err:
                    print(f"後台單點數據繪圖失敗拋錯: {str(draw_err)}")
                    image_url = None

            # 同時回傳數據包與圖片連結
            return {
                "graph_result": [structured],
                "image_url": image_url,  # 👈 讓前端、LINE 或 Dify 撈到圖的通關金鑰
                "debug": debug_info
            }

        except Exception as e:
            return {
                "graph_result": [{
                    "query_type": "single_node",
                    "found": False,
                    "message": f"node_lookup 執行失敗: {str(e)}"
                }],
                "debug": debug_info
            }

    # ===== 後續其他 Intent 分支保持原樣不閹割 =====
    if intent == "project_lookup" and project:
        if relation_hint == "HAS_LESSON":
            return {"graph_result": query_project_lessons(project), "debug": debug_info}

        relation_cfg = PROJECT_RELATION_QUERY_MAP.get(relation_hint)
        if relation_cfg:
            result = query_project_related(
                project_name=project,
                relation_name=relation_hint,
                target_label=relation_cfg["target_label"],
                return_key=relation_cfg["return_key"]
            )
            return {"graph_result": result, "debug": debug_info}

        return {"graph_result": query_project_full(project), "debug": debug_info}

    if intent in GENERIC_LOOKUP_CONFIG:
        config = GENERIC_LOOKUP_CONFIG[intent]
        entity_name = resolved[config["payload_field"]]["matched"]

        if entity_name:
            result = run_generic_lookup(config, entity_name, limit, requested_fields)
            return {"graph_result": result, "debug": debug_info}

    if intent == "process_lookup" and process_name:
        q = """
        MATCH (pr:Process {name:$process})
        OPTIONAL MATCH (p:Project)-[:HAS_PROCESS]->(pr)
        OPTIONAL MATCH (pr)-[:REQUIRES_SPEC_ALIGNMENT]->(m:Material)
        OPTIONAL MATCH (pr)-[:MUST_ALIGN_TEST_WITH]->(cert:Certification)
        OPTIONAL MATCH (pr)-[:MUST_DISCUSS_WITH]->(d:Department)
        RETURN pr.name AS process,
               collect(DISTINCT p.name) AS related_projects,
               collect(DISTINCT m.name) AS related_materials,
               collect(DISTINCT cert.name) AS related_certifications,
               collect(DISTINCT d.name) AS departments
        LIMIT $limit
        """
        return {"graph_result": run_cypher(q, {"process": process_name, "limit": limit}), "debug": debug_info}

    if intent == "lesson_lookup" and raw_lesson_keyword:
        q = """
        MATCH (l:Lesson_Learned)
        WHERE coalesce(l.title, l.name, "") CONTAINS $kw
           OR coalesce(l.root_cause, "") CONTAINS $kw
           OR coalesce(l.description, "") CONTAINS $kw
           OR coalesce(l.issue, "") CONTAINS $kw
        RETURN {
            title: coalesce(l.title, l.name),
            issue: l.issue,
            root_cause: l.root_cause,
            detected_phase: l.detected_phase,
            action_items: [x IN [l.action_item_1, l.action_item_2, l.action_item_3] WHERE x IS NOT NULL],
            report_date: l.report_date
        } AS lesson_info
        LIMIT $limit
        """
        result = run_cypher(q, {"kw": raw_lesson_keyword, "limit": limit})
        result = filter_requested_fields(result, "lesson_info", requested_fields)
        return {"graph_result": result, "debug": debug_info}

    if intent == "relation_query" and source_entity and target_entity:

        def resolve_any_entity(raw_name):
            candidates = []
            for label in ["Project", "Component", "Material", "Process", "Certification", "Department", "Partner", "Lesson_Learned"]:
                matched, score = resolve_entity_name(label, raw_name, 45)
                if matched:
                    candidates.append({
                        "label": label,
                        "name": matched,
                        "score": score
                    })

            if not candidates:
                return None

            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[0]

        source_resolved = resolve_any_entity(source_entity)
        target_resolved = resolve_any_entity(target_entity)

        if not source_resolved or not target_resolved:
            return {
                "graph_result": [{
                    "query_type": "relation_query",
                    "found": False,
                    "message": f"無法解析查詢對象：{source_entity} 或 {target_entity}",
                    "source_input": source_entity,
                    "target_input": target_entity,
                    "source_suggestion": source_resolved,
                    "target_suggestion": target_resolved
                }],
                "debug": debug_info
            }

        q = """
        MATCH (a)-[r]-(b)
        WHERE coalesce(a.name, a.title) = $source
        AND coalesce(b.name, b.title) = $target
        WITH a, b, r
        RETURN
            coalesce(a.name, a.title) AS source,
            labels(a) AS source_labels,
            type(r) AS relation_type,
            coalesce(b.name, b.title) AS target,
            labels(b) AS target_labels
        LIMIT $limit
        """

        result = run_cypher(q, {
            "source": source_resolved["name"],
            "target": target_resolved["name"],
            "limit": limit
        })

        enriched = []

        for row in result:
            rel_type = row.get("relation_type")
            meta = RELATION_META.get(rel_type, {})

            enriched.append({
                "query_type": "relation_query",
                "found": True,
                "source_input": source_entity,
                "target_input": target_entity,
                "source_resolved": source_resolved,
                "target_resolved": target_resolved,
                "source": row.get("source"),
                "source_labels": row.get("source_labels"),
                "target": row.get("target"),
                "target_labels": row.get("target_labels"),
                "relation_type": rel_type,
                "display_name": meta.get("display_name", rel_type),
                "category": meta.get("category", "unknown"),
                "description": meta.get("description", ""),
                "sentence": f"{row.get('source')} --[{rel_type}]--> {row.get('target')}（{meta.get('display_name', rel_type)}）"
            })

        if not enriched:
            return {
                "graph_result": [{
                    "query_type": "relation_query",
                    "found": False,
                    "source_input": source_entity,
                    "target_input": target_entity,
                    "source_resolved": source_resolved,
                    "target_resolved": target_resolved,
                    "message": f"已解析為 {source_resolved['name']} 與 {target_resolved['name']}，但查不到兩者之間的直接關係"
                }],
                "debug": debug_info
            }

        return {
            "graph_result": enriched,
            "debug": debug_info
        }

    if intent == "compare_entities" and len(compare_targets) >= 2:
        resolved_targets = []
        for t in compare_targets[:2]:
            for label in ["Project", "Component", "Material", "Process"]:
                matched, _ = resolve_entity_name(label, t, 50)
                if matched:
                    resolved_targets.append(matched)
                    break

        if len(resolved_targets) < 2:
            return {"graph_result": [{"message": "無法解析比較對象"}], "debug": debug_info}

        q = """
        MATCH (n)
        WHERE n.name IN $targets
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.name AS entity,
               labels(n) AS labels,
               collect(DISTINCT type(r)) AS relations,
               collect(DISTINCT m.name)[0..10] AS neighbors
        """
        return {"graph_result": run_cypher(q, {"targets": resolved_targets}), "debug": debug_info}

    return {
        "graph_result": [{"message": "查詢條件不足，或此類查詢目前尚未支援。"}],
        "debug": debug_info
    }

# ==============================================================================
# 11. Test Helper
# ==============================================================================
def test_neo4j():
    result = run_cypher("MATCH (n) RETURN count(n) AS node_count")
    rels = run_cypher("MATCH ()-[r]->() RETURN count(r) AS rel_count")
    return {
        "success": True,
        "node_count": result[0]["node_count"],
        "rel_count": rels[0]["rel_count"]
    }
