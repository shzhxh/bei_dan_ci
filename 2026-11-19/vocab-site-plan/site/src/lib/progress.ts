/**
 * 本地学习进度（唯一存储层）。
 * 浏览器 localStorage，键：vocab.progress.v1；无后端、无上传。
 * 结构变更时提升 SCHEMA_VERSION 并在 loadProgress 中做迁移。
 */

export const STORAGE_KEY = 'vocab.progress.v1';
export const SCHEMA_VERSION = 1;
export const DAILY_REVIEW_LIMIT = 120;
export const SRS_INTERVALS = [1, 3, 7, 16, 35] as const;

export type RouteId = 'zhongkao' | 'full';

export interface ReciteState {
  b1: boolean;
  b2: boolean;
  b3: boolean;
  b4: boolean;
}

export interface PassageProgress {
  read: boolean;
  readAt: string | null;
  recite: ReciteState;
  quizScore: number | null;
  quizTotal: number | null;
  visits: number;
  lastVisit: string | null;
}

export interface SrsCard {
  id: string;
  passageId: string;
  lemma: string;
  due: string;
  step: number;
  reviews: number;
  lapses: number;
  sentence?: string;
  zh?: string;
}

export interface CardSeed {
  lemma: string;
  sentence?: string;
  zh?: string;
}

export interface Settings {
  fontSize: number;
  lineHeight: number;
  rate: number;
}

export interface ProgressState {
  version: number;
  route: RouteId;
  passages: Record<string, PassageProgress>;
  cards: SrsCard[];
  reviewsByDate: Record<string, number>;
  streak: { current: number; longest: number; lastActive: string | null };
  settings: Settings;
  updatedAt: string;
}

const emptyPassage = (): PassageProgress => ({
  read: false,
  readAt: null,
  recite: { b1: false, b2: false, b3: false, b4: false },
  quizScore: null,
  quizTotal: null,
  visits: 0,
  lastVisit: null,
});

export const defaultProgress = (): ProgressState => ({
  version: SCHEMA_VERSION,
  route: 'full',
  passages: {},
  cards: [],
  reviewsByDate: {},
  streak: { current: 0, longest: 0, lastActive: null },
  settings: { fontSize: 18, lineHeight: 1.9, rate: 1 },
  updatedAt: new Date().toISOString(),
});

/* ---------------- 日期 ---------------- */

export const dateKey = (date = new Date()): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const addDays = (days: number, from = new Date()): string => {
  const date = new Date(from);
  date.setDate(date.getDate() + days);
  return dateKey(date);
};

const dayDiff = (fromKey: string, toKey: string): number => {
  const [fy, fm, fd] = fromKey.split('-').map(Number);
  const [ty, tm, td] = toKey.split('-').map(Number);
  const from = new Date(fy, fm - 1, fd).getTime();
  const to = new Date(ty, tm - 1, td).getTime();
  return Math.round((to - from) / 86_400_000);
};

/* ---------------- 读写 ---------------- */

export const loadProgress = (): ProgressState => {
  if (typeof localStorage === 'undefined') return defaultProgress();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultProgress();
    const parsed = JSON.parse(raw) as Partial<ProgressState>;
    if (!parsed || typeof parsed !== 'object') return defaultProgress();
    const base = defaultProgress();
    return {
      ...base,
      ...parsed,
      version: SCHEMA_VERSION,
      passages: { ...base.passages, ...(parsed.passages ?? {}) },
      cards: Array.isArray(parsed.cards) ? parsed.cards : [],
      reviewsByDate: parsed.reviewsByDate ?? {},
      streak: { ...base.streak, ...(parsed.streak ?? {}) },
      settings: { ...base.settings, ...(parsed.settings ?? {}) },
    };
  } catch {
    return defaultProgress();
  }
};

export const saveProgress = (state: ProgressState): void => {
  if (typeof localStorage === 'undefined') return;
  state.updatedAt = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('vocab:progress', { detail: state }));
  }
};

export const updateProgress = (mutator: (state: ProgressState) => void): ProgressState => {
  const state = loadProgress();
  mutator(state);
  saveProgress(state);
  return state;
};

const ensurePassage = (state: ProgressState, passageId: string): PassageProgress => {
  if (!state.passages[passageId]) state.passages[passageId] = emptyPassage();
  return state.passages[passageId];
};

const touchStreak = (state: ProgressState): void => {
  const today = dateKey();
  const last = state.streak.lastActive;
  if (last === today) return;
  if (last && dayDiff(last, today) === 1) state.streak.current += 1;
  else state.streak.current = 1;
  state.streak.lastActive = today;
  state.streak.longest = Math.max(state.streak.longest, state.streak.current);
};

/* ---------------- 学习动作 ---------------- */

export const visitPassage = (passageId: string): PassageProgress => {
  let result = emptyPassage();
  updateProgress((state) => {
    const passage = ensurePassage(state, passageId);
    passage.visits += 1;
    passage.lastVisit = new Date().toISOString();
    result = { ...passage, recite: { ...passage.recite } };
  });
  return result;
};

/** 完成首次精读：记录阅读态，并为该篇目标词建立 SRS 卡（当日晚些时候可复习）。 */
export const markPassageRead = (
  passageId: string,
  seeds: Array<CardSeed | string> = [],
): ProgressState =>
  updateProgress((state) => {
    const passage = ensurePassage(state, passageId);
    const firstTime = !passage.read;
    passage.read = true;
    passage.readAt = passage.readAt ?? new Date().toISOString();
    if (firstTime && seeds.length) {
      const today = dateKey();
      for (const seed of seeds) {
        const item: CardSeed = typeof seed === 'string' ? { lemma: seed } : seed;
        if (!item.lemma) continue;
        const id = `${passageId}:${item.lemma}`;
        if (state.cards.some((card) => card.id === id)) continue;
        state.cards.push({
          id,
          passageId,
          lemma: item.lemma,
          due: today,
          step: 0,
          reviews: 0,
          lapses: 0,
          sentence: item.sentence,
          zh: item.zh,
        });
      }
    }
    touchStreak(state);
  });

