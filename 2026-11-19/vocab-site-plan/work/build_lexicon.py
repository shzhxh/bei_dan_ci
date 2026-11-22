#!/usr/bin/env python3
"""Build the 2,953-word main lexicon plus the 289-word 中考补漏 set.

Input : data/vendor/ecdict.csv
Output: data/lexicon.json, data/supplement.json, data/zhongkao.json,
        data/assignment.tsv, data/assignment-supplement.tsv,
        data/lexicon-diagnostics.json

Selection policy (v4, see outputs/词表与许可证核验报告.md):
  1. single lowercase alphabetic/hyphenated headwords only; drop pure inflections
  2. main line = ECDICT collins 3/4/5 headwords (2,953), 50 passages
  3. supplement = 中考 (zk) headwords with blank collins (289), 5 passages
     labelled star_source = "zhongkao" and stars = 0; never disguised as 3★+
  4. no frequency top-ups in either set
"""

from __future__ import annotations

import collections
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "vendor", "ecdict.csv")
DATA = os.path.join(ROOT, "data")

TOTAL_TARGET = 2953
PER_PASSAGE = 60
PASSAGES = 50
PASSAGE_SIZES = [60, 60, 60] + [59] * 47
ZK_ROUTE_PASSAGES = 22
SUPP_TOTAL = 289
SUPP_PASSAGES = 5
SUPP_SIZES = [58, 58, 58, 58, 57]
WORD_RE = re.compile(r"^[a-z][a-z-]{1,23}$")
PURE_INFLECTION = re.compile(
    r"^(pl\.|[a-z]+的(过去式|过去分词|现在分词|第三人称单数|复数|比较级|最高级))"
)
POS_INFER = re.compile(r"^(n|v|vt|vi|a|adj|ad|adv|prep|pron|conj|num|art|int|aux|modal)\.", re.I)
EXAM_TAGS = ("zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre")
POS_MAP = {"n": "n", "v": "v", "a": "adj", "s": "adj", "r": "adv"}
TAG_TO_POS = {
    "n": "n", "v": "v", "vt": "v", "vi": "v", "a": "adj", "adj": "adj",
    "ad": "adv", "adv": "adv", "prep": "prep", "pron": "pron",
    "conj": "conj", "num": "num", "art": "art", "int": "int",
    "aux": "v", "modal": "v",
}
SUFFIXES = (
    "ational", "ations", "ation", "ments", "ment", "ness", "ities", "ity",
    "ings", "ing", "edly", "ed", "ly", "ers", "er", "est", "es", "s",
)
POS_FALLBACK = {
    "hello": "int", "bye": "int", "goodbye": "int",
    "grandpa": "n", "dvd": "n", "etc": "adv",
}


def to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def first_line(translation: str) -> str:
    text = (translation or "").replace("\\n", "\n")
    for raw in text.split("\n"):
        line = raw.strip()
        if line and not line.startswith("["):
            return line
    return ""


def clean_gloss(line: str) -> str:
    line = re.sub(r"^(?:interj|aux|modal|[a-zA-Z]{1,5})\.\s*", "", line, flags=re.I)
    line = re.split(r"[，,；;]", line)[0]
    line = re.sub(r"[（(].*?[）)]", "", line).strip(" ，,。.")
    return line[:12]


def parse_senses(translation: str) -> list[dict]:
    """Collect up to four gloss lines; each line may carry its own POS marker."""
    senses = []
    text = (translation or "").replace("\\n", "\n")
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("["):
            continue
        match = POS_INFER.match(line)
        pos = TAG_TO_POS.get(match.group(1).lower()) if match else None
        gloss = clean_gloss(line)
        if not gloss:
            continue
        senses.append({"pos": pos, "zh": gloss})
        if len(senses) >= 4:
            break
    return senses


def parse_pos(senses: list[dict], raw_pos: str) -> list[str]:
    result = []
    for sense in senses:
        mapped = sense.get("pos")
        if mapped and mapped not in result:
            result.append(mapped)
    for part in (raw_pos or "").split("/"):
        key = part.split(":")[0].strip()
        mapped = POS_MAP.get(key)
        if mapped and mapped not in result:
            result.append(mapped)
    return result or ["?"]


