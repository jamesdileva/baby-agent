"""Broken module: has MODULE_meta but no SkillBase subclass."""

MODULE_meta = {
    "name": "no-class",
    "version": "1.0.0",
    "description": "Meta present but no skill class",
}


def helper():
    return "I exist but don't inherit SkillBase"
