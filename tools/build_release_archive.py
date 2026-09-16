"""Build deterministic, source-only ZIP packages for GitHub Releases."""
import argparse
import json
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026-09-16-r5'
ARCHIVE_ROOT = 'soil-city-county-chronicle'
FORBIDDEN_SUFFIXES = {'.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.7z', '.rar',
                      '.gdb', '.gpkg', '.shp', '.dbf', '.shx', '.tif', '.tiff'}


def source_root(target):
    if target == 'canonical':
        return ROOT
    if target == 'workbuddy':
        return ROOT / 'platforms' / 'workbuddy' / 'soil-city-county-chronicle'
    raise ValueError(f'unknown target: {target}')


def selected_files(target):
    base = source_root(target)
    if not base.is_dir():
        raise ValueError(f'source directory is missing: {base}')
    if target == 'canonical':
        candidates = [base / 'SKILL.md', base / 'agents', base / 'assets', base / 'references', base / 'scripts']
    else:
        candidates = [base / 'SKILL.md', base / 'BUILD-METADATA.json', base / 'references', base / 'scripts', base / 'templates']
    files = []
    for candidate in candidates:
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(path for path in candidate.rglob('*') if path.is_file())
        else:
            raise ValueError(f'required package input is missing: {candidate}')
    result = []
    for path in sorted(files, key=lambda item: item.as_posix()):
        if '__pycache__' in path.parts or path.suffix.lower() in {'.pyc', '.pyo'}:
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError(f'forbidden source artifact: {path}')
        resolved = path.resolve()
        if base.resolve() not in resolved.parents and resolved != base.resolve():
            raise ValueError(f'package input escapes source root: {path}')
        result.append((path, path.relative_to(base)))
    return result


def zip_info(name):
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build(target, output):
    output = Path(output)
    if output.exists():
        raise ValueError(f'refusing to overwrite existing archive: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    files = selected_files(target)
    metadata = json.dumps({
        'package': 'soil-city-county-chronicle',
        'version': VERSION,
        'target': target,
        'archive_root': ARCHIVE_ROOT,
        'contains_real_project_data': False,
        'source_repository': 'https://github.com/SoMic520/soil-city-county-chronicle-skill',
    }, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in files:
            member = PurePosixPath(ARCHIVE_ROOT, *relative.parts).as_posix()
            archive.writestr(zip_info(member), path.read_bytes())
        archive.writestr(zip_info(f'{ARCHIVE_ROOT}/PACKAGE-METADATA.json'), metadata)
    verify(output, target)
    return {'output': str(output.resolve()), 'target': target, 'files': len(files) + 1, 'bytes': output.stat().st_size}


def verify(path, target):
    path = Path(path)
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('archive contains duplicate paths')
        required = {f'{ARCHIVE_ROOT}/SKILL.md', f'{ARCHIVE_ROOT}/PACKAGE-METADATA.json'}
        if target == 'canonical':
            required.add(f'{ARCHIVE_ROOT}/agents/openai.yaml')
        else:
            required.add(f'{ARCHIVE_ROOT}/BUILD-METADATA.json')
        if not required <= set(names):
            raise ValueError(f'archive missing required files: {sorted(required - set(names))}')
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or '..' in member.parts or not member.parts or member.parts[0] != ARCHIVE_ROOT:
                raise ValueError(f'unsafe archive member: {name}')
            if Path(member.name).suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError(f'forbidden nested archive artifact: {name}')
        metadata = json.loads(archive.read(f'{ARCHIVE_ROOT}/PACKAGE-METADATA.json'))
        if metadata.get('target') != target or metadata.get('contains_real_project_data') is not False:
            raise ValueError('package metadata does not match requested target')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=('canonical', 'workbuddy'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args.target, args.output), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
