"""Example module-contract skill: hello_skill.

Serves as the reference implementation of the SkillBase interface.
Returns a greeting with the provided name.
"""

from qacompanion.skills.module_contract import SkillBase

MODULE_meta = {
    "name": "hello",
    "version": "1.0.0",
    "description": "Example skill that returns a greeting",
}


class HelloSkill(SkillBase):
    """Greeting skill — minimal SkillBase implementation."""

    @property
    def name(self):
        return MODULE_meta["name"]

    @property
    def description(self):
        return MODULE_meta["description"]

    def run(self, **kwargs):
        who = kwargs.get("name", "world")
        return {"greeting": f"hello {who}"}
