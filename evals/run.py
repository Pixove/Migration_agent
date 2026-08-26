from __future__ import annotations

import json

from evals.migration_evals import run_migration_evals
from evals.retrieval_evals import run_retrieval_evals


def main() -> int:
    report = {
        "retrieval": run_retrieval_evals(),
        "migration": run_migration_evals(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
