#!/usr/bin/env python3
"""补漏篇成稿校验脚本（b01–b05 专用，对照主线 qc_check.py）。

用法：
    python3 work/qc_check_supplement.py data/content/b01.json

补漏规格（v5 计划 4.1 / 4.3 / 4.6）：
  篇长 280–315 词；句数 29–32；每句 8–11 词、2–4 个目标词；
  目标词 57–58 个、每个 ≥1 次；目标词次密度 18%–22%；
  目标词全部 stars=0、star_source=zhongkao（词卡同标）；
  可用词性下限：可名 ≥30 / 可动 ≥20 / 可形副 ≥10；
  回引主线 p01–p22 已学词 ≥15 个（不计入目标词）；
  词卡顺序与 assignment-supplement.tsv 一致，搭配取自正文；
  挖空答案单词且能回拼原句；检测题 8 道、答案索引合法。
只读 data/，不写任何文件。
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

TOKEN = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
FORM_FIX = {
    "tired": {"tire", "tires", "tired", "tiring"},
    "lie": {"lie", "lies", "lay", "lying", "lain"},
    "swing": {"swing", "swings", "swung", "swinging"},
}
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "it", "its", "my", "our", "her", "his", "their",
    "she", "he", "we", "they", "this", "that", "these", "those", "but", "so", "as",
    "by", "from", "not", "no", "will", "cannot", "can", "must", "be", "us", "me",
    "him", "them", "i", "you", "has", "have", "had", "does", "do", "did", "may",
}


def load_targets(passage_id):
    path = DATA_DIR / "assignment-supplement.tsv"
    with path.open(encoding="utf-8") as handle:
        return [row["lemma"] for row in csv.DictReader(handle, delimiter="\t")
                if row["passage"] == passage_id]


def load_assignment(name):
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def surface_forms(lemma, entries):
    forms = {lemma, lemma + "s", lemma + "es", lemma + "ed", lemma + "d", lemma + "ing",
             lemma + "er", lemma + "est", lemma + "ies", lemma + "'s"}
    forms |= {form.lower() for form in entries.get(lemma, {}).get("forms", [])}
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
    sup = {w["lemma"]: w for w in json.loads((DATA_DIR / "supplement.json").read_text())["words"]}
    main_lex = {w["lemma"]: w for w in json.loads((DATA_DIR / "lexicon.json").read_text())["words"]}
    forms = {lemma: surface_forms(lemma, sup) for lemma in targets}

    sentences = [s for para in content["paragraphs"] for s in para]
    text = normalize(" ".join(s["en"] for s in sentences))
    text_words = {w.lower() for w in TOKEN.findall(text)}

    counts = {lemma: 0 for lemma in targets}
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
        rows.append((index, len(tokens), len(hits), hits))

    tokens_total = sum(counts.values())
    missing = [lemma for lemma, count in counts.items() if count < 1]
    repeats = {lemma: count for lemma, count in counts.items() if count > 1}
    bad_len = [(i, n) for i, n, _, _ in rows if not 8 <= n <= 11]
    bad_density = [(i, n) for i, n, n_hits, _ in rows if not 2 <= n_hits <= 4]
    density = tokens_total / total
    unique_density = len(targets) / total

    print(f"file         {path}")
    print(f"passage      {passage_id}  目标词 {len(targets)} (补漏 57–58)")
    print(f"words        {total}        (280–315)")
    print(f"sentences    {len(sentences)}        (29–32)  avg {total / len(sentences):.2f}")
    print(f"bad length   {bad_len}       (每句 8–11 词)")
    print(f"target T     {tokens_total}       density {density:.3f}  (0.18–0.22)")
    print(f"unique dens  {unique_density:.3f}")
    print(f"targets <1   {missing}")
    print(f"repeats      {repeats}")
    print(f"per-sentence {[n for _, _, n, _ in rows]}")
    print(f"bad T/sent   {bad_density}   (每句 2–4 个目标词)")

    noun = verb = adj_adv = 0
    for lemma in targets:
        pos = set(sup.get(lemma, {}).get("pos", []))
        noun += "n" in pos
        verb += "v" in pos
        adj_adv += bool(pos & {"adj", "adv"})
    print(f"pos floor    n={noun} (≥30)  v={verb} (≥20)  adj/adv={adj_adv} (≥10)")

    # 来源标注：补漏词必须 stars=0 / star_source=zhongkao
    bad_source = [lemma for lemma in targets
                  if sup.get(lemma, {}).get("stars") != 0
                  or sup.get(lemma, {}).get("star_source") != "zhongkao"]
    print(f"source       bad={bad_source}  (stars=0, star_source=zhongkao)")

    # 回引主线已学词（p01–p22），不计入目标词
    p0122 = {row["lemma"] for row in load_assignment("assignment.tsv")
             if row["passage"] in {f"s3000-p{i:02d}" for i in range(1, 23)}}
    main_forms = {lemma: surface_forms(lemma, main_lex) for lemma in p0122}
    recall, outside = set(), set()
    for word in (w.lower() for w in TOKEN.findall(text)):
        if word.endswith("'s"):
            word = word[:-2]
        if word in FUNCTION_WORDS or word in text_words and any(word in forms[t] for t in targets):
            continue
        if any(word in forms[t] for t in targets):
            continue
        hit = next((lemma for lemma in p0122 if word in main_forms[lemma]), None)
        if hit:
            recall.add(hit)
        else:
            outside.add(word)
    print(f"recall       {len(recall)} 个 p01–p22 已学词（≥15）")
    print(f"recall list  {sorted(recall)}")
    print(f"outside      {sorted(outside)}  （非目标、非 p01–p22，人工判断是否常用日常词）")

    cards = content.get("words", [])
    print(f"cards        {len(cards)}  order_ok={[w['lemma'] for w in cards] == targets}")
    print(f"cards bad    {[w.get('lemma') for w in cards if not (w.get('pos') and w.get('zh') and w.get('collocation'))]}")
    bad_star = [w["lemma"] for w in cards
                if w.get("stars") != 0 or w.get("star_source") != "zhongkao"]
    print(f"cards source bad={bad_star}")
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
        "A + adj + N + V": sum(1 for s in en if re.match(r"A\b", s)),
        "My/Our + N + V": sum(1 for s in en if re.match(r"(My|Our)\b", s)),
        "At/After/Then 开头": sum(1 for s in en if re.match(r"(At|After|Then)\b", s)),
    }
    print(f"patterns     {patterns}  (补漏 3 个模板)")

    stray = [s for s in en if re.search(r"\bnot\b[^.;]*\bbut\b", s) or re.search(r"\bnever\b[^.;]*\bbut\b", s)]
    print(f"R9 配对回环   {stray}")

    metrics = content.get("metrics", {})
    metrics_ok = (metrics.get("words") == total and metrics.get("sentences") == len(sentences)
                  and abs(metrics.get("targetTokenDensity", 0) - density) < 0.002
                  and abs(metrics.get("newDensity", 0) - unique_density) < 0.002)
    print(f"metrics      {metrics.get('words')}/{metrics.get('sentences')} "
          f"{metrics.get('targetTokenDensity')}/{metrics.get('newDensity')}  ok={metrics_ok}")

    fails = []
    if not 280 <= total <= 315:
        fails.append("篇长不在 280–315")
    if not 29 <= len(sentences) <= 32:
        fails.append("句数不在 29–32")
    if bad_len:
        fails.append("存在 8 词以下或 11 词以上的句子")
    if bad_density:
        fails.append("存在目标词少于 2 个或多于 4 个的句子")
    if not 0.18 <= density <= 0.22:
        fails.append("目标词密度不在 18–22%")
    if not 57 <= len(targets) <= 58:
        fails.append("目标词数不是 57–58")
    if missing:
        fails.append("有目标词未出现")
    if noun < 30 or verb < 20 or adj_adv < 10:
        fails.append("可用词性下限未达标")
    if bad_source:
        fails.append("补漏词来源标注不是 stars=0 / zhongkao")
    if len(recall) < 15:
        fails.append("回引主线 p01–p22 已学词不足 15 个")
    if len(cards) != len(targets) or [w["lemma"] for w in cards] != targets:
        fails.append("词卡数量或顺序与账簿不符")
    if bad_col or bad_star:
        fails.append("词卡搭配未取自正文或来源标注错误")
    if bad_answer or bad_rebuild:
        fails.append("挖空答案不是单词或无法回拼原句")
    if len(quiz) != 8 or bad_quiz:
        fails.append("检测题不足 8 题或答案索引非法")
    if not metrics_ok:
        fails.append("metrics 与脚本统计不一致")
    if len(metrics.get("patterns", [])) < 3 or min(patterns.values()) < 1:
        fails.append("句式模板不足 3 个")
    if stray:
        fails.append("存在配对回环 / 同句先肯定再否定")

    print(f"RESULT       {'PASS' if not fails else 'FAIL: ' + '；'.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
