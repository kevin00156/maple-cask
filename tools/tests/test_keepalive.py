"""MC-12: keepalive unit 用跑這次的直譯器;status 看上一次 service 的結果。不碰真的 systemd。"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_passkey import cli


class KeepaliveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(cli, 'systemd_unit_dir', return_value=self.tmp.name),
                  patch.object(cli.shutil, 'which', return_value='/usr/bin/systemctl')):
            p.start(); self.addCleanup(p.stop)

    def service(self):
        with open(os.path.join(self.tmp.name, cli.UNIT + '.service')) as f:
            return f.read()

    def test_exec_start_names_interpreter(self):
        with patch.object(cli, 'systemctl', return_value=True):
            cli.keepalive_install()
        me = os.path.abspath(cli.__file__)
        self.assertIn(f"ExecStart={sys.executable} {me} keepalive\n", self.service())

    def test_old_shebang_unit_gets_rewritten(self):
        me = os.path.abspath(cli.__file__)
        for suffix, body in (('.timer', ''), ('.service', f"ExecStart={me} keepalive\n")):
            with open(os.path.join(self.tmp.name, cli.UNIT + suffix), 'w') as f:
                f.write(body)
        with patch.object(cli, 'systemctl', return_value=True), patch('builtins.print'):
            cli.keepalive_ensure()
        self.assertIn(sys.executable, self.service())

    def state(self, show):
        open(os.path.join(self.tmp.name, cli.UNIT + '.timer'), 'w').close()
        with patch.object(cli, 'systemctl_out', side_effect=lambda *a: '' if a[0] == 'is-active' else show):
            return cli.keepalive_state()

    def test_state_reports_failed_runs(self):
        s = self.state("Result=exit-code\nExecMainStatus=1\n")
        self.assertIn('失敗', s); self.assertIn('ExecMainStatus=1', s)

    def test_state_ok_when_never_run_or_succeeded(self):
        self.assertIn('保活跑著', self.state("Result=success\nExecMainStatus=0\n"))

    def test_state_ok_when_show_fails(self):
        self.assertIn('保活跑著', self.state(None))


if __name__ == '__main__':
    unittest.main()
