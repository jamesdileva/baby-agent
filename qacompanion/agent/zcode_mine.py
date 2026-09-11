"""S62 ZCode session mining: the same SST-family schema as opencode
(`~/.zcode/cli/db/db.sqlite` — session / message / part with JSON data
blobs and the same part vocabulary, plus step-start / step-finish /
timeline extras the base miner ignores naturally), so the adapter is a
thin subclass: source tag, tags, and the default DB path change.

Corpus reality (2026-09-11): exactly 1 session — this adapter earns its
keep as the human uses ZCode. Session ids (`sess_…`) cannot collide
with opencode ids. The richer rollout-JSONL source
(`~/.zcode/cli/rollout/model-io-<sess>.jsonl`) is a documented future
extension; the DB is the stable contract.
"""

from pathlib import Path

from .opencode_mine import OpencodeMiner

DEFAULT_ZCODE_DB = (Path.home() / ".zcode" / "cli" / "db" / "db.sqlite")


class ZcodeMiner(OpencodeMiner):
    """Read-only miner over the ZCode CLI SQLite session store."""

    SOURCE_NAME = "zcode"

    def __init__(self, db_path=None):
        super().__init__(db_path or DEFAULT_ZCODE_DB)
