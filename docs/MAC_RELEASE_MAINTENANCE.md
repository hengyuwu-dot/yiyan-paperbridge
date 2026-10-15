# Mac 应用更新与模型资源维护

模型和应用独立发布。普通应用更新复用原来的模型文件，用户只下载新的应用与运行环境。

## 发布下一次应用更新

1. 修改应用源码，并将 `release-assets/macos-version.json` 中的 `version` 提升，例如 `1.8.3`。保留 `model_tag`，即可复用现有 4B / 14B 模型资源。
2. 推送后，“Build Mac one-click installer and independent updates”自动构建应用、检查内置运行环境、验证窗口首次启动，并生成候选发行版。
3. 检查候选版后，在 GitHub **Actions → Publish Mac application update → Run workflow** 中填写版本号。
4. 发布流程核对构建报告、应用文件大小与 SHA256、首次启动记录，随后发布正式版并更新版本检查入口。

用户通过“译研 → 检查更新”发现新版本。更新向导仅替换 `译研.app`，保留独立模型目录及论文工作室。

## 更新接口

| 内容 | 位置 |
|---|---|
| 当前发布设置 | `release-assets/macos-version.json` |
| 客户端版本检查入口 | `https://raw.githubusercontent.com/hengyuwu-dot/yiyan-paperbridge/main/release-assets/macos-update.json` |
| 应用版本清单 | 各 Mac 发行版的 `macos-app.json` |
| 固定模型清单 | 模型发行版的 `macos-models.json` |
| 模型快照校验 | `release-assets/model-snapshots/qwen3-4b.json`、`qwen3-14b.json` |
| 更新发布流程 | `.github/workflows/macos-promote.yml` |

当前接口版本为 `schema: 1`。应用清单包含版本号、最低系统版本、架构、应用归档 URL、字节数、SHA256，以及独立模型清单 URL。安装器只接受本仓库的 HTTPS 发布地址，下载校验通过后才安装。

## 普通更新的边界

应用更新包含界面、翻译与排版程序、字体和运行环境；模型权重另存。更新时不更改模型内容，也不重新下载模型。对确实需要更换权重的版本，应另外发布新的模型资源版本并明确说明下载量。

旧模型发行版保留，应用版本发布流程会检查固定快照；无需每次重新上传 10GB 模型。
