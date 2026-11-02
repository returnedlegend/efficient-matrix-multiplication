"""Package, verify, or restore the complete historical research outputs."""
import argparse
import lzma
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts/research-results-20261102.tar.xz'
MANIFEST = ROOT / 'artifacts/research-results-20261102.manifest.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def create():
    files = sorted(p for folder in (ROOT/'artifacts', ROOT/'research/campaign')
                   for p in folder.rglob('*') if p.is_file()
                   and p not in (ARCHIVE, MANIFEST)
                   and not p.name.startswith('research-results-20261102.')
                   and '__pycache__' not in p.parts and not p.name.endswith('.tmp'))
    records = {}
    with ARCHIVE.open('wb') as output, lzma.LZMAFile(output, mode='wb', preset=6) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as archive:
            for path in files:
                if path.is_symlink():
                    raise ValueError(f'symlink is not a result file: {path}')
                name = path.relative_to(ROOT).as_posix()
                info = tarfile.TarInfo(name)
                info.size = path.stat().st_size
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                with path.open('rb') as source:
                    archive.addfile(info, source)
                records[name] = {'size': info.size, 'sha256': digest(path)}
    manifest = {'archive': ARCHIVE.relative_to(ROOT).as_posix(), 'sha256': digest(ARCHIVE),
                'compressed_bytes': ARCHIVE.stat().st_size,
                'uncompressed_bytes': sum(v['size'] for v in records.values()),
                'files': records}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}))


def verify_or_restore(restore=False):
    manifest = json.loads(MANIFEST.read_text())
    if digest(ARCHIVE) != manifest['sha256']:
        raise ValueError('archive checksum mismatch')
    if restore:
        for name, record in manifest['files'].items():
            path = ROOT / name
            if (not name.startswith(('artifacts/', 'research/campaign/'))
                    or not path.resolve().is_relative_to(ROOT)):
                raise ValueError(f'path escapes checkout: {name}')
            if path.exists() and (not path.is_file() or digest(path) != record['sha256']):
                raise ValueError(f'preserving conflicting local file: {name}')
    seen = set()
    with tarfile.open(ARCHIVE, 'r:*') as archive:
        for member in archive:
            name = member.name
            path = ROOT / name
            record = manifest['files'].get(name)
            if (not record or name in seen or not member.isfile()
                    or not name.startswith(('artifacts/', 'research/campaign/'))
                    or not path.resolve().is_relative_to(ROOT) or member.size != record['size']):
                raise ValueError(f'invalid archive member: {name}')
            seen.add(name)
            source = archive.extractfile(member)
            h = hashlib.sha256()
            destination = None
            temporary = path.with_name(path.name + '.restore.tmp')
            if restore and not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                destination = temporary.open('xb')
            try:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    h.update(chunk)
                    if destination:
                        destination.write(chunk)
            finally:
                if destination:
                    destination.close()
            if h.hexdigest() != record['sha256']:
                temporary.unlink(missing_ok=True)
                raise ValueError(f'result checksum mismatch: {name}')
            if destination:
                if path.exists():
                    temporary.unlink()
                    raise ValueError(f'local file appeared during restore: {name}')
                temporary.rename(path)
                path.chmod(member.mode)
    if seen != set(manifest['files']):
        raise ValueError('archive is missing manifest members')
    print(json.dumps({'verified_files': len(seen), 'restored': restore,
                      'sha256': manifest['sha256']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify', 'restore'))
    args = parser.parse_args()
    create() if args.action == 'create' else verify_or_restore(args.action == 'restore')