def parse_forms(exchange: str) -> list[str]:
    forms = []
    for part in (exchange or "").split("/"):
        if ":" not in part:
            continue
        kind, form = part.split(":", 1)
        if kind in ("p", "d", "i", "3", "r", "t", "s") and form and form not in forms:
            forms.append(form)
    return forms


def exam_list(tag: str) -> list[str]:
    present = set((tag or "").split())
    return [t for t in EXAM_TAGS if t in present]


def is_headword(word: str, gloss_line: str, exchange: str) -> bool:
    if PURE_INFLECTION.match(gloss_line):
        return False
    lemma = re.search(r"(?:^|/)0:([^/]+)", exchange or "")
    variant_type = re.search(r"(?:^|/)1:([^/]+)", exchange or "")
    if lemma and variant_type and "s" in variant_type.group(1):
        if word == lemma.group(1) + "s":
            return False
    return True


def load_candidates(path: str) -> tuple[dict, dict]:
    stats = collections.Counter()
    star_rows = collections.Counter()
    zk_invalid = collections.Counter()
    best: dict[str, dict] = {}

    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            stats["rows"] += 1
            word = (row.get("word") or "").strip()
            raw_star = to_int(row.get("collins"))
            if 1 <= raw_star <= 5:
                star_rows[raw_star] += 1
            exams = exam_list(row.get("tag") or "")

            if not WORD_RE.match(word) or (len(word) < 3 and "zk" not in exams):
                if "zk" in exams:
                    zk_invalid["non_single_word"] += 1
                stats["rejected_word_shape"] += 1
                continue

            line = first_line(row.get("translation") or "")
            if not line:
                stats["rejected_no_gloss"] += 1
                continue
            exchange = row.get("exchange") or ""
            if not is_headword(word, line, exchange):
                if "zk" in exams:
                    zk_invalid["inflected_variant"] += 1
                stats["rejected_inflected"] += 1
                continue

            stars = raw_star if 3 <= raw_star <= 5 else 0
            if stars == 0 and not exams:
                stats["rejected_unrated_non_exam"] += 1
                continue

            senses = parse_senses(row.get("translation") or "")
            if not senses:
                stats["rejected_no_gloss"] += 1
                continue
            pos = parse_pos(senses, row.get("pos") or "")
            if pos == ["?"] and word in POS_FALLBACK:
                pos = [POS_FALLBACK[word]]
            rec = {
                "lemma": word,
                "pos": pos,
                "stars": stars,
                "star_source": "collins" if stars else ("zhongkao" if "zk" in exams else "frequency"),
                "senses": senses,
                "exams": exams,
                "freq": {"bnc": to_int(row.get("bnc")), "frq": to_int(row.get("frq"))},
                "forms": parse_forms(exchange),
                "phonetic": (row.get("phonetic") or "").strip(),
            }
            prev = best.get(word)
            if prev is None:
                best[word] = rec
            else:
                stats["deduped_entries"] += 1
                if (rec["stars"], len(rec["senses"])) > (prev["stars"], len(prev["senses"])):
                    best[word] = rec
    return best, {"stats": stats, "star_rows": star_rows, "zk_invalid": zk_invalid}


def exam_tier(rec: dict) -> int:
    tier = {"zk": 0, "gk": 1, "cet4": 2, "cet6": 3, "ky": 3}
    return min((tier[e] for e in rec["exams"] if e in tier), default=4)


def freq_key(rec: dict) -> tuple[int, int]:
    return (rec["freq"]["bnc"] or 10**9, rec["freq"]["frq"] or 10**9)


def build_selection(candidates: dict) -> tuple[list[dict], dict]:
    """Keep only Collins 3-5 star headwords; no 中考-only or frequency top-ups."""
    words = [r for r in candidates.values() if r["stars"] >= 3]
    words.sort(key=lambda r: (exam_tier(r), -r["stars"], *freq_key(r), r["lemma"]))
    for index, rec in enumerate(words, start=1):
        rec["order"] = index
        rec["status"] = "assigned"
        rec["route"] = "zhongkao+full" if "zk" in rec["exams"] else "full"
        rec["set"] = "s3000"
        rec["passage"] = None

    diagnostics = {
        "final_total": len(words),
        "zk_total": sum(1 for r in words if "zk" in r["exams"]),
        "final_star_counts": dict(collections.Counter(r["stars"] for r in words)),
        "final_star_source": dict(collections.Counter(r["star_source"] for r in words)),
    }
    return words, diagnostics


