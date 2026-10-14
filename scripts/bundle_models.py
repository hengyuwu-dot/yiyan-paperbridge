"""Copy only hash-verified public model weights and layout resources.

Does not access documents, task databases, translation caches or user settings.
The installed model precision and files remain unchanged.
"""
import hashlib
import json
from pathlib import Path
import shutil


def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def bundle_models(root, resources):
    root, resources = Path(root), Path(resources)
    records = []
    for name in ['qwen3-14b', 'qwen3-4b']:
        source = root / 'models' / name
        metadata = json.loads((source / 'installation.json').read_text())
        target = resources / 'Models' / name
        target.mkdir(parents=True)
        size = 0
        for item in metadata['files']:
            filename = item['file']
            if Path(filename).name != filename or not filename.endswith(('.safetensors', '.json', '.txt', '.md', '.model')) and filename != 'LICENSE':
                raise RuntimeError('Unexpected model snapshot file')
            path = source / filename
            if path.is_symlink() or path.stat().st_size != item['size'] or digest(path) != item['sha256']:
                raise RuntimeError(f'Installed model checksum failed: {name}/{filename}')
            shutil.copy2(path, target / filename)
            size += item['size']
        shutil.copy2(source / 'installation.json', target / 'installation.json')
        records.append({'directory': name, 'repo': metadata['repo'], 'revision': metadata['revision'],
                        'bytes': size, 'quantization_bits': json.loads((target / 'config.json').read_text())['quantization']['bits'],
                        'snapshot_sha256_verified': True})
        print(f'Bundled unchanged {name}: {size / 1e9:.2f} GB, SHA256 verified', flush=True)
    source = root / '.cache/babeldoc'
    metadata = json.loads((source / 'ready.json').read_text())
    target = resources / 'LayoutAssets'
    target.mkdir()
    for category in ['fonts', 'models', 'tiktoken', 'cmap']:
        (target / category).mkdir()
        for item in metadata[category]:
            name = item['name']
            if Path(name).name != name:
                raise RuntimeError('Unexpected layout resource path')
            path = source / category / name
            if path.is_symlink() or digest(path, 'sha3_256') != item['sha3_256']:
                raise RuntimeError(f'Installed layout checksum failed: {category}/{name}')
            shutil.copy2(path, target / category / name)
    shutil.copy2(source / 'ready.json', target / 'ready.json')
    (resources / 'BUNDLED_MODELS.json').write_text(json.dumps({'models': records, 'layout_sha3_verified': True}, indent=2))
    print('Bundled verified fonts, layout model, CMaps and tokenizer resources; no private caches copied', flush=True)
