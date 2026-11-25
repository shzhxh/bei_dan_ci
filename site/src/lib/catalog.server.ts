import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * 构建期内容加载层（仅服务端使用）。
 * - 主线：data/assignment.tsv（50 组，2,953 词）
 * - 中考补漏：data/assignment-zhongkao.tsv（可选，数据到位前用 5 个空壳）
 * - 成稿：data/content/{id}.json（p01…p50 / p51…p55），缺省即“内容制作中”
 * 只用 fs 读取，不修改 data/ 下任何文件。
 */

export interface Sentence {
  en: string;
  zh: string;
}

export interface WordEntry {
  lemma: string;
  pos: string;
  zh: string;
  collocation: string;
}

export interface ClozeItem {
  before: string;
  hint: string;
  after: string;
  answer: string;
}

export interface QuizQuestion {
  id: string;
  type: string;
  prompt: string;
  options: string[];
  answer: number;
  speak?: string;
}

export interface PassageContent {
  title?: string;
  titleZh?: string;
  topic?: string;
  paragraphs: Sentence[][];
  flatSentences: Sentence[];
  words: WordEntry[];
  quiz: QuizQuestion[];
  recite: {
    b2: ClozeItem[];
    b3: ClozeItem[];
    b4: Array<{ zh: string; keywords: string[] }>;
  };
  metrics?: {
    words?: number;
    sentences?: number;
    newDensity?: number;
    targetTokenDensity?: number;
    patterns?: string[];
  };
  note?: string;
  sourcePath?: string;
}

export type Track = 'main' | 'supplement';

export interface CatalogPassage {
  id: string;
  slug: string;
  order: number;
  title: string;
  titleZh: string;
  topic: string;
  stage: number;
  track: Track;
  inZhongkaoRoute: boolean;
  targetCount: number;
  wordCount: number;
  lemmas: string[];
  content: PassageContent | null;
}

export interface Catalog {
  passages: CatalogPassage[];
  main: CatalogPassage[];
  supplement: CatalogPassage[];
  totals: {
    passages: number;
    words: number;
    mainWords: number;
    supplementWords: number;
    zhongkaoWords: number;
    zhongkaoPassages: number;
    mainZhongkaoPassages: number;
  };
}

const SITE_ROOT = process.cwd();
const DATA_DIR = process.env.VOCAB_DATA_DIR
  ? resolve(process.env.VOCAB_DATA_DIR)
  : resolve(SITE_ROOT, '../data');
const CONTENT_DIR = process.env.VOCAB_CONTENT_DIR
  ? resolve(process.env.VOCAB_CONTENT_DIR)
  : join(DATA_DIR, 'content');

const STAGE_SIZE = 10;
const SUPPLEMENT_COUNT = 5;
const SUPPLEMENT_WORD_TOTAL = 289;

