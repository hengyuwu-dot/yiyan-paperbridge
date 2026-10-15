# 译研 1.6 · Windows 完整离线版

安装完成，导入论文即可离线翻译。模型、Python、CPU / NVIDIA CUDA 推理组件、Microsoft WebView2 阅读组件、字体和排版资源均随安装包提供。

## 选择完整版

| 版本 | 模型 | 电脑内存最低 / 建议 | NVIDIA 显存最低 / 建议 | 安装预留空间 |
| --- | --- | --- | --- | --- |
| [4B 标准完整版](https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/tag/v1.6.0-windows-4b-offline) | Qwen3-4B Q4_K_M | 16GB / 16GB+ | 6GB / 8GB+ | 15GB |
| [14B 精译完整版](https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/tag/v1.6.0-windows-14b-offline) | Qwen3-14B Q4_K_M | 24GB / 32GB+ | 12GB / 16GB+ | 30GB |

两种版本均支持 CPU；显存要求用于 NVIDIA GPU 加速。系统为 Windows 10 2004+ 或 Windows 11，Intel / AMD x64、AVX2 处理器。下载所选版本即可，安装后自动选中内置模型。

## 下载与安装

1. 展开下面的 **Assets**，下载同一版本的 **`...-Setup.exe` 和全部 `...-Setup-*.bin`**，放入同一个文件夹。
2. 双击 **`...-Setup.exe`**，按提示安装。
3. 打开桌面的 **译研**，导入 PDF，点击 **开始翻译**。

`.bin` 是安装数据分卷，安装器会自动读取。分卷是完整安装包的一部分，保持原文件名、全部下载即可，无需手工合并。安装后可把安装文件移到备份磁盘，也可以删除以腾出空间。

界面自动使用安装目录中的模型，不会再复制一份到个人数据目录。中文 PDF、中英对照、同步翻阅、缩放、批量队列、专业词表、用时及资源清理均可使用。需要另一种模型时，可在模型窗口联网下载，也可安装另一完整版。

**[完整安装教程](https://github.com/hengyuwu-dot/yiyan-paperbridge/blob/main/docs/WINDOWS_INSTALL.md)** · **[软件首页](https://github.com/hengyuwu-dot/yiyan-paperbridge)**

随附 `BUILD-REPORT.json`、`WINDOWS-OFFLINE-SMOKE-REPORT.json`、首次启动记录与 `SHA256SUMS.txt`，用于查看组件版本、离线 PDF 验证结果和文件完整性。
