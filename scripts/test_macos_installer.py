"""Exercise the production Swift downloader with an in-memory HTTP transport."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='macos-installer-checks-') as folder:
    folder=Path(folder)
    source=(ROOT/'desktop/macos-setup/InstallerCore.swift').read_text()
    needle='let config=URLSessionConfiguration.ephemeral;config.timeoutIntervalForResource=24*3600'
    assert source.count(needle)==1
    # Replace only the network transport; manifest, streaming, retry and hash logic remain unchanged.
    (folder/'Core.swift').write_text(source.replace(needle,'let config=fixtureConfiguration();config.timeoutIntervalForResource=24*3600'))
    subprocess.run(['xcrun','swiftc','-swift-version','5','-O','-module-cache-path',str(ROOT/'.cache/macos-build/modules'),'-framework','AppKit','-framework','CryptoKit',str(folder/'Core.swift'),str(ROOT/'tests/macos_installer_tests.swift'),'-o',str(folder/'checks')],check=True)
    subprocess.run([str(folder/'checks')],check=True,timeout=120)
