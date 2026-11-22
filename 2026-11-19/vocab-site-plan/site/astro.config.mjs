// @ts-check
import { defineConfig } from 'astro/config';

// GitHub Pages 的项目站点需要子路径（例如 /repo-name/）。
// 用户站点（username.github.io）保持 "/"。
// 部署工作流会通过 BASE_PATH 环境变量注入，本地默认 "/"。
const base = process.env.BASE_PATH || '/';
const site = process.env.SITE_URL || undefined;

export default defineConfig({
  site,
  base,
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
  devToolbar: {
    enabled: false,
  },
});
