from unittest import TestCase

from llm.tool_commands import direct_command


class AppCommandTests(TestCase):
    def test_find_and_open_have_distinct_intents(self):
        self.assertEqual(direct_command("Where's Blender installed?"), ("find_app", {"name": "Blender"}))
        self.assertEqual(direct_command("Do I have OBS on this PC?"), ("find_app", {"name": "OBS"}))
        self.assertEqual(direct_command("Open File Explorer"), ("open_app", {"name": "File Explorer"}))
        self.assertEqual(direct_command('Launch "Visual Studio Code"'), ("open_app", {"name": "Visual Studio Code"}))

    def test_conditional_and_compound_requests_fall_back(self):
        self.assertIsNone(direct_command("Open Chrome and then search for pizza"))
        self.assertIsNone(direct_command("Open Chrome with my work profile"))
        self.assertIsNone(direct_command("Start it again"))
