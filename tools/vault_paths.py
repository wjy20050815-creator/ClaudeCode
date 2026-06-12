"""vault.paths.env 解析器 — vault 路径的唯一来源。

用法（agent 内）：
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from vault_paths import vault_path
    VAULT = vault_path("VAULT_ROOT")
"""

import re
from functools import lru_cache
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "vault.paths.env"


@lru_cache(maxsize=1)
def load() -> dict[str, str]:
    vals: dict[str, str] = {}
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        val = raw.strip().strip('"').strip("'")
        val = re.sub(r"\$\{(\w+)\}", lambda m: vals.get(m.group(1), ""), val)
        vals[key.strip()] = val
    return vals


def vault_path(key: str) -> Path:
    return Path(load()[key])
