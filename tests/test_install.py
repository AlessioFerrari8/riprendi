import unittest

from riprendi.cli import render_unit


class Unit(unittest.TestCase):
    def test_installed_package_needs_no_pythonpath(self):
        unit = render_unit("/venv/bin/python", "/home/u/.local/bin/claude", None)
        self.assertIn("ExecStart=/venv/bin/python -m riprendi watch", unit)
        self.assertNotIn("PYTHONPATH", unit)

    def test_claudes_folder_comes_first_on_path(self):
        # A systemd service does not inherit the shell's PATH.
        unit = render_unit("/usr/bin/python3", "/home/u/.local/bin/claude", None)
        self.assertIn("Environment=PATH=/home/u/.local/bin:/usr/local/bin:/usr/bin:/bin", unit)

    def test_running_from_a_clone_sets_pythonpath(self):
        unit = render_unit("/usr/bin/python3", "/usr/bin/claude", "/src/riprendi")
        self.assertIn("Environment=PYTHONPATH=/src/riprendi", unit)
        # /usr/bin is not listed twice
        self.assertIn("Environment=PATH=/usr/bin:/usr/local/bin:/bin", unit)


if __name__ == "__main__":
    unittest.main()
