/**
 * 客户端课程目录。
 * 构建期由 BaseLayout 把目录摘要写进 #site-catalog，浏览器只读这份 JSON，
 * 不在客户端打包 fs 数据或成稿正文。
 */

import type { Track } from './catalog.server';

export interface ClientPassage {
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
  hasContent: boolean;
}

export interface ClientCatalog {
  passages: ClientPassage[];
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

const EMPTY: ClientCatalog = {
  passages: [],
  totals: {
    passages: 0,
    words: 0,
    mainWords: 0,
    supplementWords: 0,
    zhongkaoWords: 0,
    zhongkaoPassages: 0,
    mainZhongkaoPassages: 0,
  },
};

export const readCatalog = (): ClientCatalog => {
  if (typeof document === 'undefined') return EMPTY;
  const node = document.getElementById('site-catalog');
  if (!node?.textContent) return EMPTY;
  try {
    return JSON.parse(node.textContent) as ClientCatalog;
  } catch {
    return EMPTY;
  }
};

export const mainPassages = (catalog: ClientCatalog): ClientPassage[] =>
  catalog.passages.filter((passage) => passage.track === 'main');

export const supplementPassages = (catalog: ClientCatalog): ClientPassage[] =>
  catalog.passages.filter((passage) => passage.track === 'supplement');

export const zhongkaoPassages = (catalog: ClientCatalog): ClientPassage[] =>
  catalog.passages.filter((passage) => passage.inZhongkaoRoute);

export const weightsOf = (passages: ClientPassage[]): Record<string, number> =>
  Object.fromEntries(passages.map((passage) => [passage.id, passage.targetCount]));

export const findPassage = (
  catalog: ClientCatalog,
  passageId: string,
): ClientPassage | undefined => catalog.passages.find((passage) => passage.id === passageId);
