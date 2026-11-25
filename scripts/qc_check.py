#!/usr/bin/env python3
"""成稿校验脚本（p01 新参数；p02–p50 / b01–b05 通用）。

用法：
    python3 scripts/qc_check.py data/content/p01.json

校验依据（2026-11-21 修订版参数）：
  篇长 280–320 词；每句 8–14 词；每句 2–4 个目标词；
  60 个目标词各 ≥1 次；目标词次密度 18%–22%；
  可用词性下限：可名 ≥30 / 可动 ≥20 / 可形副 ≥10；
  3 个句式模板各 ≥3 次；
  词卡顺序与 assignment.tsv 一致，搭配取自正文；
  挖空答案必须单词且能回拼原句；检测题 8 道、答案索引合法。

只读 data/，不写任何文件。
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

TOKEN = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
FORM_FIX = {
    "tired": {"tire", "tires", "tired", "tiring"},
    "lie": {"lie", "lies", "lay", "lying", "lain"},
    "swing": {"swing", "swings", "swung", "swinging"},
}


def load_targets(passage_id):
    for name in ("assignment.tsv", "assignment-supplement.tsv"):
        path = DATA_DIR / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            rows = [row["lemma"] for row in csv.DictReader(handle, delimiter="\t")
                    if row["passage"] == passage_id]
        if rows:
            return rows
    return []


def surface_forms(lemma, lexicon):
    forms = {lemma, lemma + "s", lemma + "es", lemma + "ed", lemma + "d", lemma + "ing",
             lemma + "er", lemma + "est", lemma + "ies", lemma + "'s"}
    forms |= {form.lower() for form in lexicon.get(lemma, {}).get("forms", [])}
    forms |= FORM_FIX.get(lemma, set())
    return forms


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    content = json.loads(path.read_text(encoding="utf-8"))
    pid = content.get("id", "")
    passage_id = pid if pid.startswith("s3000-") else f"s3000-{pid}"
    targets = load_targets(passage_id) or [w["lemma"] for w in content.get("words", [])]
    lexicon = {w["lemma"]: w for w in json.loads((DATA_DIR / "lexicon.json").read_text())["words"]}
    forms = {lemma: surface_forms(lemma, lexicon) for lemma in targets}

    sentences = [s for para in content["paragraphs"] for s in para]
    text = normalize(" ".join(s["en"] for s in sentences))
    text_words = {w.lower() for w in TOKEN.findall(text)}

    counts = {lemma: 0 for lemma in targets}
    non_target = {}
    total = 0
    rows = []
    for index, sentence in enumerate(sentences, 1):
        tokens = [w.lower() for w in TOKEN.findall(sentence["en"])]
        total += len(tokens)
        hits = []
        for word in tokens:
            if word.endswith("'s"):
                word = word[:-2]
            hit = next((lemma for lemma in targets if word in forms[lemma]), None)
            if hit:
                counts[hit] += 1
                hits.append(hit)
            elif word not in {"a", "an", "the", "and", "or", "of", "to", "in", "on", "at",
                              "for", "with", "is", "are", "was", "were", "it", "its",
                              "my", "our", "her", "his", "their", "she", "he", "we", "they",
                              "this", "that", "these", "those", "but", "so", "as", "by",
                              "from", "not", "no", "will", "cannot", "can", "must", "be"}:
                non_target[word] = non_target.get(word, 0) + 1
        rows.append((index, len(tokens), len(hits), hits))

    tokens_total = sum(counts.values())
    missing = [lemma for lemma, count in counts.items() if count < 1]
    repeats = {lemma: count for lemma, count in counts.items() if count > 1}
    bad_len = [(i, n) for i, n, _, _ in rows if not 8 <= n <= 14]
    bad_density = [(i, n) for i, n, n_hits, _ in rows if not 2 <= n_hits <= 4]
    density = tokens_total / total
    unique_density = len(targets) / total

    print(f"file         {path}")
    print(f"passage      {passage_id}  目标词 {len(targets)}")
    print(f"words        {total}        (280–320)")
    print(f"sentences    {len(sentences)}        avg {total / len(sentences):.2f}")
    print(f"bad length   {bad_len}       (每句 8–14 词)")
    print(f"target T     {tokens_total}       density {density:.3f}  (0.18–0.22)")
    print(f"unique dens  {unique_density:.3f}")
    print(f"targets <1   {missing}")
    print(f"repeats      {repeats}")
    print(f"per-sentence {[(i, n) for i, _, n, _ in rows]}")
    print(f"bad T/sent   {bad_density}   (每句 2–4 个目标词)")
    print(f"non-target   {sorted(non_target.items(), key=lambda kv: -kv[1])[:20]}")

    noun = verb = adj_adv = 0
    for lemma in targets:
        pos = set(lexicon.get(lemma, {}).get("pos", []))
        noun += "n" in pos
        verb += "v" in pos
        adj_adv += bool(pos & {"adj", "adv"})
    print(f"pos floor    n={noun} (≥30)  v={verb} (≥20)  adj/adv={adj_adv} (≥10)")

    cards = content.get("words", [])
    print(f"cards        {len(cards)}  order_ok={[w['lemma'] for w in cards] == targets}")
    print(f"cards bad    {[w.get('lemma') for w in cards if not (w.get('pos') and w.get('zh') and w.get('stars') and w.get('collocation'))]}")
    bad_col = [(w["lemma"], phrase) for w in cards
               for phrase in w.get("collocation", "").split("/")
               if phrase.strip() and normalize(phrase) not in text]
    print(f"bad colloc   {bad_col}")

    recite = content.get("recite", {})
    cloze = recite.get("b2", []) + recite.get("b3", [])
    bad_answer = [item["answer"] for item in cloze
                  if len(TOKEN.findall(item["answer"])) != 1 or item["answer"].lower() not in text_words]
    bad_rebuild = [item["answer"] for item in cloze
                   if normalize(item["before"] + item["answer"] + item["after"]) not in text]
    print(f"recite       b2={len(recite.get('b2', []))} b3={len(recite.get('b3', []))} b4={len(recite.get('b4', []))}")
    print(f"cloze bad    answer={bad_answer} rebuild={bad_rebuild}")

    quiz = content.get("quiz", [])
    bad_quiz = [q.get("id") for q in quiz
                if not (0 <= q.get("answer", -1) < len(q.get("options", [])))
                or len(set(q.get("options", []))) != len(q.get("options", []))]
    print(f"quiz         {len(quiz)}  bad={bad_quiz}")

    en = [s["en"] for s in sentences]
    patterns = {
        "My + N + V": sum(1 for s in en if re.match(r"My\b", s)),
        "A + adj + N + V": sum(1 for s in en if re.match(r"A\b", s)),
        "During/Then/Later 开头": sum(1 for s in en if re.match(r"(During|Then|Later)\b", s)),
    }
    print(f"patterns     {patterns}  (每个 ≥3)")

    metrics = content.get("metrics", {})
    metrics_ok = (metrics.get("words") == total and metrics.get("sentences") == len(sentences)
                  and abs(metrics.get("targetTokenDensity", 0) - density) < 0.002
                  and abs(metrics.get("newDensity", 0) - unique_density) < 0.002)
    print(f"metrics      {metrics.get('words')}/{metrics.get('sentences')} "
          f"{metrics.get('targetTokenDensity')}/{metrics.get('newDensity')}  ok={metrics_ok}")

    fails = []
    if not 280 <= total <= 320:
        fails.append("篇长不在 280–320")
    if not 20 <= len(sentences) <= 40:
        fails.append("句数不在 20–40")
    if bad_len:
        fails.append("存在 8 词以下或 14 词以上的句子")
    if bad_density:
        fails.append("存在目标词少于 2 个或多于 4 个的句子")
    if not 0.18 <= density <= 0.22:
        fails.append("目标词密度不在 18–22%")
    if missing:
        fails.append("有目标词未出现")
    if noun < 30 or verb < 20 or adj_adv < 10:
        fails.append("可用词性下限未达标")
    if len(cards) != len(targets) or [w["lemma"] for w in cards] != targets:
        fails.append("词卡数量或顺序与账簿不符")
    if bad_col:
        fails.append("词卡搭配未取自正文")
    if bad_answer or bad_rebuild:
        fails.append("挖空答案不是单词或无法回拼原句")
    if len(quiz) != 8 or bad_quiz:
        fails.append("检测题不足 8 题或答案索引非法")
    if not metrics_ok:
        fails.append("metrics 与脚本统计不一致")
    if min(patterns.values()) < 3:
        fails.append("句式模板复用不足 3 次")

    print(f"RESULT       {'PASS' if not fails else 'FAIL: ' + '；'.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
