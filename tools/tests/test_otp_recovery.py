"""Deterministic command recovery tests; no network/keyring/game/session files."""
from argparse import Namespace
from contextlib import ExitStack
import io
import unittest
from unittest.mock import Mock, patch
from test_passkey import cli, p


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.events = []
        self.oldacct = dict(sid='stable', sname='first', ssn='old', enabled=True)
        self.newacct = dict(sid='stable', sname='renamed', ssn='new', enabled=True)
        self.old = cli.Login(Mock(), 'fake-old', [self.oldacct])
        self.new = Mock()
        self.args = Namespace(run=False, qr=False, qr_timeout=12, name=None, pick=1,
                              wait_game=0, no_type=True, no_clip=True,
                              no_submit=False, mode='direct', gap=0)
        self.open = self.mock(cli, 'open_session', side_effect=self.open_old)
        self.original_login = p.login
        self.login = self.mock(p, 'login', side_effect=self.new_login)
        self.qr = self.mock(cli, 'qr_login', side_effect=AssertionError('unexpected QR'))
        self.save = self.mock(cli, 'save_session', side_effect=lambda x: self.events.append('save'))
        self.mock(cli, 'keepalive_ensure')
        self.mock(cli, 'load_remembered', return_value={'sname':'first'})
        self.prefs = self.mock(cli, 'save_remembered')
        self.pick = self.mock(cli, 'pick_account', return_value=self.oldacct)
        self.mock(cli, 'runtime_dir', return_value='/unused')
        self.mock(cli, 'config_dir', return_value='/unused')
        self.show = self.mock(cli, 'show')
        self.deliver = self.mock(cli, 'hand_over', side_effect=lambda *a, **k: self.events.append('deliver'))
        self.stderr = io.StringIO()
        self.stack.enter_context(patch('sys.stderr', self.stderr))
        self.original_otp = cli.bfotp.get_otp
        self.otp = self.mock(cli.bfotp, 'get_otp', side_effect=self.mint)
        self.errors = [cli.bfotp.BFError('injected request fault'), None]

    def mock(self, obj, name, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, **kwargs))

    def open_old(self):
        self.events.append('open'); return self.old

    def new_login(self, *a):
        self.events.append('passkey'); return self.new, 'fake-new', [self.newacct]

    def mint(self, session, token, account, *a):
        self.events.append('otp-old' if session is self.old.session else 'otp-new')
        error = self.errors.pop(0)
        if error: raise error
        self.assertIs(account, self.newacct)
        return 'fake-result'

    def test_old_fault_recovers_same_sid_once(self):
        self.assertEqual(cli.cmd_otp(self.args), 0)
        self.assertEqual(self.events, ['open', 'otp-old', 'passkey', 'save', 'otp-new', 'deliver'])
        self.login.assert_called_once(); self.save.assert_called_once()
        self.pick.assert_called_once(); self.prefs.assert_not_called()
        self.show.assert_called_once(); self.deliver.assert_called_once()
        self.old.session.close.assert_called_once(); self.new.close.assert_called_once()

    def test_old_otp_fault_real_login_loop_ignores_legacy_count3(self):
        import contextlib
        import json
        import tempfile
        import time
        from pathlib import Path
        from test_user_no_cooldown import ClickDrivenCDP
        from test_passkey_flow import CRED
        cdp = ClickDrivenCDP()
        clock = iter(i*.1 for i in range(1000))
        with tempfile.TemporaryDirectory() as directory:
            state = dict(count=3, last=time.time(), dirty=False)
            path = Path(directory, 'passkey-state.json')
            path.write_text(json.dumps(state))
            self.mock(cli, 'config_dir', return_value=directory)
            self.mock(p, 'secret', return_value=CRED.copy())
            self.mock(p, 'browser', return_value=contextlib.nullcontext(cdp))
            self.mock(p.time, 'monotonic', side_effect=lambda:next(clock))
            self.mock(p.time, 'sleep')
            self.mock(cli.bfotp, 'new_session', return_value=self.new)
            self.mock(cli.bfotp, 'bfwebtoken', return_value='fake-new')
            self.mock(cli.bfotp, 'list_accounts', return_value=[self.newacct])
            def actual_login(api, config, runtime):
                self.events.append('passkey')
                return self.original_login(api, config, runtime, timeout=10,
                                           diagnostic=lambda record:None)
            self.login.side_effect = actual_login
            self.assertEqual(cli.cmd_otp(self.args), 0)
            self.assertEqual(self.events, ['open', 'otp-old', 'passkey', 'save', 'otp-new', 'deliver'])
            self.login.assert_called_once(); self.qr.assert_not_called()
            self.assertEqual(self.otp.call_count, 2)
            self.assertEqual(cdp.releases, 2)
            self.assertEqual(json.loads(path.read_text()), state)
            self.new.close.assert_called_once()

    def test_explicit_qr_old_session_otp_fault_does_not_switch_to_passkey(self):
        self.args.qr = True
        for error in (cli.bfotp.BFError('fault'), cli.requests.RequestException('fault')):
            with self.subTest(error=type(error).__name__):
                self.events.clear()
                self.errors = [error, None]
                with self.assertRaisesRegex(cli.bfotp.BFError, 'QR'):
                    cli.cmd_otp(self.args)
                self.assertEqual(self.events, ['open', 'otp-old'])
                self.login.assert_not_called(); self.qr.assert_not_called()
                self.save.assert_not_called(); self.show.assert_not_called()
                self.deliver.assert_not_called()
                self.assertNotIn('passkey 恢復', self.stderr.getvalue())
        self.assertEqual(self.otp.call_count, 2)  # one per independent command
        self.assertEqual(self.old.session.close.call_count, 2)

    def test_login_failure_no_qr_or_second_otp(self):
        self.login.side_effect = p.PasskeyError('injected login failure')
        with self.assertRaises(p.PasskeyError): cli.cmd_otp(self.args)
        self.login.assert_called_once(); self.qr.assert_not_called()
        self.assertEqual(self.otp.call_count, 1); self.deliver.assert_not_called()
        self.save.assert_not_called(); self.old.session.close.assert_called_once()

    def test_second_fault_stops_and_redacts(self):
        self.errors[1] = cli.requests.RequestException('FAKE_SENSITIVE_QUERY')
        with self.assertRaises(cli.bfotp.BFError) as caught: cli.cmd_otp(self.args)
        self.assertNotIn('FAKE_SENSITIVE_QUERY', str(caught.exception) + self.stderr.getvalue())
        self.assertEqual(self.otp.call_count, 2); self.login.assert_called_once()
        self.qr.assert_not_called(); self.deliver.assert_not_called()
        self.new.close.assert_called_once()

    def test_initial_new_session_has_no_recovery_budget(self):
        self.open.side_effect = cli.bfotp.BFError('old cannot list')
        with self.assertRaises(cli.bfotp.BFError): cli.cmd_otp(self.args)
        self.login.assert_called_once(); self.assertEqual(self.otp.call_count, 1)
        self.qr.assert_not_called(); self.new.close.assert_called_once()

    def test_sid_missing_or_disabled_never_reselects(self):
        for account in (dict(self.newacct, sid='other'), dict(self.newacct, enabled=False)):
            with self.subTest(account=account['enabled']):
                self.setUp_subcase(account)
                with self.assertRaises(cli.bfotp.BFError): cli.cmd_otp(self.args)
                self.assertEqual(self.otp.call_count, 1); self.pick.assert_called_once()
                self.prefs.assert_not_called(); self.deliver.assert_not_called()
                self.new.close.assert_called_once()

    def setUp_subcase(self, account):
        for mock in (self.otp, self.pick, self.prefs, self.deliver, self.new.close): mock.reset_mock()
        self.errors = [cli.bfotp.BFError('fault')]
        self.login.side_effect = lambda *a: (self.new, 'fake-new', [account])

    def test_non_request_interrupts_do_not_login(self):
        for error in (KeyboardInterrupt(), SystemExit(), ValueError('local failure')):
            with self.subTest(error=type(error).__name__):
                self.errors = [error]
                with self.assertRaises(type(error)): cli.cmd_otp(self.args)
                self.login.assert_not_called(); self.deliver.assert_not_called()

    def test_selection_and_ui_errors_do_not_login(self):
        self.pick.side_effect = cli.bfotp.BFError('selection cancelled')
        with self.assertRaises(cli.bfotp.BFError): cli.cmd_otp(self.args)
        self.login.assert_not_called(); self.otp.assert_not_called()
        self.pick.side_effect = None
        self.otp.side_effect = None; self.otp.return_value = 'fake-result'
        self.args.no_type = False
        auto = self.mock(cli, 'auto_type', side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt): cli.cmd_otp(self.args)
        auto.assert_called_once(); self.login.assert_not_called()

    def test_run_preflight_stops_before_requests(self):
        self.args.run = True
        self.mock(cli, 'check_run_env', return_value='injected preflight failure')
        self.assertEqual(cli.cmd_otp(self.args), 2)
        self.open.assert_not_called(); self.login.assert_not_called(); self.otp.assert_not_called()

    def test_unavailable_recovery_never_qr(self):
        self.login.side_effect = p.PasskeyUnavailable('沒有專用 passkey')
        with self.assertRaises(p.PasskeyUnavailable): cli.cmd_otp(self.args)
        self.qr.assert_not_called(); self.assertEqual(self.otp.call_count, 1)

    def test_normal_unavailable_can_qr_but_failure_cannot(self):
        self.qr.side_effect = None; self.qr.return_value = self.old
        for error in (p.PasskeyUnavailable('missing dependency'), p.PasskeyError('failed'),
                      cli.requests.RequestException('FAKE_SENSITIVE_QUERY')):
            with self.subTest(error=type(error).__name__):
                self.qr.reset_mock(); self.login.side_effect = error
                if isinstance(error, p.PasskeyUnavailable):
                    self.assertIs(cli.fresh_login(self.args), self.old); self.qr.assert_called_once_with(12)
                else:
                    with self.assertRaises(p.PasskeyError) as caught: cli.fresh_login(self.args)
                    self.assertNotIn('FAKE_SENSITIVE_QUERY', str(caught.exception))
                    self.qr.assert_not_called()

    def test_explicit_qr_failure_once_no_passkey(self):
        self.args.qr = True
        self.qr.side_effect = cli.bfotp.BFError('QR failed')
        with self.assertRaises(cli.bfotp.BFError): cli.fresh_login(self.args)
        self.qr.assert_called_once_with(12); self.login.assert_not_called()

    def test_bfotp_missing_lpk_redacts_body_no_hidden_retry(self):
        session = Mock()
        response = Mock(status_code=200, text='FAKE_SENSITIVE_HTML')
        session.get.return_value = response
        with self.assertRaises(cli.bfotp.BFError) as caught:
            self.original_otp(session, 'fake', self.oldacct, *cli.SERVICE)
        self.assertNotIn('FAKE_SENSITIVE_HTML', str(caught.exception))
        session.get.assert_called_once()

    def test_network_fault_also_recovers(self):
        self.errors[0] = cli.requests.Timeout('FAKE_SENSITIVE_QUERY')
        self.assertEqual(cli.cmd_otp(self.args), 0)
        self.assertEqual(self.otp.call_count, 2); self.login.assert_called_once()
        self.assertNotIn('FAKE_SENSITIVE_QUERY', self.stderr.getvalue())

    def test_new_command_restores_budget(self):
        for i in range(2):
            self.errors = [cli.bfotp.BFError('fault'), None]
            self.assertEqual(cli.cmd_otp(self.args), 0)
        self.assertEqual(self.login.call_count, 2)
        self.assertEqual(self.otp.call_count, 4)
        self.assertEqual(self.deliver.call_count, 2)

    def test_wait_and_delivery_faults_do_not_login(self):
        self.args.wait_game = 1
        wait = self.mock(cli, 'wait_for_login_screen', side_effect=cli.bfotp.BFError('UI fault'))
        with self.assertRaises(cli.bfotp.BFError): cli.cmd_otp(self.args)
        self.otp.assert_not_called(); self.login.assert_not_called()
        wait.side_effect = None; wait.return_value = True
        self.otp.side_effect = None; self.otp.return_value = 'fake-result'
        self.deliver.side_effect = cli.requests.RequestException('delivery fault')
        with self.assertRaises(cli.requests.RequestException): cli.cmd_otp(self.args)
        self.login.assert_not_called(); self.otp.assert_called_once()

    def test_initial_qr_new_session_otp_fault_no_more_login(self):
        self.open.side_effect = cli.bfotp.BFError('no saved session')
        self.args.qr = True
        self.qr.side_effect = None; self.qr.return_value = self.old
        with self.assertRaises(cli.bfotp.BFError): cli.cmd_otp(self.args)
        self.qr.assert_called_once_with(12); self.login.assert_not_called()
        self.otp.assert_called_once(); self.deliver.assert_not_called()

    def test_cmd_login_actual_failure_no_qr(self):
        self.login.side_effect = cli.requests.Timeout('FAKE_SENSITIVE_QUERY')
        with self.assertRaises(p.PasskeyError) as caught: cli.cmd_login(self.args)
        self.assertNotIn('FAKE_SENSITIVE_QUERY', str(caught.exception))
        self.login.assert_called_once(); self.qr.assert_not_called(); self.pick.assert_not_called()

    def test_missing_credentials_typed_unavailable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, patch.object(p, 'secret', return_value=None), patch.object(p, 'browser') as browser:
            with self.assertRaises(p.PasskeyUnavailable): self.original_login(Mock(), directory, '/unused')
            browser.assert_not_called()

    def test_missing_dependencies_typed_unavailable(self):
        with patch.object(p.shutil, 'which', return_value=None), patch.object(p.subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaises(p.PasskeyUnavailable): p.secret('lookup')
            with self.assertRaises(p.PasskeyUnavailable): p.browser_executable()
            with self.assertRaises(p.PasskeyUnavailable): p.keyring_available()

    def test_initial_login_failure_stops_before_otp(self):
        self.open.side_effect = cli.bfotp.BFError('cannot list')
        self.login.side_effect = p.PasskeyError('login failure')
        with self.assertRaises(p.PasskeyError): cli.cmd_otp(self.args)
        self.login.assert_called_once(); self.qr.assert_not_called(); self.otp.assert_not_called()

    def test_second_bferror_also_stops_redacted(self):
        self.errors[1] = cli.bfotp.BFError('FAKE_SENSITIVE_HTML')
        with self.assertRaises(cli.bfotp.BFError) as caught: cli.cmd_otp(self.args)
        self.assertNotIn('FAKE_SENSITIVE_HTML', str(caught.exception) + self.stderr.getvalue())
        self.assertEqual(self.otp.call_count, 2); self.login.assert_called_once()
        self.deliver.assert_not_called()

    def test_session_save_failure_stops_and_closes(self):
        self.save.side_effect = OSError('FAKE_SENSITIVE_QUERY')
        with self.assertRaises(p.PasskeyError) as caught: cli.cmd_otp(self.args)
        self.assertNotIn('FAKE_SENSITIVE_QUERY', str(caught.exception))
        self.login.assert_called_once(); self.save.assert_called_once()
        self.assertEqual(self.otp.call_count, 1); self.new.close.assert_called_once()
        self.qr.assert_not_called(); self.deliver.assert_not_called()

    def test_run_exec_interrupt_does_not_login(self):
        self.args.run = True
        self.mock(cli, 'check_run_env', return_value=None)
        self.mock(cli, 'launcher', return_value='/fake/no-game')
        execute = self.mock(cli.os, 'execv', side_effect=KeyboardInterrupt())
        self.otp.side_effect = None; self.otp.return_value = 'fake-result'
        with patch('builtins.print'), self.assertRaises(KeyboardInterrupt): cli.cmd_otp(self.args)
        execute.assert_called_once_with('/fake/no-game', ['/fake/no-game'])
        self.otp.assert_called_once(); self.login.assert_not_called()
        self.deliver.assert_called_once()
        self.assertFalse(self.deliver.call_args.kwargs['two_stage'])

    def test_recovery_persistence_interrupt_closes_new_session(self):
        for target in ('save_session', 'keepalive_ensure'):
            for exception_type in (KeyboardInterrupt, SystemExit):
                with self.subTest(target=target, exception=exception_type.__name__):
                    self.login.reset_mock(); self.qr.reset_mock(); self.otp.reset_mock()
                    self.new.close.reset_mock(); self.old.session.close.reset_mock()
                    self.errors = [cli.bfotp.BFError('injected fault')]
                    interruption = exception_type()
                    # keepalive also runs before OTP; interrupt only after passkey.
                    def interrupt_after_login(*args):
                        if self.login.called: raise interruption
                    with patch.object(cli, target, side_effect=interrupt_after_login):
                        with self.assertRaises(exception_type) as caught: cli.cmd_otp(self.args)
                    self.assertIs(caught.exception, interruption)
                    self.login.assert_called_once(); self.qr.assert_not_called()
                    self.otp.assert_called_once(); self.deliver.assert_not_called()
                    self.old.session.close.assert_called_once(); self.new.close.assert_called_once()
