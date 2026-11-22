#!/usr/bin/env python3
"""全局成稿核对（只读 data/，报告写到 work/）。

用法：
    python3 work/audit_all.py            # 核对 data/content/ 下全部篇目
    python3 work/audit_all.py --no-write # 只打印，不写报告文件

核对项：
  1. 文件与编号：p01–p50、b01–b05 齐全，无多余 json，id 与文件名一致；
  2. 结构：JSON 可解析；必填字段齐全；paragraphs 为嵌套数组且逐句 en/zh；
     words 卡字段齐全；quiz 8 题；recite b2/b3/b4 字段完整；metrics 齐全；
  3. 账簿对账：词卡集合/顺序与 assignment 一致；正文覆盖全部目标词；列出正文中
     出现的“别篇目标词”（仅提示，非珠玑——非目标词本就允许常用词）；
  4. 全局覆盖：lexicon 2953 词、supplement 289 词是否都在其所属篇正文出现；
  5. 分布：篇长、句数、密度、每句词数、每句目标词数是否在规格内；
  6. 标题唯一（英/中）、题材重复、开头句雷同；
  7. 素材一致：词卡搭配取自正文、b2/b3 可回拼、b4 译文与正文句子对应、
     keywords 出现在正文、quiz 选项与答案合法；
  8. metrics 与实测是否一致。

只读 data/；唯一写入是 work/audit-report.md 与 work/audit-report.json。
"""

import csv
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTENT = DATA / "content"
WORK = ROOT / "work"

TOKEN_MAIN = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
TOKEN_SUP = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
TOKEN = TOKEN_SUP
FORM_FIX = {
    "tired": {"tire", "tires", "tired", "tiring"},
    "lie": {"lie", "lies", "lay", "lying", "lain"},
    "swing": {"swing", "swings", "swung", "swinging"},
}
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "it", "its", "my", "our", "her", "his", "their",
    "she", "he", "we", "they", "this", "that", "these", "those", "but", "so",
    "as", "by", "from", "not", "no", "will", "cannot", "can", "must", "be",
    "us", "me", "him", "them", "i", "you", "has", "have", "had", "does", "do",
    "did", "may", "there", "then", "when", "while", "into", "out", "up", "down",
    "one", "two", "all", "every", "some", "any", "very", "still", "just", "also",
}


def normalize(text):
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def forms_for(lemma, entry):
    forms = {lemma, lemma + "s", lemma + "es", lemma + "ed", lemma + "d", lemma + "ing",
             lemma + "er", lemma + "est", lemma + "ies", lemma + "'s"}
    forms |= {str(form).lower() for form in entry.get("forms", [])}
    forms |= FORM_FIX.get(lemma, set())
    return forms


