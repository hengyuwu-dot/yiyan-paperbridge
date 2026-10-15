# 译研 1.5 · Windows 版

在 Windows 上阅读 SCI 英文论文：本地全文翻译、专业术语、中英对照、同步缩放与 PDF 导出。

## 下载与安装

下载 **Yiyan-1.5.0-Windows-x64-Setup.exe**，双击安装后从桌面打开“译研”。也可下载 ZIP 免安装版，全部解压后打开 Yiyan.exe。

首次启动，在模型窗口选择下载 **4B 标准（约 2.50GB）** 或 **14B 精译（约 9.00GB）**；两种模型可以同时安装，按论文任务切换。下载完成后，翻译在本机离线进行。

## 配置要求

| 配置 | 4B 标准 | 14B 精译 |
| --- | --- | --- |
| 系统 | Windows 10 2004+ / 11，x64 | Windows 10 2004+ / 11，x64 |
| 内存最低 / 建议 | **16GB / 16GB+** | **24GB / 32GB+** |
| NVIDIA 显存最低 / 建议 | **6GB / 8GB+** | **12GB / 16GB+** |
| 安装及使用预留空间 | **15GB** | **30GB** |

两种模型均支持 CPU；显存要求用于完整 GPU 加速，按 Q4_K_M、8192 上下文与单任务预留开销。同时安装两种模型建议留 40GB 磁盘空间，NVIDIA 驱动建议 551.61+。

[完整 Windows 安装与使用教程](https://github.com/hengyuwu-dot/yiyan-paperbridge/blob/main/docs/WINDOWS_INSTALL.md) · [软件首页与界面展示](https://github.com/hengyuwu-dot/yiyan-paperbridge)

安装包内附 Python、CPU/CUDA 推理组件、排版资源、应用源码和第三方许可。Qwen 模型按需下载并校验 SHA256。发行附件提供 Windows 实际运行生成的界面截图与 4B PDF 翻译检查记录。
