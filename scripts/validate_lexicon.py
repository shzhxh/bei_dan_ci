#!/usr/bin/env python3
"""Validate the v4 data: 2,953-word main line (50 passages) + 289-word
中考补漏 set (5 passages), with 1,547 中考词 covered by the 27-passage route."""

from __future__ import annotations

import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PASSAGES = 50
ROUTE_PASSAGES = 22
SIZES = [60, 60, 60] + [59] * 47
TOTAL = 2953
ZK_TOTAL = 1258
SUPP_PASSAGES = 5
SUPP_SIZES = [58, 58, 58, 58, 57]
SUPP_TOTAL = 289
ROUTE_TOTAL = 27
ZK_ALL = 1547
TOTAL_ALL = 3242
POS_MIN = {"n": 30, "v": 20, "aa": 10}
SUFFIXES = (
    "ational", "ations", "ation", "ments", "ment", "ness", "ities", "ity",
    "ings", "ing", "edly", "ed", "ly", "ers", "er", "est", "es", "s",
)


def family_keys(lemmas: set[str]) -> dict[str, str]:
    mapping = {}
    for word in lemmas:
        base = word
        for suffix in SUFFIXES:
            if word.endswith(suffix):
                stem = word[: -len(suffix)]
                if len(stem) >= 4 and stem in lemmas:
                    base = stem
                    break
        mapping[word] = base
    return mapping


def pos_caps(group: list[dict]) -> dict[str, int]:
    return {
        "n": sum("n" in w["pos"] for w in group),
        "v": sum("v" in w["pos"] for w in group),
        "aa": sum(("adj" in w["pos"] or "adv" in w["pos"]) for w in group),
    }


def check_common(prefix: str, words: list[dict], problems: list[str]) -> None:
    for word in words:
        if not word.get("senses") or not word["senses"][0].get("zh"):
            problems.append(f"{prefix}/{word['lemma']} 缺中文释义")
        if not word.get("pos") or word["pos"] == ["?"]:
            problems.append(f"{prefix}/{word['lemma']} 缺词性")
        if not word.get("passage"):
            problems.append(f"{prefix}/{word['lemma']} 未分配篇目")


