import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from client_apps import linux


class LinuxAppTests(TestCase):
    def test_user_entries_mask_system_entries_and_launch_without_a_shell(self):
        with TemporaryDirectory() as temp:
            user, system = Path(temp) / "user", Path(temp) / "system"
            for directory in (user, system):
                (directory / "applications").mkdir(parents=True)
            entry = "[Desktop Entry]\nType=Application\nName=Test App\nExec=test-app %U\n"
            (system / "applications/test.desktop").write_text(entry)
            (user / "applications/test.desktop").write_text("[Desktop Entry]\nType=Application\nHidden=true\n")
            test_app = system / "applications/visible.desktop"
            test_app.write_text(entry)
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(user), "XDG_DATA_DIRS": str(system), "DISPLAY": "", "WAYLAND_DISPLAY": ""}):
                app, = linux.catalog()
                self.assertEqual(app.app_id, "visible.desktop")
                self.assertEqual(linux.launch(app), "no_desktop")
                with patch.dict(os.environ, {"DISPLAY": ":1"}), patch("shutil.which", return_value="/usr/bin/gio"), patch("subprocess.run") as run:
                    self.assertEqual(linux.launch(app), "launch_requested")
                    self.assertEqual(run.call_args.args[0], ["/usr/bin/gio", "launch", str(test_app)])