def build_supplement(candidates: dict) -> tuple[list[dict], dict]:
    """Keep only 中考-tagged headwords without a Collins star (289)."""
    words = [r for r in candidates.values() if r["stars"] == 0 and "zk" in r["exams"]]
    words.sort(key=lambda r: (*freq_key(r), r["lemma"]))
    for index, rec in enumerate(words, start=1):
        rec["order"] = index
        rec["status"] = "assigned"
        rec["route"] = "zhongkao"
        rec["set"] = "zk-supplement"
        rec["passage"] = None
        rec["star_source"] = "zhongkao"

    diagnostics = {
        "supplement_total": len(words),
        "supplement_star_source": dict(collections.Counter(r["star_source"] for r in words)),
        "supplement_stars": dict(collections.Counter(r["stars"] for r in words)),
    }
    return words, diagnostics


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


def group_families(group: list[dict], families: dict[str, str]) -> collections.Counter:
    return collections.Counter(families.get(r["lemma"], r["lemma"]) for r in group)


def repair_collisions(groups: list[list[dict]], families: dict[str, str]) -> list[tuple]:
    """Swap words between passages until no two same-family words share a passage."""
    for gi, group in enumerate(groups):
        for _ in range(20):
            counts = group_families(group, families)
            dup = [fam for fam, n in counts.items() if n > 1]
            if not dup:
                break
            fam = dup[0]
            victim = next(
                r for r in reversed(group) if families.get(r["lemma"], r["lemma"]) == fam
            )
            swapped = False
            for gj, other in enumerate(groups):
                if gj == gi:
                    continue
                if "zk" in victim["exams"] and gj >= ZK_ROUTE_PASSAGES:
                    continue
                other_counts = group_families(other, families)
                for cand in other:
                    if "zk" in cand["exams"] and gi >= ZK_ROUTE_PASSAGES:
                        continue
                    if cand["pos"][0] != victim["pos"][0]:
                        continue
                    cand_fam = families.get(cand["lemma"], cand["lemma"])
                    if cand_fam == fam:
                        continue
                    if other_counts[fam] or counts[cand_fam]:
                        continue
                    group.remove(victim)
                    other.remove(cand)
                    group.append(cand)
                    other.append(victim)
                    swapped = True
                    break
                if swapped:
                    break
            if not swapped:
                break

    remaining = []
    for gi, group in enumerate(groups, start=1):
        counts = group_families(group, families)
        for fam, n in counts.items():
            if n > 1:
                members = [r["lemma"] for r in group if families.get(r["lemma"], r["lemma"]) == fam]
                remaining.append((gi, fam, members))
    return remaining


FUNCTION_CAP = 25
FUNCTION_LEMMAS = {
    "the", "a", "an", "be", "am", "is", "are", "was", "were", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must", "not", "no", "yes", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our", "their", "mine",
    "yours", "hers", "ours", "theirs", "myself", "yourself", "himself", "herself",
    "itself", "ourselves", "yourselves", "themselves", "who", "whom", "whose",
    "which", "what", "when", "where", "why", "how", "some", "any", "every",
    "each", "all", "both", "either", "neither", "many", "much", "more", "most",
    "few", "little", "other", "another", "such", "than", "as", "so", "too",
    "very", "just", "only", "even", "still", "also", "never", "always",
    "often", "sometimes", "usually", "already", "yet", "again", "here", "there",
    "now", "then", "up", "down", "in", "out", "on", "off", "over", "under",
    "about", "around", "away", "back", "together", "apart", "of", "to", "for",
    "with", "by", "from", "at", "into", "onto", "upon", "after", "before",
    "during", "without", "within", "through", "between", "among", "against",
    "and", "but", "or", "if", "because", "while", "although", "though", "since",
    "until", "unless", "whether", "per",
}


