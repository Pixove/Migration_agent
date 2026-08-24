from __future__ import annotations

import unittest

from agent.config import load_config
from migration.registry import get_profiles, load_profile


class ProfileRegistryTests(unittest.TestCase):
    def test_profiles_registered(self):
        profiles = get_profiles()
        self.assertIn("py2to3", profiles)
        self.assertIn("py3_upgrade", profiles)

    def test_load_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            load_profile("not_exist")

    def test_config_has_migration_profile(self):
        config = load_config("config.yaml")
        self.assertEqual(config.migration.profile, "py2to3")
        self.assertEqual(config.migration.scope, "syntax")

    def test_py3_upgrade_profile_has_transform(self):
        profile = load_profile("py3_upgrade")
        self.assertIsNotNone(profile.transform)

    def test_profiles_have_knowledge_base(self):
        profiles = get_profiles()
        self.assertEqual(
            profiles["py2to3"].knowledge_base,
            "knowledge_base/py2to3",
        )
        self.assertEqual(
            profiles["py3_upgrade"].knowledge_base,
            "knowledge_base/py3_upgrade",
        )


if __name__ == "__main__":
    unittest.main()
