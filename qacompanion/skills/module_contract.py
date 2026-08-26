"""S17 module-contract skills: guarded Python skill interface.

For capabilities too complex for declarative rules, Python modules
satisfying a fixed SkillBase interface are auto-discovered from
skills/modules/. Guardrails:

- Module must define a class inheriting SkillBase.
- Module must have MODULE_meta dict with name, version, description.
- Module is discovered only; never auto-executed unreviewed.
- Discovery validates the interface; broken modules are rejected.
"""

import importlib
import importlib.util
import sys
from pathlib import Path


class SkillBase:
    """Abstract base for module-contract skills.

    Subclasses must implement:
      - name: str property (unique identifier)
      - description: str property (human-readable summary)
      - run(**kwargs) -> dict (main entry point)
    """

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    def run(self, **kwargs) -> dict:
        raise NotImplementedError


REQUIRED_META = {"name", "version", "description"}


def _validate_meta(module):
    """Check MODULE_meta exists and has required fields. Returns meta dict."""
    meta = getattr(module, "MODULE_meta", None)
    if not isinstance(meta, dict):
        raise ContractError(
            f"module {module.__name__!r} missing MODULE_meta dict"
        )
    missing = REQUIRED_META - set(meta.keys())
    if missing:
        raise ContractError(
            f"module {module.__name__!r} MODULE_meta missing: "
            + ", ".join(sorted(missing))
        )
    for key in REQUIRED_META:
        val = meta[key]
        if not isinstance(val, str) or not val.strip():
            raise ContractError(
                f"module {module.__name__!r} MODULE_meta {key!r} must be non-empty string"
            )
    return meta


def _validate_skill_class(cls, module_name):
    """Check that cls is a concrete SkillBase subclass."""
    if not isinstance(cls, type):
        raise ContractError(
            f"module {module_name!r}: skill entry is not a class"
        )
    if not issubclass(cls, SkillBase):
        raise ContractError(
            f"module {module_name!r}: skill class {cls.__name__!r} "
            f"does not inherit SkillBase"
        )
    # Check it's not the base itself
    if cls is SkillBase:
        raise ContractError(
            f"module {module_name!r}: skill entry is SkillBase itself"
        )
    # Check required methods are overridden (not just the base raises)
    for method_name in ("name", "description", "run"):
        method = getattr(cls, method_name)
        if method is getattr(SkillBase, method_name):
            raise ContractError(
                f"module {module_name!r}: skill class {cls.__name__!r} "
                f"does not override {method_name}"
            )


class ContractError(Exception):
    """Raised when a module fails the skill contract validation."""


class ModuleSkill:
    """Wrapper around a discovered module-contract skill."""

    def __init__(self, meta, skill_cls, module):
        self.meta = meta
        self.skill_cls = skill_cls
        self.module = module
        self._instance = None

    @property
    def name(self):
        return self.meta["name"]

    @property
    def description(self):
        return self.meta["description"]

    @property
    def version(self):
        return self.meta["version"]

    def get_instance(self):
        """Return a lazily-created instance of the skill class."""
        if self._instance is None:
            self._instance = self.skill_cls()
        return self._instance

    def run(self, **kwargs):
        return self.get_instance().run(**kwargs)


def discover_modules(modules_dir):
    """Discover and validate skill modules from a directory.

    Args:
        modules_dir: Path to the skills/modules/ directory.

    Returns:
        tuple of (skills: list[ModuleSkill], errors: list[tuple[Path, str]])
        where errors are (file_path, error_string) for modules that failed.
    """
    modules_dir = Path(modules_dir)
    skills = []
    errors = []

    if not modules_dir.is_dir():
        return skills, errors

    for path in sorted(modules_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            skill = _load_one(path, modules_dir)
            skills.append(skill)
        except ContractError as exc:
            errors.append((path, str(exc)))
        except Exception as exc:
            errors.append((path, f"unexpected error: {exc}"))

    return skills, errors


def _load_one(path, modules_dir):
    """Load and validate a single module file. Returns ModuleSkill."""
    module_name = f"_skill_module_{path.stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ContractError(f"cannot load {path.name}: spec is None")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ContractError(f"module {path.name!r} import failed: {exc}")
    finally:
        sys.modules.pop(module_name, None)

    meta = _validate_meta(module)

    # Find SkillBase subclass in the module
    skill_cls = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, SkillBase)
            and attr is not SkillBase
        ):
            skill_cls = attr
            break

    if skill_cls is None:
        raise ContractError(
            f"module {path.name!r}: no SkillBase subclass found"
        )

    _validate_skill_class(skill_cls, path.name)
    return ModuleSkill(meta, skill_cls, module)
