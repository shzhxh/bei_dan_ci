# 背单词 55 篇

一个纯静态的英语背诵站点：55 篇短文（主线 50 篇 + 考纲补漏 5 篇），覆盖 3,242 个目标词。
页面由 Astro 构建，无后端、无账号，学习进度只保存在浏览器 localStorage（`vocab.progress.v1`）。

站点地址（部署后）：<https://shzhxh.github.io/bei_dan_ci/>

## 仓库结构

```
.
├── site/       Astro 站点源码（构建入口）
├── data/       词表、分篇账簿、校验数据与 55 篇成稿（data/content/）
├── scripts/    预览、词表构建、审计与写作自查脚本
├── docs/plan/  建设计划、阶段任务清单与历史版本（v1–v4）
└── .github/workflows/deploy.yml   GitHub Pages 自动构建与发布
```

`site/` 与 `data/` 是同级目录，站点构建时读取 `../data/`。

## 本地预览

```bash
cd "$(git rev-parse --show-toplevel)"
./scripts/preview.sh                # http://localhost:4321/
./scripts/preview.sh -p 4400        # 换端口
./scripts/preview.sh --host 0.0.0.0 # 允许局域网访问
```

脚本会自动把 `$HOME/.local/node/bin`（若存在）加入 PATH；也可用 `NODE_BIN_DIR` 指定 Node 目录。

手动启动：

```bash
cd site
npm ci
npm run dev
```

## 构建

要求 Node 22（Node 18+ 可用）。从仓库根目录执行：

```bash
cd site
npm ci
npm run build        # 输出到 site/dist，共 62 个 HTML 页面
npm run check        # 可选：Astro/TypeScript 类型检查
```

62 页 = 首页、课程、复习、看板、方法、关于、404 共 7 个站级页 + p01–p55 共 55 个短文页。

本地构建时 `base` 默认为 `/`；部署工作流会注入 `BASE_PATH` 与 `SITE_URL`，无需手改配置。

## 部署到 GitHub Pages

仓库已配置 `.github/workflows/deploy.yml`，推送到 `main` 即自动构建并发布：

1. 在 GitHub 仓库 **Settings → Pages** 中，把 **Source** 设为 **GitHub Actions**。
2. 推送到 `main`：

```bash
git push -u origin main
```

3. 工作流会：安装 `site/` 依赖 → 以 `site/` 为工作目录构建 → 上传 `site/dist` → 发布。
   项目站点自动使用 `/bei_dan_ci/` 作为 base；若仓库改名为 `<user>.github.io`，自动切换为 `/`。

远端：`origin` = `git@github.com:shzhxh/bei_dan_ci.git`，分支 `main`。

## 数据与许可

- 分篇与词表：`data/assignment.tsv`、`data/assignment-supplement.tsv`、`data/lexicon.json`、`data/zhongkao.json`。
- 成稿：`data/content/*.json`，55 篇，构建时读取；缺少或损坏的篇目会回退为「内容制作中」占位。
- `data/vendor/ecdict.csv` 为 63MB 的 ECDICT 原始词库，**未入库**：GitHub 建议单文件不超过 50MB（硬上限 100MB），
  该文件仅用于词表生成流程，站点构建不依赖它，入库会显著增大克隆体积。
  需要重建词表时请从 [ECDICT](https://github.com/skywind3000/ECDICT) 获取并放到 `data/vendor/`。
  其许可证保留在 `data/vendor/ECDICT-LICENSE.txt`。
- `docs/plan/` 中的历史版本（v1–v4）一并保留，便于追溯方案变更，不参与构建。
