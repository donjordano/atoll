import os
import subprocess
import tempfile
import unittest
from unittest import mock

from atoll import paths
from atoll.system import autostart
from atoll.system.git import git_status, parse_git, recent_commits
from atoll.system.github import parse_prs
from atoll.system.sysinfo import cpu_percent


class Git(unittest.TestCase):
    def test_parse_porcelain_v2(self):
        g = parse_git("# branch.oid abc\n# branch.head main\n# branch.ab +2 -1\n"
                      "1 .M N... 100644 100644 100644 h1 h2 src/my file.py\n"
                      "2 R. N... 100644 100644 100644 h1 h2 R100 new.py\told.py\n? notes.txt\n")
        self.assertEqual(g, {"branch": "main", "ahead": 2, "behind": 1, "changed": 3,
                             "files": ["src/my file.py", "new.py", "notes.txt"]})

    def test_empty_repo_has_no_commits(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertEqual(recent_commits(d), [])
            self.assertEqual(git_status(d)["changed"], 0)
            subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                            "--allow-empty", "-m", "first"], check=True)
            (line,) = recent_commits(d)
            self.assertIn("first", line)

    def test_no_upstream(self):
        self.assertIsNone(parse_git("# branch.head (detached)\n")["ahead"])


class GitHub(unittest.TestCase):
    def test_parse_prs(self):
        self.assertEqual(parse_prs('[{"repository":{"nameWithOwner":"o/r"},"number":5,"title":"T","url":"u"}]'),
                         [("o/r", 5, "T", "u")])
        self.assertEqual(parse_prs(""), [])


class SysInfo(unittest.TestCase):
    def test_cpu_percent(self):
        self.assertEqual(cpu_percent((100, 1000), (150, 1100)), 50.0)
        self.assertEqual(cpu_percent((1, 1), (1, 1)), 0.0)


class Autostart(unittest.TestCase):
    def test_exec_line_quotes_awkward_paths(self):
        self.assertIn('Exec=python3 "/home/a b/atoll/bin/atoll"\n', autostart.autostart_entry("/home/a b/atoll/bin/atoll"))
        self.assertEqual(autostart.exec_quote('/x/$HOME "q" 100%'), r'"/x/\\$HOME \\"q\\" 100%%"')
        self.assertEqual(autostart.exec_quote("/x\\y"), r'"/x\\\\y"')  # a literal backslash becomes four


class Migration(unittest.TestCase):
    def test_old_name_and_old_launcher_move_over(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(home + "/.local/share/claude-island")
            open(home + "/.local/share/claude-island/tasks.json", "w").write("[]")
            os.makedirs(home + "/.config/autostart")
            open(home + "/.config/autostart/claude-island.desktop", "w").write("Exec=python3 /x/island.py\n")
            with mock.patch.multiple(paths, HOME=home, DATA=home + "/.local/share/atoll", CACHE=home + "/.cache/atoll",
                                     AUTOSTART=home + "/.config/autostart/atoll.desktop"):
                autostart.migrate_old_layout()
                self.assertTrue(os.path.exists(home + "/.local/share/atoll/tasks.json"))
                self.assertFalse(os.path.exists(home + "/.config/autostart/claude-island.desktop"))
                self.assertIn("bin/atoll", open(paths.AUTOSTART).read())

    def test_stale_island_py_entry_rewritten(self):
        with tempfile.TemporaryDirectory() as home:
            entry = home + "/atoll.desktop"
            open(entry, "w").write("Exec=python3 /old/island.py\n")
            with mock.patch.multiple(paths, HOME=home, DATA=home + "/d", CACHE=home + "/c", AUTOSTART=entry):
                autostart.migrate_old_layout()
            self.assertNotIn("island.py", open(entry).read())


if __name__ == "__main__":
    unittest.main()
