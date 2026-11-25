/** 统一处理 GitHub Pages 子路径（base）。 */
const rawBase = import.meta.env.BASE_URL || '/';
const base = rawBase.endsWith('/') ? rawBase.slice(0, -1) : rawBase;

export const url = (path = '/'): string => {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (!base) return normalized;
  return `${base}${normalized === '/' ? '/' : normalized}`;
};

export const isActive = (currentPath: string, target: string): boolean => {
  const current = currentPath.replace(/\/+$/, '') || '/';
  const path = target.replace(/\/+$/, '') || '/';
  if (path === '/') return current === '/';
  return current === path || current.startsWith(`${path}/`);
};