def is_function_word(rec: dict) -> bool:
    return rec["lemma"] in FUNCTION_LEMMAS or rec["pos"][0] in {"pron", "prep", "conj", "art"}


def assign_groups(words: list[dict]) -> tuple[list[list[dict]], dict]:
    n_groups = PASSAGES
    sizes = PASSAGE_SIZES[:n_groups]
    if sum(sizes) != len(words):
        raise SystemExit(f"分篇容量 {sum(sizes)} ≠ 词数 {len(words)}")
    zk = [w for w in words if "zk" in w["exams"]]
    rest = [w for w in words if "zk" not in w["exams"]]
    route_capacity = sum(sizes[:ZK_ROUTE_PASSAGES])
    if len(zk) > route_capacity:
        raise SystemExit(f"中考词 {len(zk)} 超出前 {ZK_ROUTE_PASSAGES} 篇容量 {route_capacity}")

    groups: list[list[dict]] = [[] for _ in range(n_groups)]
    func_count = [0] * n_groups
    # 可用词性目标（可重叠，不要求互斥）：每篇可作名词 ≥30、动词 ≥20、形/副 ≥10
    POS_TARGETS = {"n": 30, "v": 20, "aa": 10}
    pos_counts = [{"n": 0, "v": 0, "aa": 0} for _ in range(n_groups)]

    def cap_keys(rec: dict) -> set[str]:
        keys = set()
        if "n" in rec["pos"]:
            keys.add("n")
        if "v" in rec["pos"]:
            keys.add("v")
        if "adj" in rec["pos"] or "adv" in rec["pos"]:
            keys.add("aa")
        return keys

    def score(gi: int, rec: dict) -> tuple:
        keys = cap_keys(rec)
        deficit = sum(max(0, POS_TARGETS[k] - pos_counts[gi][k]) for k in keys)
        return (deficit, sizes[gi] - len(groups[gi]))

    def put(rec: dict, limit: int) -> bool:
        best = None
        for gi in range(limit):
            if len(groups[gi]) >= sizes[gi]:
                continue
            func = is_function_word(rec)
            if func and func_count[gi] >= FUNCTION_CAP:
                continue
            candidate = (score(gi, rec), gi)
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best is None:
            return False
        gi = best[1]
        groups[gi].append(rec)
        for key in cap_keys(rec):
            pos_counts[gi][key] += 1
        if is_function_word(rec):
            func_count[gi] += 1
        return True

    for rec in zk:
        if not put(rec, ZK_ROUTE_PASSAGES):
            raise SystemExit(f"中考词无法在前 {ZK_ROUTE_PASSAGES} 篇内排布")
    for rec in rest:
        if not put(rec, n_groups):
            raise SystemExit("分组溢出")

    families = family_keys({w["lemma"] for w in words})
    collisions = repair_collisions(groups, families)

    for gi, group in enumerate(groups, start=1):
        for rec in group:
            rec["passage"] = f"s3000-p{gi:02d}"

    pos_caps = []
    for group in groups:
        pos_caps.append({p: sum(p in w["pos"] for w in group) for p in ("n", "v", "adj", "adv")})
    return groups, {
        "groups": n_groups,
        "sizes": [len(g) for g in groups],
        "route_capacity": route_capacity,
        "zk_in_route": sum(len(g) for g in groups[:ZK_ROUTE_PASSAGES]),
        "family_collisions": collisions,
        "pos_capability_min": {p: min(x[p] for x in pos_caps) for p in ("n", "v", "adj", "adv")},
        "pos_capability_avg": {
            p: round(sum(x[p] for x in pos_caps) / n_groups, 1) for p in ("n", "v", "adj", "adv")
        },
    }


