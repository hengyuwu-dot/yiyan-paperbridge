# 译研 Windows 安装与使用教程

译研把 SCI 英文论文翻译成专业中文，支持原文／译文左右对照、同步翻阅、专业词表与 PDF 导出。Windows 版提供 **4B 标准**和 **14B 精译**两种本地模型，可分别下载，也可以同时安装。

[下载 Windows 版](https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/tag/v1.5.0-windows) · [返回软件首页](../README.md)

## 1. 选择适合电脑的模型

| 配置 | 4B 标准 | 14B 精译 |
| --- | --- | --- |
| 操作系统 | Windows 10 2004+ / Windows 11，64 位 x64 | Windows 10 2004+ / Windows 11，64 位 x64 |
| 处理器 | 支持 AVX2 的 Intel / AMD 64 位处理器，4 核起 | 支持 AVX2 的 Intel / AMD 64 位处理器，6 核起 |
| 电脑内存最低配置 | **16GB RAM** | **24GB RAM** |
| 电脑内存建议配置 | **16GB 或更多** | **32GB 或更多** |
| 完整 GPU 加速的显存配置 | NVIDIA **6GB 起，建议 8GB+** | NVIDIA **12GB 起，建议 16GB+** |
| CPU 运行 | 支持，使用上面的电脑内存配置 | 支持，使用上面的电脑内存配置 |
| 模型下载大小 | **约 2.50GB** | **约 9.00GB** |
| 安装及使用预留磁盘空间 | **15GB** | **30GB** |

同时安装两个模型建议预留 **40GB** 磁盘空间。应用及论文也需要空间，模型文件大小和运行内存是不同的数字。

表中的容量是本软件按 **Qwen3 Q4_K_M、8192 token 上下文、单任务、FP16 KV 缓存**预留推理与排版开销后的配置预算。显存指单张 NVIDIA 显卡可用的独立显存；运行大型游戏或其他模型时，应先释放相应资源。这里的最低配置用于选择模型，实际占用会随论文内容和后台程序变化。

**选哪个：** 日常阅读和较低配置先选 4B；希望更充分处理长句、复杂关系及专业表达时选择 14B。两种模型沿用相同的专业术语、数值与公式检查和排版流程。

**是否一定要独立显卡：** 两种模型都支持 CPU。显卡用于加速；软件检测到可用显存充足的 NVIDIA 显卡时优先使用 GPU，其他情况使用 CPU。AMD、Intel 显卡电脑可使用 CPU 模式。

NVIDIA 加速组件使用 CUDA 12.4，建议安装 **551.61 或更新版本的 NVIDIA 驱动**；应用内附所需推理运行库。依据：[NVIDIA CUDA 12.4 驱动说明](https://docs.nvidia.com/cuda/archive/12.4.0/cuda-toolkit-release-notes/index.html)。

## 2. 下载并安装

1. 打开上面的 Windows 下载页面，展开 **Assets**。
2. 下载 **`Yiyan-1.5.0-Windows-x64-Setup.exe`**。
3. 双击安装，选择安装位置，按提示完成。
4. 从桌面或开始菜单打开 **译研**。

安装器默认安装到当前用户的应用目录，并创建桌面和开始菜单入口。

如果使用免安装版，下载 **`Yiyan-1.5.0-Windows-x64.zip`**，在资源管理器中选择“全部解压”，打开解压后的 `Yiyan` 文件夹，双击 **`Yiyan.exe`**。升级免安装版时，把新版本解压到另一个文件夹后打开即可。

阅读窗口使用 Microsoft Edge WebView2。Windows 11 通常已有该组件；若软件提示需要准备阅读组件，前往 [Microsoft 官方 WebView2 下载页](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) 安装 **Evergreen Standalone Installer（x64）**，完成后再打开译研。[Microsoft 运行时说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。

推理组件还使用 Microsoft Visual C++ v14 x64 运行库。若打开模型时提示缺少 `MSVCP140.dll` 或 `VCRUNTIME140.dll`，安装 [Microsoft 官方 x64 运行库](https://aka.ms/vc14/vc_redist.x64.exe) 后重新打开译研。[Microsoft 运行库说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。

## 3. 首次选择 4B 或 14B

1. 点击右上角 **准备本地模型**。
2. 在模型窗口查看本机内存、NVIDIA 显存以及两种模式的配置表。
3. 点击 **下载 4B 标准模型（约 2.50GB）**，或 **下载 14B 精译模型（约 9.00GB）**。
4. 等待下载和完整性校验完成，显示“本地模型已就绪”后导入论文。

首次下载需要联网获取 Qwen 官方模型；下载完成后的翻译在本机运行。已安装一种模型后，可以随时再下载另一种。下载中断时再次点击下载，可继续获取剩余内容。

## 4. 翻译论文并切换模型

1. 点击 **选择论文 PDF** 或拖入英文论文；可以一次放入多篇。
2. 展开 **翻译设置 → 更多设置 → 本地模型**，选择 **标准 · 4B** 或 **精译 · 14B**。
3. 选择学科、翻译页码、术语及译后复核设置，点击 **开始翻译**。
4. 完成后在左右两栏对照阅读，同步滚动并独立或联动放大。
5. 在 **导出** 中选择中文 PDF、原译交替双语 PDF 或完整译文记录。

适用正文可以选择、复制的英文 PDF；单篇 80MB 以内、300 页以内。4B 与 14B 按论文任务选择，依次处理队列；切换时会释放上一任务的模型资源。

## 5. 专业词表、内存与存储

- 在 **专业术语表** 中选择学科词库，并添加 `English term = 中文译名`。
- 在右上角 **内存 / 存储** 中查看占用，选择清理临时文件、旧自动备份、下载缓存或日志。
- 开启 **完成后自动清理**，任务完成后整理临时资源；推理进程结束后释放内存和显存。

论文、译稿、模型和设置保存在 **`%LOCALAPPDATA%\PaperBridge`**；应用文件与个人数据分开存放。

## 常见操作

| 情况 | 处理方法 |
| --- | --- |
| 想先体验、电脑内存 16GB | 选择 4B 标准模型 |
| 14B 下载或加载占用较大 | 按配置表释放内存，或在任务设置中切换到已安装的 4B |
| 有 NVIDIA 显卡但显示 CPU | 关闭其他占用显存的程序，并更新 NVIDIA 驱动后重新开始任务 |
| 下载到一半中断 | 保留下载缓存，再次点击对应模型的下载按钮 |
| 想更换安装目录 | 安装到新目录，重新打开译研；个人数据继续从上面的用户目录读取 |
| 想查看本地运行记录 | 打开 `%LOCALAPPDATA%\PaperBridge\tmp`，以及对应论文任务中的 `full-worker.log` |

## 模型与开源来源

Windows 版使用 Qwen 官方 [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF) 与 [Qwen3-14B-GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF) 的 **Q4_K_M** 文件，由 [llama.cpp](https://github.com/ggml-org/llama.cpp) 在本机运行。下载固定到具体版本，并在启用前校验 SHA256。

应用源码使用 AGPL-3.0；Qwen 模型使用 Apache-2.0；llama.cpp 使用 MIT。对应源码与依赖许可随应用提供，见 [第三方声明](../THIRD_PARTY_NOTICES.md)。