def main() -> None:
    lexicon = json.load(open(os.path.join(DATA, "lexicon.json"), encoding="utf-8"))
    words = lexicon["words"]
    supplement = json.load(open(os.path.join(DATA, "supplement.json"), encoding="utf-8"))
    supp = supplement["words"]
    route = json.load(open(os.path.join(DATA, "zhongkao.json"), encoding="utf-8"))
    problems: list[str] = []

    # ---------- main line ----------
    if lexicon["meta"]["total"] != TOTAL or len(words) != TOTAL:
        problems.append(f"主线词条数 {len(words)} ≠ {TOTAL}")
    if len(words) != sum(SIZES):
        problems.append("主线分篇容量与词数不一致")

    lemmas = [w["lemma"] for w in words]
    dup = [w for w, n in collections.Counter(lemmas).items() if n > 1]
    if dup:
        problems.append(f"主线重复词条：{dup[:10]}")
    check_common("main", words, problems)

    for word in words:
        if word.get("star_source") != "collins" or word.get("stars") not in (3, 4, 5):
            problems.append(f"{word['lemma']} 不是纯 Collins 3–5★")

    groups = collections.defaultdict(list)
    for word in words:
        groups[word["passage"]].append(word)
    if len(groups) != PASSAGES:
        problems.append(f"主线篇目数 {len(groups)} ≠ {PASSAGES}")
    actual_sizes = [len(groups[f"s3000-p{i:02d}"]) for i in range(1, PASSAGES + 1)]
    if actual_sizes != SIZES:
        problems.append(f"主线分篇词数 {actual_sizes} 与方案不一致")

    zk = [w for w in words if "zk" in w["exams"]]
    if len(zk) != ZK_TOTAL:
        problems.append(f"主线中考词 {len(zk)} ≠ {ZK_TOTAL}")
    zk_late = [w["lemma"] for w in zk if int(w["passage"].split("p")[-1]) > ROUTE_PASSAGES]
    if zk_late:
        problems.append(f"主线中考词落在 {ROUTE_PASSAGES} 篇之后：{zk_late[:10]}")

    for i in range(1, PASSAGES + 1):
        caps = pos_caps(groups[f"s3000-p{i:02d}"])
        for key, minimum in POS_MIN.items():
            if caps[key] < minimum:
                problems.append(f"主线 p{i:02d} 可用{key}词性 {caps[key]} < {minimum}")

    families = family_keys(set(lemmas))
    collisions = []
    for passage, group in groups.items():
        counts = collections.Counter(families.get(w["lemma"], w["lemma"]) for w in group)
        for fam, n in counts.items():
            if n > 1:
                collisions.append((passage, fam, n))
    if collisions:
        problems.append(f"主线同族词同篇：{collisions[:5]}")

    # ---------- supplement ----------
    if supplement["meta"]["total"] != SUPP_TOTAL or len(supp) != SUPP_TOTAL:
        problems.append(f"补漏词条数 {len(supp)} ≠ {SUPP_TOTAL}")
    if len(supp) != sum(SUPP_SIZES):
        problems.append("补漏分篇容量与词数不一致")
    supp_lemmas = [w["lemma"] for w in supp]
    supp_dup = [w for w, n in collections.Counter(supp_lemmas).items() if n > 1]
    if supp_dup:
        problems.append(f"补漏重复词条：{supp_dup[:10]}")
    overlap = set(lemmas) & set(supp_lemmas)
    if overlap:
        problems.append(f"主线与补漏重词：{sorted(overlap)[:10]}")
    check_common("supp", supp, problems)

    for word in supp:
        if word.get("stars") != 0 or word.get("star_source") != "zhongkao":
            problems.append(f"{word['lemma']} 补漏来源标注错误")
        if "zk" not in word["exams"]:
            problems.append(f"{word['lemma']} 补漏词无中考标签")

    supp_groups = collections.defaultdict(list)
    for word in supp:
        supp_groups[word["passage"]].append(word)
    if len(supp_groups) != SUPP_PASSAGES:
        problems.append(f"补漏篇目数 {len(supp_groups)} ≠ {SUPP_PASSAGES}")
    supp_actual = [len(supp_groups[f"s3000-b{i:02d}"]) for i in range(1, SUPP_PASSAGES + 1)]
    if supp_actual != SUPP_SIZES:
        problems.append(f"补漏分篇词数 {supp_actual} 与方案不一致")

    for i in range(1, SUPP_PASSAGES + 1):
        caps = pos_caps(supp_groups[f"s3000-b{i:02d}"])
        for key, minimum in POS_MIN.items():
            if caps[key] < minimum:
                problems.append(f"补漏 b{i:02d} 可用{key}词性 {caps[key]} < {minimum}")

    supp_families = family_keys(set(supp_lemmas))
    supp_collisions = []
    for passage, group in supp_groups.items():
        counts = collections.Counter(supp_families.get(w["lemma"], w["lemma"]) for w in group)
        for fam, n in counts.items():
            if n > 1:
                supp_collisions.append((passage, fam, n))
    if supp_collisions:
        problems.append(f"补漏同族词同篇：{supp_collisions[:5]}")

    # ---------- combined route ----------
    if route["meta"]["total"] != ZK_ALL or len(route["words"]) != ZK_ALL:
        problems.append(f"中考路线词数 {len(route['words'])} ≠ {ZK_ALL}")
    if route["meta"]["main_zhongkao"] != ZK_TOTAL or route["meta"]["supplement"] != SUPP_TOTAL:
        problems.append("中考路线来源拆分不正确")
    route_sets = collections.Counter(w.get("set") for w in route["words"])
    if route_sets.get("s3000") != ZK_TOTAL or route_sets.get("zk-supplement") != SUPP_TOTAL:
        problems.append(f"中考路线来源计数错误：{dict(route_sets)}")
    route_indexes = {w.get("route_index", 0) for w in route["words"]}
    if route_indexes != set(range(1, ROUTE_TOTAL + 1)):
        problems.append(f"中考路线序号集合异常：{sorted(route_indexes)[:5]}…")
    routes_by_passage = collections.defaultdict(set)
    for word in route["words"]:
        routes_by_passage[word["passage"]].add(word.get("route_index", 0))
    if any(len(values) != 1 for values in routes_by_passage.values()):
        problems.append("同一篇目的路线序号不一致")
    supp_route = [w for w in route["words"] if w.get("set") == "zk-supplement"]
    if any(w["route_index"] <= ROUTE_PASSAGES for w in supp_route):
        problems.append("补漏词出现在路线前 22 位")
    if any(int(w["passage"].split("b")[-1]) not in range(1, SUPP_PASSAGES + 1)
           for w in supp_route):
        problems.append("补漏词落在 b01–b05 之外")

    if len(words) + len(supp) != TOTAL_ALL:
        problems.append(f"总词数 {len(words) + len(supp)} ≠ {TOTAL_ALL}")
    if len(groups) + len(supp_groups) != PASSAGES + SUPP_PASSAGES:
        problems.append("总篇数不等于 55")

    assignment_rows = sum(
        1 for _ in open(os.path.join(DATA, "assignment.tsv"), encoding="utf-8")
    ) - 1
    if assignment_rows != len(words):
        problems.append(f"assignment.tsv 行数 {assignment_rows} ≠ {len(words)}")
    supp_rows = sum(
        1 for _ in open(os.path.join(DATA, "assignment-supplement.tsv"), encoding="utf-8")
    ) - 1
    if supp_rows != len(supp):
        problems.append(f"assignment-supplement.tsv 行数 {supp_rows} ≠ {len(supp)}")

    result = {
        "ok": not problems,
        "problems": problems,
        "main": {
            "total": len(words),
            "passages": len(groups),
            "sizes": actual_sizes,
            "per_passage": "59–60",
            "zhongkao": len(zk),
            "route_passages": ROUTE_PASSAGES,
            "route_capacity": sum(SIZES[:ROUTE_PASSAGES]),
            "star_counts": dict(sorted(collections.Counter(w["stars"] for w in words).items())),
            "pos_capability_min": {
                key: min(pos_caps(groups[f"s3000-p{i:02d}"])[key]
                         for i in range(1, PASSAGES + 1))
                for key in POS_MIN
            },
            "family_collisions": len(collisions),
        },
        "supplement": {
            "total": len(supp),
            "passages": len(supp_groups),
            "sizes": supp_actual,
            "per_passage": "57–58",
            "stars": 0,
            "star_source": "zhongkao",
            "pos_capability_min": {
                key: min(pos_caps(supp_groups[f"s3000-b{i:02d}"])[key]
                         for i in range(1, SUPP_PASSAGES + 1))
                for key in POS_MIN
            },
            "family_collisions": len(supp_collisions),
        },
        "combined": {
            "total": len(words) + len(supp),
            "passages": len(groups) + len(supp_groups),
            "zhongkao": len(route["words"]),
            "route_passages": ROUTE_TOTAL,
        },
    }
    with open(os.path.join(DATA, "validation.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