const MAIN_TITLES: Array<[string, string, string]> = [
  ['The Crowded Platform', '拥挤的站台', '出行'],
  ['A Late Breakfast', '迟到的早餐', '日常'],
  ['The Missing Key', '不见的钥匙', '家庭'],
  ['A Noise Upstairs', '楼上的声响', '邻里'],
  ['The Small Bookshop', '小书店', '城市'],
  ['A Rainy Walk', '雨中散步', '天气'],
  ['The Broken Chair', '坏掉的椅子', '日常'],
  ['A Letter from Home', '家里的来信', '家庭'],
  ['The Garden Next Door', '隔壁的花园', '邻里'],
  ['A Long Queue', '长长的队伍', '城市'],
  ['The Quiet Neighbour', '安静的邻居', '邻里'],
  ['A Different Route', '另一条路', '出行'],
  ['The Old Bicycle', '旧自行车', '日常'],
  ['A Table for Two', '两人桌', '日常'],
  ['The Night Bus', '夜班车', '出行'],
  ['A Simple Repair', '简单的修理', '日常'],
  ['The Borrowed Umbrella', '借来的伞', '天气'],
  ['A Change of Plan', '改变计划', '出行'],
  ['The Cold Morning', '寒冷的清晨', '天气'],
  ['A Voice at the Door', '门口的说话声', '邻里'],
  ['The Untidy Desk', '凌乱的书桌', '学习'],
  ['A Short Holiday', '短暂的假期', '旅行'],
  ['The Light in the Hall', '走廊的灯', '家庭'],
  ['A Difficult Choice', '难做的选择', '学习'],
  ['The Second Chance', '第二次机会', '工作'],
  ['A Message on the Wall', '墙上的留言', '城市'],
  ['The Empty Seat', '空座位', '日常'],
  ['A New Beginning', '新的开始', '学习'],
  ['The First Snow', '初雪', '天气'],
  ['A Borrowed Book', '借来的书', '学习'],
  ['The Long Night', '长夜', '工作'],
  ['A Small Mistake', '小错', '工作'],
  ['The Open Window', '开着的窗', '家庭'],
  ['A Street Performer', '街头艺人', '城市'],
  ['The Last Train', '末班车', '出行'],
  ['A Quiet Argument', '安静的争执', '关系'],
  ['The Old Photograph', '旧照片', '家庭'],
  ['A Different Answer', '不同的答案', '学习'],
  ['The Busy Market', '热闹的市场', '城市'],
  ['A Promise Kept', '守住的承诺', '关系'],
  ['The Sinking Boat', '下沉的船', '自然'],
  ['A Voice in the Crowd', '人群中的声音', '城市'],
  ['The Locked Room', '上锁的房间', '家庭'],
  ['A Season of Waiting', '等待的季节', '自然'],
  ['The Hidden Path', '隐藏的小路', '自然'],
  ['A Matter of Trust', '信任问题', '关系'],
  ['The Returning Tide', '回潮', '自然'],
  ['A City at Night', '夜里的城', '城市'],
  ['The Unfinished Letter', '未写完的信', '关系'],
  ['A Question of Time', '时间问题', '工作'],
];

const SUPPLEMENT_TITLES: Array<[string, string]> = [
  ['Zhongkao Supplement 1', '考纲补漏（一）'],
  ['Zhongkao Supplement 2', '考纲补漏（二）'],
  ['Zhongkao Supplement 3', '考纲补漏（三）'],
  ['Zhongkao Supplement 4', '考纲补漏（四）'],
  ['Zhongkao Supplement 5', '考纲补漏（五）'],
];

const pad = (value: number) => String(value).padStart(2, '0');

interface AssignmentRow {
  lemma: string;
  passage: string;
  route: string;
}

const parseTsv = (path: string): AssignmentRow[] => {
  if (!existsSync(path)) return [];
  const text = readFileSync(path, 'utf8').replace(/^\uFEFF/, '');
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];
  const header = lines[0].split('\t');
  const index = {
    lemma: header.indexOf('lemma'),
    passage: header.indexOf('passage'),
    route: header.indexOf('route'),
  };
  if (index.lemma < 0 || index.passage < 0) return [];
  const rows: AssignmentRow[] = [];
  for (const line of lines.slice(1)) {
    const cells = line.split('\t');
    const lemma = cells[index.lemma]?.trim();
    const passage = cells[index.passage]?.trim();
    if (!lemma || !passage) continue;
    rows.push({ lemma, passage, route: cells[index.route]?.trim() ?? '' });
  }
  return rows;
};

const groupByPassage = (rows: AssignmentRow[]): Map<string, string[]> => {
  const groups = new Map<string, string[]>();
  for (const row of rows) {
    const list = groups.get(row.passage) ?? [];
    list.push(row.lemma);
    groups.set(row.passage, list);
  }
  return groups;
};

/* ---------------- 成稿读取 ---------------- */

const pick = (value: unknown, keys: string[]): unknown => {
  if (!value || typeof value !== 'object') return undefined;
  for (const key of keys) {
    const found = (value as Record<string, unknown>)[key];
    if (found !== undefined && found !== null && found !== '') return found;
  }
  return undefined;
};

const asString = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback;

const asNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const normalizeSentence = (raw: unknown): Sentence | null => {
  if (typeof raw === 'string') return { en: raw.trim(), zh: '' };
  if (!raw || typeof raw !== 'object') return null;
  const en = asString(pick(raw, ['en', 'text', 'english', 'sentence'])).trim();
  const zh = asString(pick(raw, ['zh', 'cn', 'chinese', 'translation'])).trim();
  return en ? { en, zh } : null;
};

