"""Build two reproducible complete editions from the verified Windows runtime."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from package_windows import copy, digest, download, extract, ROOT

OUTPUT = Path(os.environ.get("PAPERBRIDGE_WINDOWS_OUTPUT", ROOT / "dist/windows/Yiyan"))
CACHE = Path(os.environ.get("PAPERBRIDGE_WINDOWS_CACHE", ROOT / ".cache/windows-offline-build"))
BASE_URL = "https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/download/v1.5.0-windows/Yiyan-1.5.0-Windows-x64.zip"
BASE_SHA256 = "b9dbb035035ef1e315f1841b9791b69a1ed335a2e85910c3d99e2c15a4e6e0fb"
WEBVIEW_VERSION = "155.0.4283.45"
WEBVIEW_URL = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/01b0fbd9-6ea3-4e12-818a-a71f73f3855b/Microsoft.WebView2.FixedVersionRuntime.155.0.4283.45.x64.cab"


def signed_by_microsoft(path):
    # Check the actual downloaded vendor executable, not a filename or URL.
    command = "$s=Get-AuthenticodeSignature -LiteralPath $env:PB_SIGNED_FILE; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Invalid Microsoft signature' }; $s.SignerCertificate.Subject"
    result = subprocess.run(["pwsh", "-NoProfile", "-Command", command], check=True,
                            capture_output=True, text=True, env=dict(os.environ, PB_SIGNED_FILE=str(path)))
    return result.stdout.strip()


def build(profile):
    if sys.platform != "win32":
        raise RuntimeError("Run this builder on Windows x64")
    if OUTPUT.exists():
        raise RuntimeError("Use an empty build output directory")
    CACHE.mkdir(parents=True, exist_ok=True)
    print("Free build volume bytes:", shutil.disk_usage(OUTPUT.anchor).free, flush=True)
    base = CACHE / "windows-runtime-v1.5.0.zip"
    download(BASE_URL, base, BASE_SHA256)
    extract(base, OUTPUT.parent)
    if not OUTPUT.is_dir():
        raise RuntimeError("Runtime archive did not produce the expected Yiyan folder")
    base.unlink()  # The model edition does not need a second copy of the core archive.
    engine = OUTPUT / "Engine"
    for name in ("paperbridge", "scripts", "desktop", "tests", "docs", "release-assets", "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "requirements.txt", "requirements.lock.txt", "requirements.windows.txt"):
        copy(ROOT / name, engine / name)
    copy(ROOT / "docs/WINDOWS_INSTALL.md", OUTPUT / "Windows-安装教程.md")
    subprocess.run(["dotnet", "publish", str(ROOT / "desktop/windows/PaperBridge.csproj"),
                    "-c", "Release", "-r", "win-x64", "--self-contained", "true",
                    "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=true",
                    "-p:Version=1.6.0", "-o", str(OUTPUT)], check=True)
    cab = CACHE / "webview2-x64.cab"
    download(WEBVIEW_URL, cab)
    unpacked = CACHE / "webview2-expanded"
    unpacked.mkdir(exist_ok=True)
    subprocess.run(["expand.exe", str(cab), "-F:*", str(unpacked)], check=True, stdout=subprocess.DEVNULL)
    browsers = list(unpacked.rglob("msedgewebview2.exe"))
    if len(browsers) != 1:
        raise RuntimeError("Unexpected fixed WebView2 package layout")
    webview_signer = signed_by_microsoft(browsers[0])
    browser = OUTPUT / "Runtime/WebView2"
    shutil.move(str(browsers[0].parent), str(browser))
    # Windows 10 fixed runtime renderer permissions required by Microsoft.
    subprocess.run(["icacls", str(browser), "/grant", "*S-1-15-2-2:(OI)(CI)(RX)",
                    "*S-1-15-2-1:(OI)(CI)(RX)"], check=True, stdout=subprocess.DEVNULL)
    vc = OUTPUT / "Runtime/Prerequisites/vc_redist.x64.exe"
    download("https://aka.ms/vc14/vc_redist.x64.exe", vc)
    vc_signer = signed_by_microsoft(vc)
    sys.path.insert(0, str(ROOT))
    from paperbridge.windows_models import manifest
    from paperbridge.windows_download import install_gguf
    entry = manifest()[profile]
    model = OUTPUT / "Models" / ("qwen3-14b" if profile == "precision" else "qwen3-4b")
    install_gguf(print, model)
    for filename in ("LICENSE", "README.md"):
        download(f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{filename}", model / filename)
    report = json.loads((OUTPUT / "BUILD-REPORT.json").read_text(encoding="utf-8"))
    report.update(version="1.6.0", edition=profile, models=[entry], offline_first_launch=True,
                  source_commit=os.environ.get("GITHUB_SHA"), base_runtime_sha256=BASE_SHA256,
                  webview={"version": WEBVIEW_VERSION, "url": WEBVIEW_URL, "sha256": digest(cab), "signer": webview_signer},
                  vc_redist={"sha256": digest(vc), "signer": vc_signer})
    (OUTPUT / "BUILD-REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(OUTPUT / "BUILD-REPORT.json", CACHE / "BUILD-REPORT.json")
    cab.unlink()
    print("Complete offline edition assembled:", profile, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=("standard", "precision"))
    build(parser.parse_args().profile)
