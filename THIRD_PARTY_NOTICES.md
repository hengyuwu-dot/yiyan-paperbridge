# 第三方许可与分发说明

译研 PaperBridge 的应用源码按 GNU Affero General Public License v3.0（AGPL-3.0）发布，完整文本见 LICENSE。
本目录的许可声明不改变第三方组件的许可，也不覆盖用户导入的论文或输出文稿。

主要组件：

| 组件 | 许可 | 上游 |
| --- | --- | --- |
| BabelDOC 0.6.4 | AGPL-3.0 | https://github.com/funstory-ai/BabelDOC/tree/v0.6.4 |
| PyMuPDF 1.27.2.3 / MuPDF | AGPL-3.0，另有商业许可 | https://github.com/pymupdf/PyMuPDF |
| MLX / MLX LM | MIT | https://github.com/ml-explore/mlx / https://github.com/ml-explore/mlx-lm |
| Python 3.12 | PSF 及随源代码附带的组件许可 | https://www.python.org/ |
| Qwen3 模型 | Apache-2.0 | https://huggingface.co/Qwen |
| llama.cpp（Windows CPU / CUDA） | MIT 及随二进制附带的运行库许可 | https://github.com/ggml-org/llama.cpp |
| Microsoft .NET / WebView2 SDK | MIT / Microsoft 随组件附带的许可 | https://github.com/dotnet/runtime / https://www.nuget.org/packages/Microsoft.Web.WebView2 |
| Microsoft WebView2 固定运行时 / Visual C++ Redistributable | Microsoft 运行时分发条款，保留官方文件与许可 | https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution / https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist |

完整安装依赖、版本、元数据与随包许可由 `scripts/prepare_release_licenses.py` 收集，保存在 `release-assets/licenses/` 和 `DEPENDENCIES.json`。
运行时不修改 CPython 源码；打包时只重定位文件、移除基础发行版中不需要的额外 Python 包，并加入本应用所需依赖。原始第三方许可、声明及组件内置许可文件保留。
发布前应核对基础 Python 发行版的再分发材料，以及所选依赖的完整许可与对应源码要求；脚本不是法律合规认证。

## GitHub 发布范围

- 发布应用源码，保留 LICENSE、第三方声明及各组件的原始版权信息。
- 分享安装包时，同时提供本版本的源码及需要提供的第三方对应源码、构建信息，遵守 AGPL 的分发要求。
- 本地整理和打包不等于已经公开上传；请在确定 GitHub 仓库后执行发布。
- 轻量安装包在首次使用时从原上游下载模型、排版模型及字体；完整离线包内置校验过的原始公开资源，并保留权重许可、字体版权和原始资源说明。两种包都不包含用户论文或任务数据库。
- 不上传个人论文、未发表稿件、译稿、任务数据、缓存、日志、个人路径、API 密钥或整个虚拟环境到源码仓库。
- 商业销售或闭源分发需要另行评估依赖授权；尤其不能把 AGPL 依赖简单改标为 MIT。

许可规则参考：[PyMuPDF 官方许可](https://pymupdf.io/licensing)、[BabelDOC 许可](https://github.com/funstory-ai/BabelDOC/blob/v0.6.4/LICENSE)。

Windows 完整离线版按固定版本读取 Qwen 官方 GGUF 权重，随模型提供上游 LICENSE 与 README。基础 Python、PDF 依赖及其对应源码沿用校验过的 1.5.0 Windows 运行包，新增应用源码随包更新。Microsoft WebView2 固定运行时从官方分发地址获取，校验实际执行文件的 Microsoft 签名，完整保留运行时目录；Visual C++ 官方安装器原样附带。构建记录包含模型、基础运行包和 Microsoft 组件的 SHA256、版本及签名主体。
