from pathlib import Path

def generate_qrc(asset_dir, output_file):
    asset_path = Path(asset_dir)

    with open(output_file, 'w') as f:
        f.write('<RCC>\n')
        f.write('    <qresource prefix="/">\n')

        for file_path in asset_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(asset_path.parent)
                f.write(f'        <file>{relative_path.as_posix()}</file>\n')

        f.write('    </qresource>\n')
        f.write('</RCC>\n')

if __name__ == "__main__":
    assert Path("pyproject.toml").exists(), "Must be run from project root"
    generate_qrc('./assets', './resources.qrc')