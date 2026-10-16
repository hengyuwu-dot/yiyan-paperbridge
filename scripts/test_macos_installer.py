"""Exercise the production Swift downloader with an in-memory HTTP transport."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='macos-installer-checks-') as folder:
    folder=Path(folder)
    source=(ROOT/'desktop/macos-setup/InstallerCore.swift').read_text()
    needle='let config=installerNetworkConfiguration()\n                let queue=OperationQueue()'
    assert source.count(needle)==1
    # Replace only the network transport; manifest, streaming, retry and hash logic remain unchanged.
    (folder/'Core.swift').write_text(source.replace(needle,'let config=fixtureConfiguration()\n                let queue=OperationQueue()'))
    subprocess.run(['xcrun','swiftc','-swift-version','5','-O','-module-cache-path',str(ROOT/'.cache/macos-build/modules'),'-framework','AppKit','-framework','CryptoKit',str(ROOT/'desktop/macos-setup/DownloadNetwork.swift'),str(folder/'Core.swift'),str(ROOT/'tests/macos_installer_tests.swift'),'-o',str(folder/'checks')],check=True)
    subprocess.run([str(folder/'checks')],check=True,timeout=120)