def assign_supplement(words: list[dict]) -> tuple[list[list[dict]], dict]:
    """Split the 289 中考补漏词 into 5 balanced passages (58/58/58/58/57)."""
    n_groups = SUPP_PASSAGES
    sizes = SUPP_SIZES[:n_groups]
    if sum(sizes) != len(words):
        raise SystemExit(f"补漏分篇容量 {sum(sizes)} ≠ 词数 {len(words)}")

    groups: list[list[dict]] = [[] for _ in range(n_groups)]
    func_count = [0] * n_groups
    POS_TARGETS = {"n": 30, "v": 20, "aa": 10}
    pos_counts = [{"n": 0, "v": 0, "aa": 0} for _ in range(n_groups)]

    def cap_keys(rec: dict) -> set[str]:
        keys = set()
        if "n" in rec["pos"]:
            keys.add("n")
        if "v" in rec["pos"]:
            keys.add("v")
        if "adj" in rec["pos"] or "adv" in rec["pos"]:
            keys.add("aa")
        return keys

    def score(gi: int, rec: dict) -> tuple:
        deficit = sum(max(0, POS_TARGETS[k] - pos_counts[gi][k]) for k in cap_keys(rec))
        return (deficit, sizes[gi] - len(groups[gi]))

    for rec in words:
        best = None
        for gi in range(n_groups):
            if len(groups[gi]) >= sizes[gi]:
                continue
            if is_function_word(rec) and func_count[gi] >= FUNCTION_CAP:
                continue
            candidate = (score(gi, rec), gi)
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best is None:
            raise SystemExit(f"补漏词 {rec['lemma']} 无法排布")
        gi = best[1]
        groups[gi].append(rec)
        for key in cap_keys(rec):
            pos_counts[gi][key] += 1
        if is_function_word(rec):
            func_count[gi] += 1

    families = family_keys({w["lemma"] for w in words})
    collisions = repair_collisions(groups, families)

    for gi, group in enumerate(groups, start=1):
        for rec in group:
            rec["passage"] = f"s3000-b{gi:02d}"

    pos_caps = [
        {p: sum(p in w["pos"] for w in group) for p in ("n", "v", "adj", "adv")}
        for group in groups
    ]
    return groups, {
        "groups": n_groups,
        "sizes": [len(g) for g in groups],
        "family_collisions": collisions,
        "pos_capability_min": {p: min(x[p] for x in pos_caps) for p in ("n", "v", "adj", "adv")},
        "pos_capability_avg": {
            p: round(sum(x[p] for x in pos_caps) / n_groups, 1) for p in ("n", "v", "adj", "adv")
        },
    }