def read_tsv(path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main(write=True):
    issues = []          # (level, passage, check, detail)
    notes = []

    def add(level, passage, check, detail):
        issues.append({"level": level, "passage": passage, "check": check, "detail": detail})

    lexicon = {w["lemma"]: w for w in json.loads((DATA / "lexicon.json").read_text(encoding="utf-8"))["words"]}
    supplement = {w["lemma"]: w for w in json.loads((DATA / "supplement.json").read_text(encoding="utf-8"))["words"]}
    main_rows = read_tsv(DATA / "assignment.tsv")
    sup_rows = read_tsv(DATA / "assignment-supplement.tsv")

    main_assign = defaultdict(list)
    for row in main_rows:
        main_assign[row["passage"]].append(row["lemma"])
    sup_assign = defaultdict(list)
    for row in sup_rows:
        sup_assign[row["passage"]].append(row["lemma"])

    # ---------- 1. 文件与编号 ----------
    files = sorted(CONTENT.glob("*.json"))
    stems = {path.stem for path in files}
    expected_main = {f"p{i:02d}" for i in range(1, 51)}
    expected_sup = {f"b{i:02d}" for i in range(1, 6)}
    expected = expected_main | expected_sup
    missing = sorted(expected - stems)
    extra = sorted(stems - expected)
    if missing:
        add("ERROR", "-", "编号完整性", f"缺少文件：{', '.join(missing)}")
    if extra:
        add("ERROR", "-", "编号完整性", f"多余文件：{', '.join(extra)}")

    # 反向索引：token -> 可能的 lemma 集合（只建一次）
    reverse = defaultdict(set)
    for lemma, entry in lexicon.items():
        for form in forms_for(lemma, entry):
            reverse[form].add(lemma)
    for lemma, entry in supplement.items():
        for form in forms_for(lemma, entry):
            reverse[form].add(lemma)

    contents = {}
    for path in files:
        pid = path.stem
        try:
            contents[pid] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            add("ERROR", pid, "JSON 解析", f"{path.name}: {exc}")

    # ---------- 2. 结构 ----------
    required = ["id", "title", "titleZh", "topic", "paragraphs", "words", "quiz", "recite", "metrics"]
    for pid in sorted(contents):
        data = contents[pid]
        for key in required:
            if key not in data or data[key] in (None, "", [], {}):
                add("ERROR", pid, "必填字段", f"缺少或为空：{key}")
        if data.get("id") != pid:
            add("ERROR", pid, "字段一致性", f"id={data.get('id')!r} 与文件名不一致")

        paragraphs = data.get("paragraphs")
        if not isinstance(paragraphs, list) or not all(isinstance(p, list) and p for p in paragraphs):
            add("ERROR", pid, "段落结构", "paragraphs 必须是“数组的数组”且每段非空")
            paragraphs = []
        flat = []
        for index, para in enumerate(paragraphs, 1):
            for seq, sentence in enumerate(para, 1):
                if not isinstance(sentence, dict):
                    add("ERROR", pid, "段落结构", f"第 {index} 段第 {seq} 句不是对象（加载器会丢弃 zh）")
                    continue
                en = str(sentence.get("en", "")).strip()
                zh = str(sentence.get("zh", "")).strip()
                if not en:
                    add("ERROR", pid, "段落结构", f"第 {index} 段第 {seq} 句缺 en")
                if not zh:
                    add("WARN", pid, "段落结构", f"第 {index} 段第 {seq} 句缺 zh")
                flat.append({"en": en, "zh": zh, "para": index})

        words = data.get("words") if isinstance(data.get("words"), list) else []
        for card in words:
            if not isinstance(card, dict):
                add("ERROR", pid, "词卡结构", "words 中存在非对象项")
                continue
            for key in ("lemma", "pos", "zh", "collocation"):
                if not str(card.get(key, "")).strip():
                    add("ERROR", pid, "词卡结构", f"{card.get('lemma', '?')} 缺 {key}")

        quiz = data.get("quiz") if isinstance(data.get("quiz"), list) else []
        if len(quiz) != 8:
            add("ERROR", pid, "检测题", f"题数 {len(quiz)} ≠ 8")
        for q in quiz:
            if not isinstance(q, dict):
                add("ERROR", pid, "检测题", "存在非对象题目")
                continue
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2:
                add("ERROR", pid, "检测题", f"{q.get('id')} 选项非法")
                continue
            if len(set(map(str, options))) != len(options):
                add("ERROR", pid, "检测题", f"{q.get('id')} 选项重复")
            answer = q.get("answer")
            if not isinstance(answer, int) or not 0 <= answer < len(options):
                add("ERROR", pid, "检测题", f"{q.get('id')} answer 索引非法：{answer!r}")
            for key in ("id", "type", "prompt"):
                if not str(q.get(key, "")).strip():
                    add("WARN", pid, "检测题", f"{q.get('id')} 缺 {key}")

        recite = data.get("recite") if isinstance(data.get("recite"), dict) else {}
        for block, low in (("b2", 8), ("b3", 6), ("b4", 5)):
            items = recite.get(block, [])
            if not isinstance(items, list) or len(items) < low:
                add("ERROR", pid, "背诵素材", f"{block} 数量 {len(items) if isinstance(items, list) else '非法'} < {low}")
        for block in ("b2", "b3"):
            for item in recite.get(block, []) or []:
                if not isinstance(item, dict):
                    add("ERROR", pid, "背诵素材", f"{block} 存在非对象项")
                    continue
                for key in ("before", "hint", "after", "answer"):
                    if key not in item:
                        add("ERROR", pid, "背诵素材", f"{block} 缺 {key}（答案 {item.get('answer')!r}）")
        for item in recite.get("b4", []) or []:
            if not isinstance(item, dict) or not str(item.get("zh", "")).strip():
                add("ERROR", pid, "背诵素材", "b4 缺中文")
            elif not isinstance(item.get("keywords"), list) or not item["keywords"]:
                add("WARN", pid, "背诵素材", f"b4「{item['zh'][:12]}…」缺 keywords")

        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        for key in ("words", "sentences", "newDensity", "targetTokenDensity", "patterns"):
            if key not in metrics:
                add("ERROR", pid, "metrics", f"缺 {key}")

    # ---------- 逐篇统计 ----------
    stats = {}
    covered = {}      # lemma -> [passage]
    for pid in sorted(contents):
        data = contents[pid]
        is_sup = pid.startswith("b")
        assign_key = f"s3000-{pid}"
        targets = sup_assign.get(assign_key, []) if is_sup else main_assign.get(assign_key, [])
        entry_book = supplement if is_sup else lexicon
        target_forms = {lemma: forms_for(lemma, entry_book.get(lemma, {})) for lemma in targets}

        paragraphs = data.get("paragraphs") if isinstance(data.get("paragraphs"), list) else []
        sentences = []
        for para in paragraphs:
            if not isinstance(para, list):
                continue
            for sentence in para:
                if isinstance(sentence, dict) and str(sentence.get("en", "")).strip():
                    sentences.append(sentence)
        text = normalize(" ".join(str(s.get("en", "")) for s in sentences))
        token_re = TOKEN_SUP if is_sup else TOKEN_MAIN
        tokens = [w.lower() for w in token_re.findall(text)]
        text_words = set(tokens)

        counts = Counter()
        per_sentence = []
        for sentence in sentences:
            words = [w.lower() for w in token_re.findall(str(sentence.get("en", "")))]
            hits = []
            for word in words:
                if word.endswith("'s"):
                    word = word[:-2]
                hit = next((lemma for lemma in targets if word in target_forms[lemma]), None)
                if hit:
                    counts[hit] += 1
                    hits.append(hit)
            per_sentence.append({"len": len(words), "hits": len(hits)})

        total = sum(per_sentence_entry["len"] for per_sentence_entry in per_sentence)
        hits_total = sum(counts.values())
        missing_targets = [lemma for lemma in targets if counts[lemma] == 0]
        density = hits_total / total if total else 0.0
        unique_density = len(targets) / total if total else 0.0

        stats[pid] = {
            "track": "supplement" if is_sup else "main",
            "title": data.get("title", ""),
            "titleZh": data.get("titleZh", ""),
            "topic": data.get("topic", ""),
            "words": total,
            "sentences": len(sentences),
            "hits": hits_total,
            "density": round(density, 4),
            "uniqueDensity": round(unique_density, 4),
            "targets": len(targets),
            "missingTargets": missing_targets,
            "perSentence": per_sentence,
            "cards": len(data.get("words", []) or []),
            "text": text,
            "textWords": text_words,
        }
        for lemma, count in counts.items():
            if count:
                covered.setdefault(lemma, []).append(pid)

        # ---------- 3. 账簿对账 ----------
        if not targets:
            add("ERROR", pid, "分配账簿", "账簿中找不到该篇目标词")
        cards = [card.get("lemma") for card in data.get("words", []) or [] if isinstance(card, dict)]
        if cards != targets:
            only_cards = [lemma for lemma in cards if lemma not in set(targets)]
            only_book = [lemma for lemma in targets if lemma not in set(cards)]
            detail = f"词卡 {len(cards)} 个 / 账簿 {len(targets)} 个"
            if only_cards:
                detail += f"；多出：{only_cards[:10]}"
            if only_book:
                detail += f"；缺少：{only_book[:10]}"
            if not only_cards and not only_book:
                detail += "；顺序不一致"
            add("ERROR", pid, "词卡与账簿", detail)

        if missing_targets:
            add("ERROR", pid, "正文覆盖", f"未出现：{missing_targets}")

        # 别篇目标词泄漏（信息级）
        own = set(targets)
        others = set()
        for word in tokens:
            if word.endswith("'s"):
                word = word[:-2]
            for lemma in reverse.get(word, ()):
                if lemma not in own:
                    others.add(lemma)
        stats[pid]["otherTargets"] = sorted(others)

        # ---------- 5. 分布 ----------
        low_words, high_words = 280, (315 if is_sup else 320)
        if not low_words <= total <= high_words:
            add("ERROR", pid, "篇长", f"{total} 不在 {low_words}–{high_words}")
        if is_sup:
            if not 29 <= len(sentences) <= 32:
                add("ERROR", pid, "句数", f"{len(sentences)} 不在 29–32")
        elif not 20 <= len(sentences) <= 40:
            add("ERROR", pid, "句数", f"{len(sentences)} 不在 20–40")
        if not 0.18 <= density <= 0.22:
            add("ERROR", pid, "目标词密度", f"{density:.3f} 不在 0.18–0.22")

        len_low, len_high = (8, 11) if is_sup else (8, 14)
        bad_len = [i + 1 for i, row in enumerate(per_sentence) if not len_low <= row["len"] <= len_high]
        if bad_len:
            add("WARN", pid, "句长", f"第 {bad_len} 句不在 {len_low}–{len_high} 词")
        bad_hits = [i + 1 for i, row in enumerate(per_sentence) if not 2 <= row["hits"] <= 4]
        if bad_hits:
            add("ERROR", pid, "每句目标词", f"第 {bad_hits} 句不在 2–4 个")

        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        metrics_ok = (
            metrics.get("words") == total
            and metrics.get("sentences") == len(sentences)
            and abs(metrics.get("targetTokenDensity", 0) - density) < 0.002
            and abs(metrics.get("newDensity", 0) - unique_density) < 0.002
        )
        if not metrics_ok:
            add("WARN", pid, "metrics", f"记录 {metrics.get('words')}/{metrics.get('sentences')} "
                                        f"{metrics.get('targetTokenDensity')}/{metrics.get('newDensity')}，"
                                        f"实测 {total}/{len(sentences)} {density:.3f}/{unique_density:.3f}")

        # ---------- 7. 素材一致 ----------
        recite = data.get("recite") if isinstance(data.get("recite"), dict) else {}
        for card in data.get("words", []) or []:
            if not isinstance(card, dict):
                continue
            for phrase in str(card.get("collocation", "")).split("/"):
                phrase = phrase.strip()
                if phrase and normalize(phrase) not in text:
                    add("ERROR", pid, "词卡搭配", f"{card.get('lemma')}：{phrase!r} 不在正文")
                    break

        for block in ("b2", "b3"):
            for item in recite.get(block, []) or []:
                if not isinstance(item, dict):
                    continue
                answer = str(item.get("answer", ""))
                if len(token_re.findall(answer)) != 1:
                    add("ERROR", pid, "挖空", f"{block} 答案不是单词：{answer!r}")
                    continue
                if answer.lower() not in text_words:
                    add("ERROR", pid, "挖空", f"{block} 答案不在正文：{answer!r}")
                rebuild = normalize(str(item.get("before", "")) + answer + str(item.get("after", "")))
                if rebuild not in text:
                    add("ERROR", pid, "挖空回拼", f"{block} 无法回拼：{answer!r}")
                hint = str(item.get("hint", "")).lower()
                if hint and not answer.lower().startswith(hint):
                    add("WARN", pid, "挖空提示", f"{block} hint={hint!r} 不是 {answer!r} 的前缀")

        zh_list = [normalize(s.get("zh", "")) for s in sentences if s.get("zh")]
        for item in recite.get("b4", []) or []:
            if not isinstance(item, dict):
                continue
            target_zh = normalize(item.get("zh", ""))
            best = max((difflib.SequenceMatcher(None, target_zh, zh).ratio() for zh in zh_list), default=0.0)
            if best < 0.6:
                add("INFO", pid, "回译", f"改写/合并句（最高相似度 {best:.2f}）：{str(item.get('zh', ''))[:24]}…")
            for keyword in item.get("keywords", []) or []:
                key = str(keyword).lower()
                if " " in key or "-" in key:
                    found = normalize(keyword) in text
                else:
                    keyword_forms = forms_for(key, entry_book.get(key, {}))
                    found = key in text_words or any(form in text_words for form in keyword_forms)
                if not found:
                    add("WARN", pid, "回译关键词", f"{keyword!r} 不在正文")

    # ---------- 4. 全局覆盖 ----------
    lexicon_covered = 0
    lexicon_missing = defaultdict(list)
    for lemma, entry in lexicon.items():
        passage = entry.get("passage", "")
        pid = passage.replace("s3000-", "") if passage.startswith("s3000-") else passage
        if pid not in contents:
            lexicon_missing[pid or "?"].append(lemma)
            continue
        if lemma not in covered.get(lemma, []):
            if lemma not in stats[pid]["textWords"] and not any(
                form in stats[pid]["textWords"] for form in forms_for(lemma, entry)
            ):
                lexicon_missing[pid].append(lemma)
                continue
        lexicon_covered += 1
    if lexicon_missing:
        for pid, lemmas in sorted(lexicon_missing.items()):
            add("ERROR", pid, "lexicon 覆盖", f"{len(lemmas)} 词未出现：{lemmas[:15]}")

    supplement_covered = 0
    supplement_missing = defaultdict(list)
    for lemma, entry in supplement.items():
        passage = entry.get("passage", "")
        pid = passage.replace("s3000-", "") if passage.startswith("s3000-") else passage
        if pid not in contents:
            supplement_missing[pid or "?"].append(lemma)
            continue
        if not any(form in stats[pid]["textWords"] for form in forms_for(lemma, entry)):
            supplement_missing[pid].append(lemma)
            continue
        supplement_covered += 1
    if supplement_missing:
        for pid, lemmas in sorted(supplement_missing.items()):
            add("ERROR", pid, "supplement 覆盖", f"{len(lemmas)} 词未出现：{lemmas[:15]}")

    assign_missing = [row["lemma"] for row in main_rows if row["lemma"] not in lexicon]
    if assign_missing:
        add("ERROR", "-", "账簿与 lexicon", f"账簿词不在 lexicon：{assign_missing[:15]}")
    sup_assign_missing = [row["lemma"] for row in sup_rows if row["lemma"] not in supplement]
    if sup_assign_missing:
        add("ERROR", "-", "账簿与 supplement", f"补漏账簿词不在 supplement：{sup_assign_missing[:15]}")

    # ---------- 6. 标题与题材 ----------
    titles_en = defaultdict(list)
    titles_zh = defaultdict(list)
    topics = defaultdict(list)
    for pid, data in contents.items():
        if data.get("title"):
            titles_en[normalize(data["title"])].append(pid)
        if data.get("titleZh"):
            titles_zh[normalize(data["titleZh"])].append(pid)
        if data.get("topic"):
            topics[normalize(data["topic"])].append(pid)
    for title, pids in titles_en.items():
        if len(pids) > 1:
            add("ERROR", ",".join(pids), "英文标题重复", title)
    for title, pids in titles_zh.items():
        if len(pids) > 1:
            add("ERROR", ",".join(pids), "中文标题重复", title)
    for topic, pids in topics.items():
        if len(pids) > 1:
            titles = [f"{pid}《{contents[pid].get('title', '')}》" for pid in pids]
            add("WARN", ",".join(pids), "题材标签重复", f"{topic}：{'、'.join(titles)}")

    openers = []
    for pid, data in contents.items():
        paragraphs = data.get("paragraphs") if isinstance(data.get("paragraphs"), list) else []
        first = ""
        for para in paragraphs:
            if isinstance(para, list) and para and isinstance(para[0], dict):
                first = str(para[0].get("en", ""))
                break
        if first:
            openers.append((pid, first))
    for i in range(len(openers)):
        for j in range(i + 1, len(openers)):
            pid_a, first_a = openers[i]
            pid_b, first_b = openers[j]
            parts_a = [w for w in TOKEN.findall(normalize(first_a)) if w not in STOPWORDS]
            parts_b = [w for w in TOKEN.findall(normalize(first_b)) if w not in STOPWORDS]
            if not parts_a or not parts_b:
                continue
            overlap = len(set(parts_a) & set(parts_b)) / len(set(parts_a) | set(parts_b))
            same_prefix = " ".join(normalize(first_a).split()[:5]) == " ".join(normalize(first_b).split()[:5])
            if overlap >= 0.6 or same_prefix:
                add("WARN", f"{pid_a},{pid_b}", "开头句雷同", f"重合度 {overlap:.2f}：{first_a[:50]}…")

    # ---------- 汇总 ----------
    errors = [item for item in issues if item["level"] == "ERROR"]
    warns = [item for item in issues if item["level"] == "WARN"]
    infos = [item for item in issues if item["level"] == "INFO"]
    passed = {
        "编号完整性": not missing and not extra,
        "JSON 解析": not any(i["check"] == "JSON 解析" for i in errors),
        "结构完整性": not any(i["check"] in {"必填字段", "段落结构", "词卡结构", "检测题", "背诵素材", "metrics"} for i in errors),
        "词卡与账簿一致": not any(i["check"] == "词卡与账簿" for i in errors),
        "正文覆盖目标词": not any(i["check"] == "正文覆盖" for i in errors),
        "全局词表覆盖": not any(i["check"] in {"lexicon 覆盖", "supplement 覆盖", "账簿与 lexicon", "账簿与 supplement"} for i in errors),
        "分布规格": not any(i["check"] in {"篇长", "句数", "目标词密度", "每句目标词"} for i in errors),
        "标题唯一": not any(i["check"] in {"英文标题重复", "中文标题重复"} for i in errors),
        "素材与正文一致": not any(i["check"] in {"词卡搭配", "挖空", "挖空回拼"} for i in errors),
    }

    total_words = sum(item["words"] for item in stats.values())
    total_sentences = sum(item["sentences"] for item in stats.values())

    # ---------- 输出 ----------
    lines = []
    lines.append("# 成稿全局核对报告")
    lines.append("")
    lines.append(f"- 篇目：{len(contents)} 个（主线 {sum(1 for p in stats if p.startswith('p'))}、补漏 {sum(1 for p in stats if p.startswith('b'))}）")
    lines.append(f"- 正文合计：{total_words} 词 / {total_sentences} 句")
    lines.append(f"- 错误：{len(errors)} 项；提示：{len(warns)} 项；备注：{len(infos)} 项")
    lines.append(f"- 词表覆盖：lexicon {lexicon_covered}/{len(lexicon)}，"
                 f"supplement {supplement_covered}/{len(supplement)}")
    main_stats = [v for k, v in stats.items() if k.startswith("p")]
    sup_stats = [v for k, v in stats.items() if k.startswith("b")]
    if main_stats:
        lines.append(f"- 主线词数 {min(v['words'] for v in main_stats)}–{max(v['words'] for v in main_stats)}，"
                     f"句数 {min(v['sentences'] for v in main_stats)}–{max(v['sentences'] for v in main_stats)}，"
                     f"密度 {min(v['density'] for v in main_stats):.3f}–{max(v['density'] for v in main_stats):.3f}")
    if sup_stats:
        lines.append(f"- 补漏词数 {min(v['words'] for v in sup_stats)}–{max(v['words'] for v in sup_stats)}，"
                     f"句数 {min(v['sentences'] for v in sup_stats)}–{max(v['sentences'] for v in sup_stats)}，"
                     f"密度 {min(v['density'] for v in sup_stats):.3f}–{max(v['density'] for v in sup_stats):.3f}")
    lines.append(f"- 标题：英文 {len(titles_en)} 个唯一值、中文 {len(titles_zh)} 个唯一值；"
                 f"开头句共比对 {len(openers) * (len(openers) - 1) // 2} 对")
    lines.append("")

    lines.append("## 结论")
    lines.append("")
    for name, ok in passed.items():
        lines.append(f"- {'通过' if ok else '**未通过**'}：{name}")
    lines.append("")

    lines.append("## 分篇统计")
    lines.append("")
    lines.append("| 篇 | 标题 | 词数 | 句数 | 目标词 | 词次 | 密度 | 缺词 | 别篇词 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for pid in sorted(stats):
        info = stats[pid]
        dev = len(info["missingTargets"])
        lines.append(
            f"| {pid} | {info['title']} | {info['words']} | {info['sentences']} | "
            f"{info['targets']} | {info['hits']} | {info['density']:.3f} | {dev} | "
            f"{len(info['otherTargets'])} |"
        )
    lines.append("")

    for level, title in (("ERROR", "异常项"), ("WARN", "提示项"), ("INFO", "备注项")):
        subset = [item for item in issues if item["level"] == level]
        lines.append(f"## {title}（{len(subset)}）")
        lines.append("")
        if not subset:
            lines.append("- 无")
        for item in subset:
            lines.append(f"- `{item['passage']}` · {item['check']}：{item['detail']}")
        lines.append("")

    lines.append("## 备注")
    lines.append("")
    lines.append("- “缺词”= 未在正文出现的本片目标词数量；“别篇词”= 正文中出现的别篇目标词种类数，仅统计不作错误。")
    lines.append("- 正文出现别篇目标词属正常现象（规格允许非目标常用词），本报告不计为错误。")
    lines.append("- 回译条目的中文允许改写或合并原句，相似度低只作备注，不作错误；关键词缺失计入提示。")
    lines.append("- 题材标签为粗粒度分类，标签相同但标题/故事不同时仅提示人工判断。")
    report = "\n".join(lines) + "\n"

    if write:
        (WORK / "audit-report.md").write_text(report, encoding="utf-8")
        (WORK / "audit-report.json").write_text(
            json.dumps({"stats": {k: {kk: vv for kk, vv in v.items() if kk not in {"text", "textWords", "perSentence", "otherTargets"}}
                                  for k, v in stats.items()},
                        "issues": issues, "passed": passed},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    print(f"篇目 {len(contents)}  错误 {len(errors)}  提示 {len(warns)}  备注 {len(infos)}")
    for name, ok in passed.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if errors:
        print("\n错误：")
        for item in errors[:40]:
            print(f"  [{item['passage']}] {item['check']}：{item['detail']}")
    if warns:
        print("\n提示（前 20）：")
        for item in warns[:20]:
            print(f"  [{item['passage']}] {item['check']}：{item['detail']}")
    if write:
        print(f"\n报告：{WORK / 'audit-report.md'} 与 {WORK / 'audit-report.json'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(write="--no-write" not in sys.argv))
