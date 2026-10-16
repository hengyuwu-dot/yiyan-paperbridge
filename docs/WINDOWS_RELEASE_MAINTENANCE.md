# Windows 应用更新与发布

Windows 和 Mac 使用同一个源码仓库，分别构建各自的安装器和更新包。Windows 普通应用更新继续使用已安装的模型与运行环境。

## 发布下一版本

1. 修改源码，并提升 `release-assets/windows-version.json` 的 `version`。
2. 推送到 main，自动运行 **Build and verify Windows model-preserving updates**。
3. 流程编译桌面应用、更新工具和一键安装器，执行下载与事务回退检查，并发布候选安装资源。
4. Windows 验证机使用真实 4B 模型安装软件，通过软件菜单触发一次更新，核对模型、测试论文、设置和运行环境的校验值；随后验证离线启动和 PDF 导出。
5. 验证通过后自动发布正式版，同时更新 `release-assets/windows-update.json`。已有用户在“软件 → 检查更新”中获取新版本。

模型资源继续使用已发布的固定版本，不随普通应用更新重新下载或上传。

## 更新接口

| 内容 | 位置 |
|---|---|
| 待发布版本与运行环境策略 | `release-assets/windows-version.json` |
| 稳定版查询入口 | `https://raw.githubusercontent.com/hengyuwu-dot/yiyan-paperbridge/main/release-assets/windows-update.json` |
| CDN 查询备用入口 | `https://cdn.jsdelivr.net/gh/hengyuwu-dot/yiyan-paperbridge@main/release-assets/windows-update.json` |
| 每版不可变清单 | 对应发行版的 `windows-app.json` |
| 发布与验证流程 | `.github/workflows/windows-update.yml` |

接口 `schema: 1` 包含版本号、平台、最低可升级版本、应用包 URL、字节数、SHA256、解压大小和替换组件清单。客户端验证清单后下载，校验完整文件再替换应用。

## 应用、模型和资料

普通更新包只含桌面程序、更新工具和翻译程序代码。`Models`、个人论文、译稿和设置均不属于可替换组件；原有字体、排版缓存、许可证与运行环境对应源码继续保留。更新失败会恢复已经替换的应用组件。

当前普通更新的 `include_runtime` 为 `false`。如果以后改动 Python、llama.cpp、WebView2 等依赖，应先准备经过校验的 Windows 运行环境，将该值设为 `true`，并在构建任务中提供 `PAPERBRIDGE_WINDOWS_RUNTIME_SOURCE`，同时验证对应依赖、字体、许可和源码，并把运行环境保留检查调整为核对新版运行环境清单。模型权重仍独立保留。

首次从旧版升级可运行新版一键安装器，选择原安装位置；检测到完整模型后直接更新应用。也可单独运行 `Yiyan-Updater.exe` 更新默认安装位置；自定义位置通过新版安装器选择。

## 1.9.0 验证记录

[Windows 完整验证流程](https://github.com/hengyuwu-dot/yiyan-paperbridge/actions/runs/38870306135)已通过：新安装器完成 4B 安装，通过原生菜单升级受控旧启动器，核对 4 个模型相关文件、3 个测试资料文件和 12,685 个运行环境文件。保留原模型后，完成断网启动及 CPU 离线翻译、中文与双语 PDF 导出。18 项更新事务检查覆盖 4B / 14B 模型目录保留、下载校验和失败回退。

[模型与资料保留报告](https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/download/v1.9.0-windows-update/WINDOWS-UPDATE-PRESERVATION.json) · [离线 PDF 导出报告](https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/download/v1.9.0-windows-update/WINDOWS-OFFLINE-SMOKE-REPORT.json)
