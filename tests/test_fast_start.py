"""Unit tests for Octane Fast Start, without Blender or Octane.

Run:  python -m unittest discover -s tests -v
Each test runs one scenario from scenarios.py in a separate Python process,
against startup/octane_fast_start.py (or the file in $FAST_START_PATH), using
the stub Octane add-on in tests/stub_octane and a fake bpy module.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("FAST_START_PATH",
                        os.path.join(HERE, os.pardir, "startup", "octane_fast_start.py"))

API_START, OCIO = 303, 2
OK = "<response result='1' content='stub'/>"
ALL_FOUR = [["utils_function", API_START, "", -1, None],
            ["utils_function", OCIO, "<ocio/>", -1, None],
            ["reset_render"],
            ["update_server_settings", 1, True, 0, 0]]


def run_scenario(name):
    p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "scenarios.py"), SCRIPT, name],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(f"scenario {name} crashed:\n{p.stdout}\n{p.stderr}")
    trace = json.loads(p.stdout.strip().splitlines()[-1])
    if "skip" in trace:
        raise unittest.SkipTest(trace["skip"])
    return trace


class FastStartTests(unittest.TestCase):

    def test_offline_skips_every_slow_call(self):
        t = run_scenario("offline_default")
        self.assertTrue(t["patched"])
        self.assertEqual(t["calls_reaching_octane"], [])
        # API_START, then 2 file loads x (OCIO, reset_render, update_server_settings)
        self.assertEqual(t["skipped"], 7)
        self.assertEqual(t["results"], ["", "", None, "", None])  # what failed calls return
        self.assertTrue(t["pending_start"])

    def test_online_passes_calls_through_unchanged(self):
        t = run_scenario("online_default")
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR)
        self.assertEqual(t["results"], [OK, OK, "settings"])
        self.assertEqual(t["skipped"], 0)

    def test_server_coming_online_runs_skipped_startup_work_once(self):
        t = run_scenario("offline_then_online")
        self.assertTrue(t["prober_saw_online"])
        # catch-up (API_START, OCIO, reset) exactly once, then the next file load goes through
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR + ALL_FOUR[1:])
        self.assertFalse(t["pending_start"])
        self.assertEqual(t["skipped"], 4)

    def test_server_going_offline_skips_again(self):
        t = run_scenario("online_then_offline")
        self.assertTrue(t["prober_saw_offline"])
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR[:1])
        self.assertEqual(t["skipped"], 3)

    def test_custom_port_from_octane_preferences_is_used(self):
        # Regression test: the port used to be read before Octane's preferences
        # existed, so a server on a non-default port was treated as offline.
        t = run_scenario("custom_port_online")
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR)
        self.assertEqual(t["skipped"], 0)

    def test_localhost_address_is_probed_as_127_0_0_1(self):
        t = run_scenario("localhost_alias")
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR)

    def test_register_after_octane_was_imported_still_patches(self):
        t = run_scenario("reload")
        self.assertTrue(t["patched"])
        self.assertEqual(t["calls_reaching_octane"], [])
        self.assertEqual(t["skipped"], 4)

    def test_registering_twice_does_not_wrap_twice(self):
        t = run_scenario("double_register")
        self.assertEqual(t["finders_installed"], 1)
        self.assertEqual(t["calls_reaching_octane"], ALL_FOUR)


if __name__ == "__main__":
    unittest.main()