const normalizeParagraphs = (raw: unknown): { paragraphs: Sentence[][]; flat: Sentence[] } => {
  if (!Array.isArray(raw)) return { paragraphs: [], flat: [] };
  const flat: Sentence[] = [];
  const nested: Sentence[][] = [];
  const topSentences = raw
    .map(normalizeSentence)
    .filter((item): item is Sentence => Boolean(item));

  if (topSentences.length === raw.length && topSentences.length > 0) {
    flat.push(...topSentences);
    for (let i = 0; i < topSentences.length; i += 3) {
      nested.push(topSentences.slice(i, i + 3));
    }
    return { paragraphs: nested, flat };
  }

  for (const paragraph of raw) {
    if (!Array.isArray(paragraph)) {
      const single = normalizeSentence(paragraph);
      if (single) {
        flat.push(single);
        nested.push([single]);
      }
      continue;
    }
    const sentences = paragraph
      .map(normalizeSentence)
      .filter((item): item is Sentence => Boolean(item));
    if (sentences.length) {
      flat.push(...sentences);
      nested.push(sentences);
    }
  }
  return { paragraphs: nested, flat };
};

const normalizeWords = (raw: unknown): WordEntry[] => {
  const list: WordEntry[] = [];
  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== 'object') return;
    const lemma = asString(pick(value, ['lemma', 'word', 'headword'])).trim();
    if (!lemma) return;
    list.push({
      lemma,
      pos: asString(pick(value, ['pos', 'part_of_speech'])),
      zh: asString(pick(value, ['zh', 'cn', 'meaning', 'translation'])),
      collocation: asString(pick(value, ['collocation', 'phrase', 'collocations'])),
    });
  };
  visit(raw);
  return list;
};

const normalizeQuiz = (raw: unknown): QuizQuestion[] => {
  if (!Array.isArray(raw)) return [];
  const questions: QuizQuestion[] = [];
  raw.forEach((item, index) => {
    if (!item || typeof item !== 'object') return;
    const prompt = asString(pick(item, ['prompt', 'question', 'stem']));
    const optionsRaw = pick(item, ['options', 'choices']);
    if (!prompt || !Array.isArray(optionsRaw)) return;
    const options = optionsRaw.map((option) =>
      typeof option === 'string'
        ? option
        : asString(pick(option, ['label', 'text', 'value']), String(option)),
    );
    const answerRaw = pick(item, ['answer', 'correct', 'answerIndex']);
    let answer = typeof answerRaw === 'string' ? options.indexOf(answerRaw) : Number(answerRaw);
    if (!Number.isInteger(answer) || answer < 0 || answer >= options.length) answer = 0;
    questions.push({
      id: asString(pick(item, ['id']), `q${index + 1}`),
      type: asString(pick(item, ['type']), '词义匹配'),
      prompt,
      options,
      answer,
      speak: asString(pick(item, ['speak', 'audio_word'])) || undefined,
    });
  });
  return questions;
};

const normalizeCloze = (raw: unknown): ClozeItem[] => {
  if (!Array.isArray(raw)) return [];
  const items: ClozeItem[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const answer = asString(pick(item, ['answer', 'word']));
    let before = asString(pick(item, ['before', 'prefix']));
    let after = asString(pick(item, ['after', 'suffix']));
    if (!before && !after) {
      const text = asString(pick(item, ['text', 'sentence']));
      const blank = text.indexOf('___');
      if (blank >= 0) {
        before = text.slice(0, blank);
        after = text.slice(blank + 3);
      }
    }
    if (!answer && !before) continue;
    items.push({
      before,
      hint: asString(pick(item, ['hint']), answer.slice(0, 1)),
      after,
      answer,
    });
  }
  return items;
};

