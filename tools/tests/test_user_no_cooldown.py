"""User commands ignore legacy quota; temporary files and fake services only."""
import contextlib
import json
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from test_passkey import cli, p, CRED
import test_passkey_flow as flow


class ClickDrivenCDP(flow.FakeCDP):
    """First normal input has no effect; second release navigates to RP."""
    def __init__(self):
        super().__init__([], assertion=True)
        self.host = 'login.beanfun.com'
        self.releases = 0

    def call(self, method, params=None, sid=None):
        result = super().call(method, params, sid)
        if method == 'Input.dispatchMouseEvent' and params['type'] == 'mouseReleased':
            self.releases += 1
            if self.releases == 2:
                self.host = p.RP
        if method == 'Runtime.evaluate' and params['expression'] == p.CLICK_PASS:
            self.host = 'tw.beanfun.com'
        return result


class UserNoCooldownTests(unittest.TestCase):
    def legacy(self, dirty=False):
        return dict(count=3, last=time.time(), dirty=dirty)

    def test_count3_second_pointer_confirms_navigation_without_wait(self):
        helper = flow.FlowTests()
        for _ in range(4):  # independent user commands, not an AI remote budget
            cdp = ClickDrivenCDP()
            result, records = helper.run_flow(cdp, timeout=10, initial_state=self.legacy())
            self.assertIsInstance(result, tuple)
            self.assertEqual(cdp.releases, 2)
            self.assertTrue(any(r.get('navigation_confirmed') for r in records))
            self.assertEqual(records[-1], dict(saved=True, assertions=1))
            self.assertFalse(helper.last_dirty)
            self.assertEqual(helper.store_calls, 1)
            self.assertTrue(all(delay <= .3 for delay in helper.sleep_calls))

    def test_qr_count3_and_dirty_do_not_reject_or_sleep(self):
        with tempfile.TemporaryDirectory() as d:
            state = self.legacy(dirty=True)
            path = Path(d, 'passkey-state.json'); path.write_text(json.dumps(state))
            with patch.object(cli, 'config_dir', return_value=d), patch.object(cli, '_qr_login', return_value='qr') as qr, patch.object(p.time, 'sleep') as sleep:
                for _ in range(4):
                    self.assertEqual(cli.qr_login(10), 'qr')
                self.assertEqual(qr.call_count, 4); sleep.assert_not_called()
            self.assertEqual(json.loads(path.read_text()), state)

    def test_setup_count3_reaches_navigation_and_preserves_legacy_fields(self):
        with tempfile.TemporaryDirectory() as d:
            state = self.legacy(dirty=True)
            path = Path(d, 'passkey-state.json'); path.write_text(json.dumps(state))
            pages = Mock(); pages.refresh.return_value = [dict(type='page', targetId='t')]
            pages.attached = {'t': ('s', 'a')}; pages.credentials.return_value = [CRED.copy()]
            cdp = Mock()
            with patch.object(p, 'keyring_store_ready'), patch.object(p, 'secret', side_effect=[None, None]), patch.object(p, 'Pages', return_value=pages), patch.object(p, 'browser', return_value=contextlib.nullcontext(cdp)), patch.object(p.time, 'sleep') as sleep, patch('builtins.print'):
                p.setup(Mock(PORTAL_BASE='https://invalid/'), d, '/unused')
                sleep.assert_not_called()
            self.assertTrue(any(c.args[0] == 'Page.navigate' for c in cdp.call.call_args_list))
            self.assertEqual(json.loads(path.read_text()), dict(state, dirty=False))

    def test_legacy_fields_are_not_validated(self):
        for fields in ({}, dict(count='obsolete', last=None), dict(count=900, last={})):
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as d:
                state = dict(fields, dirty=False)
                Path(d, 'passkey-state.json').write_text(json.dumps(state))
                with p.Gate(d) as lock:
                    self.assertEqual(lock.state, state)

    def test_dirty_still_stops_login_before_keyring_or_browser(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'passkey-state.json').write_text(json.dumps(self.legacy(dirty=True)))
            with patch.object(p, 'secret') as secret, patch.object(p, 'browser') as browser:
                with self.assertRaisesRegex(p.PasskeyError, 'signCount'):
                    p.login(Mock(), d, '/unused')
                secret.assert_not_called(); browser.assert_not_called()

    def test_held_credential_lock_still_rejects_qr(self):
        # Existing subprocess lock test verifies cross-process flock; this checks
        # the QR callsite cannot run its service while the same lock is held.
        with tempfile.TemporaryDirectory() as d, p.Gate(d):
            with patch.object(cli, 'config_dir', return_value=d), patch.object(cli, '_qr_login') as qr:
                with self.assertRaisesRegex(p.PasskeyError, '憑證忙碌'):
                    cli.qr_login(10)
                qr.assert_not_called()

    def test_invalid_safety_state_fails_closed(self):
        for text in ('{}', '{"dirty":0}', '[]', 'null', '{broken'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as d:
                Path(d, 'passkey-state.json').write_text(text)
                with self.assertRaises(p.PasskeyError):
                    with p.Gate(d): pass