export const setReciteStage = (passageId: string, stage: keyof ReciteState, done = true): ProgressState =>
  updateProgress((state) => {
    const passage = ensurePassage(state, passageId);
    passage.recite[stage] = done;
    touchStreak(state);
  });

export const recordQuiz = (passageId: string, score: number, total: number): ProgressState =>
  updateProgress((state) => {
    const passage = ensurePassage(state, passageId);
    passage.quizScore = score;
    passage.quizTotal = total;
    touchStreak(state);
  });

export const setRoute = (route: RouteId): ProgressState =>
  updateProgress((state) => {
    state.route = route;
  });

export const saveSettings = (settings: Partial<Settings>): ProgressState =>
  updateProgress((state) => {
    state.settings = { ...state.settings, ...settings };
  });

/* ---------------- SRS ---------------- */

export const dueCards = (state = loadProgress(), today = dateKey()): SrsCard[] =>
  state.cards
    .filter((card) => card.due <= today)
    .sort((a, b) => a.due.localeCompare(b.due));

export const upcomingCards = (state = loadProgress(), today = dateKey()): SrsCard[] =>
  state.cards.filter((card) => card.due > today).sort((a, b) => a.due.localeCompare(b.due));

export const reviewsToday = (state = loadProgress(), today = dateKey()): number =>
  state.reviewsByDate[today] ?? 0;

/**
 * 四档评分：忘记 / 模糊 / 记得 / 很熟。
 * 间隔阶梯 1 / 3 / 7 / 16 / 35 天；忘记回到第 1 档。
 */
export const rateCard = (cardId: string, rating: 0 | 1 | 2 | 3): ProgressState =>
  updateProgress((state) => {
    const card = state.cards.find((item) => item.id === cardId);
    if (!card) return;
    if (rating === 0) {
      card.step = 0;
      card.lapses += 1;
    } else if (rating === 1) {
      card.step = Math.max(0, card.step);
    } else {
      const increment = rating === 2 ? 1 : 2;
      card.step = Math.min(SRS_INTERVALS.length - 1, card.step + increment);
    }
    card.reviews += 1;
    card.due = addDays(SRS_INTERVALS[card.step]);
    const today = dateKey();
    state.reviewsByDate[today] = (state.reviewsByDate[today] ?? 0) + 1;
    touchStreak(state);
  });

/* ---------------- 统计与导入导出 ---------------- */

export interface ProgressStats {
  learnedPassages: number;
  learnedWords: number;
  quizAvg: number | null;
  dueCount: number;
  recitePassages: number;
}

/**
 * 按传入的篇目权重统计，避免把补漏篇混进主线的分母。
 * weights 为空时退化为“每篇最多 60 词”的兜底口径。
 */
export const statsOf = (
  state = loadProgress(),
  weights: Record<string, number> = {},
): ProgressStats => {
  const ids = Object.keys(weights);
  const inScope = (passageId: string) => ids.length === 0 || ids.includes(passageId);
  const passages = Object.entries(state.passages).filter(([id]) => inScope(id));
  const learned = passages.filter(([, passage]) => passage.read);
  const quizzes = passages.filter(
    ([, passage]) => passage.quizTotal && passage.quizScore !== null,
  );
  const quizAvg = quizzes.length
    ? Math.round(
        (quizzes.reduce(
          (sum, [, passage]) => sum + (passage.quizScore ?? 0) / (passage.quizTotal ?? 1),
          0,
        ) /
          quizzes.length) *
          100,
      )
    : null;
  return {
    learnedPassages: learned.length,
    learnedWords: learned.reduce(
      (sum, [id, ,]) => sum + (weights[id] ?? 60),
      0,
    ),
    quizAvg,
    dueCount: state.cards.filter(
      (card) => card.due <= dateKey() && inScope(card.passageId),
    ).length,
    recitePassages: passages.filter(([, passage]) =>
      Boolean(passage.recite.b2 || passage.recite.b3 || passage.recite.b4),
    ).length,
  };
};

export const exportProgress = (state = loadProgress()): string => JSON.stringify(state, null, 2);

export const importProgress = (raw: string): { ok: boolean; error?: string } => {
  try {
    const parsed = JSON.parse(raw) as Partial<ProgressState>;
    if (!parsed || typeof parsed !== 'object') return { ok: false, error: '文件内容不是有效的进度对象。' };
    if (!parsed.passages || typeof parsed.passages !== 'object') {
      return { ok: false, error: '缺少 passages 字段，可能不是本站在导出文件。' };
    }
    const base = defaultProgress();
    saveProgress({
      ...base,
      ...parsed,
      version: SCHEMA_VERSION,
      passages: { ...parsed.passages },
      cards: Array.isArray(parsed.cards) ? parsed.cards : [],
      reviewsByDate: parsed.reviewsByDate ?? {},
      streak: { ...base.streak, ...(parsed.streak ?? {}) },
      settings: { ...base.settings, ...(parsed.settings ?? {}) },
    });
    return { ok: true };
  } catch {
    return { ok: false, error: '无法解析 JSON。' };
  }
};

export const resetProgress = (): ProgressState => {
  const state = defaultProgress();
  saveProgress(state);
  return state;
};