const normalizeRecite = (raw: unknown): PassageContent['recite'] => {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const b4Raw = pick(source, ['b4', 'backTranslation']) ?? [];
  const b4 = Array.isArray(b4Raw)
    ? b4Raw
        .map((item) => {
          if (typeof item === 'string') return { zh: item, keywords: [] };
          if (!item || typeof item !== 'object') return null;
          const zh = asString(pick(item, ['zh', 'cn', 'prompt', 'translation']));
          const keywordsRaw = pick(item, ['keywords', 'keyWords']) ?? [];
          return {
            zh,
            keywords: Array.isArray(keywordsRaw) ? keywordsRaw.map((word) => String(word)) : [],
          };
        })
        .filter((item): item is { zh: string; keywords: string[] } => Boolean(item && item.zh))
    : [];
  return {
    b2: normalizeCloze(pick(source, ['b2', 'cloze'])),
    b3: normalizeCloze(pick(source, ['b3', 'initials'])),
    b4,
  };
};

const normalizeContent = (raw: unknown, sourcePath: string): PassageContent | null => {
  if (!raw || typeof raw !== 'object') return null;
  const paragraphsRaw = pick(raw, ['paragraphs', 'body', 'sentences', 'text']);
  const { paragraphs, flat } =
    typeof paragraphsRaw === 'string'
      ? (() => {
          const sentences = paragraphsRaw
            .split(/(?<=[.!?])\s+/)
            .map((en) => ({ en: en.trim(), zh: '' }))
            .filter((item) => item.en);
          return { paragraphs: [sentences], flat: sentences };
        })()
      : normalizeParagraphs(paragraphsRaw);
  const words = normalizeWords(pick(raw, ['words', 'targets', 'vocabulary']));
  if (!flat.length || !words.length) {
    console.warn(`[content] ${sourcePath} 缺少 paragraphs 或 words，按“内容制作中”处理`);
    return null;
  }
  const metricsRaw = pick(raw, ['metrics', 'stats']);
  return {
    title: asString(pick(raw, ['title', 'title_en', 'titleEn'])) || undefined,
    titleZh: asString(pick(raw, ['titleZh', 'title_zh', 'titleCn'])) || undefined,
    topic: asString(pick(raw, ['topic', 'theme'])) || undefined,
    paragraphs,
    flatSentences: flat,
    words,
    quiz: normalizeQuiz(pick(raw, ['quiz', 'questions'])),
    recite: normalizeRecite(pick(raw, ['recite', 'recitation'])),
    metrics: metricsRaw
      ? {
          words: asNumber(pick(metricsRaw, ['words', 'wordCount'])),
          sentences: asNumber(pick(metricsRaw, ['sentences', 'sentenceCount'])),
          newDensity: asNumber(pick(metricsRaw, ['newDensity', 'new_density'])),
          targetTokenDensity: asNumber(
            pick(metricsRaw, ['targetTokenDensity', 'target_token_density']),
          ),
          patterns: Array.isArray(pick(metricsRaw, ['patterns']))
            ? (pick(metricsRaw, ['patterns']) as unknown[]).map(String)
            : undefined,
        }
      : undefined,
    sourcePath,
  };
};

const contentCandidates = (slug: string, track: Track): string[] => {
  if (track === 'supplement') {
    const index = Number(slug) - 50;
    return [
      `p${slug}.json`,
      `s3000-b${pad(index)}.json`,
      `s3000-p${slug}.json`,
      `b${pad(index)}.json`,
      `z${pad(index)}.json`,
      `zk${pad(index)}.json`,
      `supplement-${pad(index)}.json`,
    ];
  }
  return [`p${slug}.json`, `s3000-p${slug}.json`, `${slug}.json`];
};

const loadContent = (slug: string, track: Track): PassageContent | null => {
  if (!existsSync(CONTENT_DIR)) return null;
  for (const name of contentCandidates(slug, track)) {
    const path = join(CONTENT_DIR, name);
    if (!existsSync(path)) continue;
    try {
      const raw = JSON.parse(readFileSync(path, 'utf8'));
      const content = normalizeContent(raw, path);
      if (content) return content;
    } catch (error) {
      console.warn(`[content] 无法解析 ${path}: ${(error as Error).message}`);
    }
  }
  return null;
};

/* ---------------- 组装课程目录 ---------------- */

