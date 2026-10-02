"""Check the public QR entry without contacting a login service."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class MapleQrWrapperTests(unittest.TestCase):
    def test_qr_explicitly_forces_qr_and_preserves_arguments(self):
        source = Path(__file__).resolve().parents[1] / "maple"
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory)
            shutil.copyfile(source, tools / "maple")
            stub = tools / "maple-login"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:]))\n"
            )
            stub.chmod(0o700)
            env = dict(os.environ, WINE_ROOT="/unused", WINEPREFIX="/unused",
                       GAME_DIR="/unused")
            result = subprocess.run(
                ["bash", str(tools / "maple"), "qr", "--qr-timeout", "30"],
                env=env, capture_output=True, text=True, check=True, timeout=5,
            )
            self.assertEqual(json.loads(result.stdout),
                             ["login", "--qr", "--qr-timeout", "30"])


if __name__ == "__main__":
    unittest.main()
