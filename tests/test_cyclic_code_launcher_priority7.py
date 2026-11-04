"""Regression for the observed queue-niceness launch failure; no solver calls."""
import os
import subprocess
import sys
import unittest


class LauncherPriorityTests(unittest.TestCase):
    def test_real_direct_and_inherited_queue_priorities(self):
        for increment in (0, 19):
            with self.subTest(increment=increment):
                code = (
                    "import os; "
                    "from scripts.run_cyclic_code_sat7 import configure_background_priority; "
                    f"os.nice({increment}); "
                    "before=os.getpriority(os.PRIO_PROCESS,0); "
                    "configure_background_priority(); "
                    "assert os.getpriority(os.PRIO_PROCESS,0)==max(before,10)"
                )
                result = subprocess.run([sys.executable, "-B", "-c", code],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
