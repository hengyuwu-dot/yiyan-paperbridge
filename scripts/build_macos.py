"""Build the local Mac desktop app with Apple's installed toolchain, offline."""
import os
import argparse
import plistlib
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".cache" / "macos-build"
APP = ROOT / "dist" / "译研.app"


def main():
    global APP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", action="store_true", help="Build the shell for the redistributable bundled runtime")
    parser.add_argument("--output", type=Path, help="Alternative app output path")
    parser.add_argument("--offline-models", action="store_true")
    args = parser.parse_args()
    if args.portable:
        APP = ROOT / "dist" / "release" / "译研.app"
    if args.output:
        APP = args.output.resolve()
    for directory in (BUILD, APP / "Contents/MacOS", APP / "Contents/Resources"):
        directory.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, CLANG_MODULE_CACHE_PATH=str(BUILD / "modules"),
                       SWIFT_MODULECACHE_PATH=str(BUILD / "modules"))

    def run(*args):
        subprocess.run(args, check=True, cwd=ROOT, env=environment)

    run("xcrun", "swiftc", "-swift-version", "5", "-O", "-target", "arm64-apple-macosx12.0",
        "-module-cache-path", str(BUILD / "modules"), "-framework", "AppKit", "-framework", "WebKit",
        str(ROOT / "desktop/macos/main.swift"), "-o", str(APP / "Contents/MacOS/PaperBridge"))
    icon = APP / "Contents/Resources/AppIcon.icns"
    icon_source = ROOT / "desktop/macos/MakeIcon.swift"
    supplied_icon = ROOT / "desktop/macos/AppIcon.icns"
    if supplied_icon.exists():
        shutil.copy2(supplied_icon, icon)
    elif not icon.exists() or icon.stat().st_mtime < icon_source.stat().st_mtime:
        run("xcrun", "swiftc", "-O", "-module-cache-path", str(BUILD / "modules"), "-framework", "AppKit",
            str(icon_source), "-o", str(BUILD / "MakeIcon"))
        run(str(BUILD / "MakeIcon"), str(BUILD / "AppIcon.iconset"))
        run("iconutil", "-c", "icns", str(BUILD / "AppIcon.iconset"), "-o", str(icon))
    info = {
        "CFBundleName": "译研", "CFBundleDisplayName": "译研", "CFBundleIdentifier": "local.paperbridge.desktop",
        "CFBundleExecutable": "PaperBridge", "CFBundlePackageType": "APPL", "CFBundleIconFile": "AppIcon",
        "CFBundleShortVersionString": "1.4.0" if args.portable else "1.3.0", "CFBundleVersion": "14" if args.portable else "13",
        "LSMinimumSystemVersion": "26.2" if args.portable else "12.0",
        "NSHighResolutionCapable": True, "NSSupportsAutomaticGraphicsSwitching": True,
        "NSPrincipalClass": "NSApplication", "CFBundleDevelopmentRegion": "zh_CN",
        "NSDocumentsFolderUsageDescription": "译研需要读取“文稿”中的本地翻译环境、模型和论文，并保存译文；文件仅在这台 Mac 上处理。",
        "NSDownloadsFolderUsageDescription": "用于导入你选择的英文论文，以及保存导出的中文与双语 PDF。",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "CFBundleDocumentTypes": [{"CFBundleTypeName": "PDF 论文", "CFBundleTypeRole": "Viewer",
                                   "LSHandlerRank": "Alternate", "LSItemContentTypes": ["com.adobe.pdf"]}],
    }
    if args.portable:
        info["CFBundleIdentifier"] = "org.paperbridge.yiyan"
    if args.offline_models:
        info["CFBundleIdentifier"] = "org.paperbridge.yiyan.offline"
    (APP / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    project = {"Portable": True} if args.portable else {"ProjectDirectory": str(ROOT)}
    if args.offline_models:
        project["BundledModels"] = True
    (APP / "Contents/Resources/Project.plist").write_bytes(plistlib.dumps(project))
    run("codesign", "--force", "--deep", "--sign", "-", str(APP))
    run("codesign", "--verify", "--deep", "--strict", str(APP))
    print(f"已生成: {APP}")
    print("发行版外壳已生成；请运行 package_macos.py 完成内置环境与安装包。" if args.portable else
          "这是复用本机环境的桌面版；模型、论文和 Python 环境保留在原软件目录。")


if __name__ == "__main__":
    main()