def main() -> None:
    if not os.path.exists(SRC):
        sys.exit(f"缺少源数据：{SRC}")
    candidates, raw = load_candidates(SRC)
    words, selection = build_selection(candidates)
    if len(words) != TOTAL_TARGET:
        raise SystemExit(f"词表 {len(words)} 词，与既定口径 {TOTAL_TARGET} 不符")
    groups, assignment = assign_groups(words)

    supp, supp_selection = build_supplement(candidates)
    if len(supp) != SUPP_TOTAL:
        raise SystemExit(f"补漏词 {len(supp)} 词，与既定口径 {SUPP_TOTAL} 不符")
    supp_groups, supp_assignment = assign_supplement(supp)

    os.makedirs(DATA, exist_ok=True)
    meta = {
        "source": "ECDICT (skywind3000/ECDICT)",
        "source_license": "MIT",
        "generated_at": "2026-11-21",
        "total": len(words),
        "zhongkao": selection["zk_total"],
        "per_passage": "59–60",
        "passage_sizes": PASSAGE_SIZES,
        "passages": len(groups),
        "route_passages": ZK_ROUTE_PASSAGES,
        "route_capacity": assignment["route_capacity"],
        "star_counts": selection["final_star_counts"],
        "star_source": selection["final_star_source"],
    }
    with open(os.path.join(DATA, "lexicon.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "words": words}, fh, ensure_ascii=False, indent=1)

    supp_meta = {
        "source": "ECDICT (skywind3000/ECDICT)",
        "source_license": "MIT",
        "generated_at": "2026-11-21",
        "set": "zk-supplement",
        "total": len(supp),
        "stars": 0,
        "star_source": "zhongkao",
        "per_passage": "57–58",
        "passage_sizes": SUPP_SIZES,
        "passages": len(supp_groups),
        "route": "zhongkao",
        "route_positions": "23–27",
        "notes": "中考无星级补漏词，不参与主线星级统计",
    }
    with open(os.path.join(DATA, "supplement.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": supp_meta, "words": supp}, fh, ensure_ascii=False, indent=1)

    main_zk = [dict(w) for w in words if "zk" in w["exams"]]
    for rec in main_zk:
        rec["route_index"] = int(rec["passage"].split("p")[-1])
    supp_zk = [dict(w) for w in supp]
    for rec in supp_zk:
        rec["route_index"] = ZK_ROUTE_PASSAGES + int(rec["passage"].split("b")[-1])
    zk_out = main_zk + supp_zk
    zk_meta = {
        "source": "ECDICT (skywind3000/ECDICT)",
        "source_license": "MIT",
        "generated_at": "2026-11-21",
        "total": len(zk_out),
        "main_zhongkao": len(main_zk),
        "supplement": len(supp_zk),
        "star_counts": dict(collections.Counter(w["stars"] for w in main_zk)),
        "star_source": dict(collections.Counter(w["star_source"] for w in zk_out)),
        "route_passages": ZK_ROUTE_PASSAGES + SUPP_PASSAGES,
        "main_route_passages": ZK_ROUTE_PASSAGES,
        "supplement_passages": SUPP_PASSAGES,
        "main_route_capacity": assignment["route_capacity"],
    }
    with open(os.path.join(DATA, "zhongkao.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {"meta": zk_meta, "words": zk_out},
            fh, ensure_ascii=False, indent=1,
        )

    with open(os.path.join(DATA, "assignment.tsv"), "w", encoding="utf-8") as fh:
        fh.write("lemma\torder\tpassage\tocc_in_passage\troute\tstatus\tstars\tstar_source\n")
        for rec in words:
            route = "zhongkao" if "zk" in rec["exams"] else "full"
            fh.write(
                f"{rec['lemma']}\t{rec['order']}\t{rec['passage']}\t\t{route}\t"
                f"{rec['status']}\t{rec['stars']}\t{rec['star_source']}\n"
            )

    with open(os.path.join(DATA, "assignment-supplement.tsv"), "w", encoding="utf-8") as fh:
        fh.write("lemma\torder\tpassage\tocc_in_passage\troute\tstatus\tstars\tstar_source\n")
        for rec in supp:
            fh.write(
                f"{rec['lemma']}\t{rec['order']}\t{rec['passage']}\t\t{rec['route']}\t"
                f"{rec['status']}\t{rec['stars']}\t{rec['star_source']}\n"
            )

    diagnostics = {
        "raw": {
            "rows": raw["stats"]["rows"],
            "star_rows_all_entries": {str(k): v for k, v in sorted(raw["star_rows"].items())},
            "rejected_word_shape": raw["stats"]["rejected_word_shape"],
            "rejected_no_gloss": raw["stats"]["rejected_no_gloss"],
            "rejected_inflected": raw["stats"]["rejected_inflected"],
            "rejected_unrated_non_exam": raw["stats"]["rejected_unrated_non_exam"],
            "deduped_entries": raw["stats"]["deduped_entries"],
            "zk_invalid": dict(raw["zk_invalid"]),
        },
        "base_headwords_by_star": dict(sorted(collections.Counter(
            r["stars"] for r in candidates.values() if r["stars"]
        ).items())),
        "selection": selection,
        "assignment": assignment,
        "supplement": {**supp_selection, **supp_assignment},
        "combined": {
            "main_total": len(words),
            "supplement_total": len(supp),
            "total": len(words) + len(supp),
            "passages": len(groups) + len(supp_groups),
            "zhongkao": len(zk_out),
        },
    }
    with open(os.path.join(DATA, "lexicon-diagnostics.json"), "w", encoding="utf-8") as fh:
        json.dump(diagnostics, fh, ensure_ascii=False, indent=1)

    summary = {
        "main": {**meta, **selection, **{k: v for k, v in assignment.items()
                                         if k != "family_collisions"},
                 "family_collisions": len(assignment["family_collisions"])},
        "supplement": {**supp_meta, **supp_selection,
                       **{k: v for k, v in supp_assignment.items()
                          if k != "family_collisions"},
                       "family_collisions": len(supp_assignment["family_collisions"])},
        "combined": diagnostics["combined"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
