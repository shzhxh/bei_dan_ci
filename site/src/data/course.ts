export type RouteId = 'zhongkao' | 'full';

export interface RouteMeta {
  id: RouteId;
  name: string;
  subtitle: string;
  passageCount: number;
  wordCount: number;
  description: string;
}

/**
 * 双轨结构：
 * 主线 50 篇（2,953 个 Collins 3–5★ 词）
 * 中考补漏 5 篇（289 个无星级中考词）
 * 中考路线 = 前 22 篇主线 + 5 篇补漏 = 27 篇
 */
export const ROUTES: Record<RouteId, RouteMeta> = {
  full: {
    id: 'full',
    name: '主线路线',
    subtitle: '主线 50 篇',
    passageCount: 50,
    wordCount: 2953,
    description: '50 篇主线短文，覆盖 2,953 个 Collins 3–5★ 高频词。学完主线即为完整路线。',
  },
  zhongkao: {
    id: 'zhongkao',
    name: '中考路线',
    subtitle: '22 主线 + 5 补漏',
    passageCount: 27,
    wordCount: 1590,
    description: '前 22 篇主线加 5 篇考纲补漏，共 27 篇，覆盖 1,547 个中考词。',
  },
};

export interface StageMeta {
  stage: number;
  label: string;
  range: string;
  sentenceMin: number;
  sentenceLimit: number;
}

export const STAGES: StageMeta[] = [
  { stage: 1, label: 'S1 起步', range: '1–10', sentenceMin: 8, sentenceLimit: 11 },
  { stage: 2, label: 'S2 渐入', range: '11–20', sentenceMin: 8, sentenceLimit: 12 },
  { stage: 3, label: 'S3 稳定', range: '21–30', sentenceMin: 8, sentenceLimit: 13 },
  { stage: 4, label: 'S4 加深', range: '31–40', sentenceMin: 8, sentenceLimit: 14 },
  { stage: 5, label: 'S5 收束', range: '41–50', sentenceMin: 8, sentenceLimit: 14 },
];

export const TRACKS = {
  main: {
    id: 'main',
    name: '主线',
    label: '主线 50 篇',
    words: 2953,
    note: 'Collins 3–5★ 星级词',
  },
  supplement: {
    id: 'supplement',
    name: '考纲补漏',
    label: '考纲补漏 5 篇',
    words: 289,
    note: '无星级中考词 · 仅中考路线',
  },
} as const;
