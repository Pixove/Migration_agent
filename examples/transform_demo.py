from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from migration.py2to3 import transform_python2_to_3


def main() -> None:
    default_source = ROOT / "examples" / "legacy_demo" / "python2_demo.py"
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source
    text = source.read_text(encoding="utf-8-sig")
    migrated = transform_python2_to_3(text)

    print(f"===== Before ({source}) =====")
    print(text)
    print("===== After =====")
    print(migrated)


if __name__ == "__main__":
    main()