const countWords = (sentences: Sentence[]): number =>
  sentences.reduce(
    (sum, sentence) => sum + (sentence.en.match(/[A-Za-z][A-Za-z'’-]*/g)?.length ?? 0),
    0,
  );

const buildPassage = (
  order: number,
  track: Track,
  title: string,
  titleZh: string,
  topic: string,
  lemmas: string[],
): CatalogPassage => {
  const slug = String(order).padStart(2, '0');
  const content = loadContent(slug, track);
  return {
    id: `p${slug}`,
    slug,
    order,
    title: content?.title ?? title,
    titleZh: content?.titleZh ?? titleZh,
    topic: content?.topic ?? topic,
    stage: track === 'main' ? Math.ceil(order / STAGE_SIZE) : 0,
    track,
    inZhongkaoRoute: track === 'supplement' || order <= 22,
    targetCount: lemmas.length,
    // 有正文时按内容文件实际词数统计；未成稿为 0，页面显示“篇长待成稿”
    wordCount: content ? countWords(content.flatSentences) : 0,
    lemmas,
    content,
  };
};

const supplementWeights = (): number[] => {
  const base = Math.floor(SUPPLEMENT_WORD_TOTAL / SUPPLEMENT_COUNT);
  const remainder = SUPPLEMENT_WORD_TOTAL - base * SUPPLEMENT_COUNT;
  return Array.from({ length: SUPPLEMENT_COUNT }, (_, index) => base + (index < remainder ? 1 : 0));
};

const buildCatalog = (): Catalog => {
  const mainRows = groupByPassage(parseTsv(join(DATA_DIR, 'assignment.tsv')));
  const supplementPath = ['assignment-zhongkao.tsv', 'assignment-supplement.tsv']
    .map((name) => join(DATA_DIR, name))
    .find((path) => existsSync(path));
  const supplementRows = supplementPath
    ? groupByPassage(parseTsv(supplementPath))
    : new Map<string, string[]>();

  const main: CatalogPassage[] = MAIN_TITLES.map(([title, titleZh, topic], index) => {
    const order = index + 1;
    const lemmas = mainRows.get(`s3000-p${pad(order)}`) ?? [];
    return buildPassage(order, 'main', title, titleZh, topic, lemmas);
  });

  const weights = supplementWeights();
  const supplement: CatalogPassage[] = SUPPLEMENT_TITLES.map(([title, titleZh], index) => {
    const order = 51 + index;
    const lemmas =
      supplementRows.get(`s3000-b${pad(index + 1)}`) ??
      supplementRows.get(`p${pad(order)}`) ??
      supplementRows.get(`s3000-p${pad(order)}`) ??
      supplementRows.get(`b${pad(index + 1)}`) ??
      supplementRows.get(`z${pad(index + 1)}`) ??
      [];
    const passage = buildPassage(order, 'supplement', title, titleZh, '考纲补漏', lemmas);
    if (!lemmas.length) passage.targetCount = weights[index];
    return passage;
  });

  const passages = [...main, ...supplement];
  const mainWords = main.reduce((sum, passage) => sum + passage.targetCount, 0);
  const supplementWords = supplement.reduce((sum, passage) => sum + passage.targetCount, 0);
  const zhongkao = passages.filter((passage) => passage.inZhongkaoRoute);

  return {
    passages,
    main,
    supplement,
    totals: {
      passages: passages.length,
      words: mainWords + supplementWords,
      mainWords,
      supplementWords,
      zhongkaoWords: zhongkao.reduce((sum, passage) => sum + passage.targetCount, 0),
      zhongkaoPassages: zhongkao.length,
      mainZhongkaoPassages: main.filter((passage) => passage.inZhongkaoRoute).length,
    },
  };
};

let cache: Catalog | null = null;

export const getCatalog = (): Catalog => {
  if (!cache) cache = buildCatalog();
  return cache;
};

export const getPassageById = (id: string): CatalogPassage | undefined =>
  getCatalog().passages.find((passage) => passage.id === id);

export const contentFilesPresent = (): string[] => {
  if (!existsSync(CONTENT_DIR)) return [];
  try {
    return readdirSync(CONTENT_DIR).filter((name) => name.endsWith('.json'));
  } catch {
    return [];
  }
};
