"""Offline tests only. Never read real sessions/Secret Service or visit websites."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import maple_passkey as p
loader = importlib.machinery.SourceFileLoader('maple_login_test', str(TOOLS/'maple-login'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
loader.exec_module(cli)

# Dummy values, not an actual credential.
CRED = dict(credentialId='dummy-id', rpId=p.RP, privateKey='dummy-key', userHandle='dummy-user', signCount=1)


class Tests(unittest.TestCase):
    def setUp(self):
        # Never reach the real Secret Service from offline tests.
        self.keyring = patch.object(p, 'keyring_available', return_value=True)
        self.keyring.start()
        self.addCleanup(self.keyring.stop)
        self.store_ready = patch.object(p, 'keyring_store_ready')
        self.store_ready.start()
        self.addCleanup(self.store_ready.stop)

    def test_pipe_timeout(self):
        r, w = os.pipe(); rr, ww = os.pipe()
        try:
            with self.assertRaisesRegex(p.PasskeyError, '逾時'):
                p.Pipe(r, ww).call('Browser.getVersion', timeout=.01)
        finally:
            for fd in (r, w, rr, ww): os.close(fd)

    def test_pipe_nul_events_and_response(self):
        r, w = os.pipe(); rr, ww = os.pipe()
        try:
            os.write(w, b'{"method":"event"}\0{"id":1,"result":{"ok":true}}\0')
            pipe = p.Pipe(r, ww); event = Mock(); pipe.on_event = event
            self.assertEqual(pipe.call('test'), {'ok': True})
            self.assertTrue(os.read(rr, 1000).endswith(b'\0'))
            event.assert_called_once()
        finally:
            for fd in (r, w, rr, ww): os.close(fd)

    def test_secret_missing_dependency(self):
        with patch.object(p.subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaises(p.PasskeyError): p.secret('lookup')

    def test_secret_save_failure_no_secret_diagnostic(self):
        with patch.object(p.subprocess, 'run', return_value=Mock(returncode=1, stdout=b'', stderr=b'dummy-key')):
            with self.assertRaises(p.PasskeyError) as error: p.secret('store', CRED)
            self.assertNotIn('dummy-key', str(error.exception))

    def test_secret_save_readback_mismatch(self):
        other = dict(CRED, signCount=0)
        with patch.object(p.subprocess, 'run', side_effect=[Mock(returncode=0), Mock(returncode=0, stdout=json.dumps(other).encode())]):
            with self.assertRaisesRegex(p.PasskeyError, '驗證'): p.secret('store', CRED)

    def test_lock_has_no_user_quota_state(self):
        with tempfile.TemporaryDirectory() as d:
            for _ in range(4):
                with p.CredentialLock(d) as lock:
                    self.assertEqual(lock.state, dict(dirty=False))
                    lock.save()

    def test_lock_competition(self):
        with tempfile.TemporaryDirectory() as d, p.Gate(d):
            with self.assertRaises(p.PasskeyError):
                with p.Gate(d): pass

    def test_lock_other_process(self):
        import subprocess
        script = ('import sys;sys.path.insert(0,sys.argv[1]);import maple_passkey as p\n'
                  'try:\n with p.Gate(sys.argv[2]): pass\n'
                  'except p.PasskeyError: sys.exit(75)\n')
        with tempfile.TemporaryDirectory() as d, p.Gate(d):
            result = subprocess.run([sys.executable, '-c', script, str(TOOLS), d], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 75)

    def test_corrupt_safety_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'passkey-state.json').write_text('{}')
            with self.assertRaises(p.PasskeyError):
                with p.Gate(d): pass

    def test_signcount_assertion_and_poll_max(self):
        cdp = Mock(); cdp.call.return_value = {'credentials': [dict(CRED, signCount=3)]}
        pages = p.Pages(cdp, CRED.copy()); pages.attached = {'t': ('s', 'a')}
        pages.active = ('s', 'a')
        pages.event({'method': 'WebAuthn.credentialAsserted', 'params': {'credential': dict(CRED, signCount=4)}})
        with patch.object(p, 'secret') as save:
            pages.sync()
            self.assertEqual(save.call_args.args[1]['signCount'], 4)

    def fake_pages(self):
        pages = Mock()
        pages.assertions = 0
        pages.refresh.return_value = [{'type':'page', 'targetId':'t', 'url':'about:blank'}]
        pages.attached = {'t': ('s', 'a')}
        return pages

    def run_failed_login(self, sync_error=False):
        with tempfile.TemporaryDirectory() as d:
            pages = self.fake_pages()
            if sync_error: pages.sync.side_effect = p.PasskeyError('save failed')
            with patch.object(p, 'secret', return_value=CRED.copy()), patch.object(p, 'Pages', return_value=pages), patch.object(p, 'browser') as b:
                b.return_value.__enter__.return_value = Mock()
                with self.assertRaises(p.PasskeyError): p.login(Mock(PORTAL_BASE='https://invalid/'), d, '/unused', timeout=0)
            pages.sync.assert_called_once()
            with p.Gate(d) as gate:
                self.assertEqual(gate.state['dirty'], sync_error)

    def test_website_timeout_still_syncs_count(self): self.run_failed_login()
    def test_save_failure_blocks_future_assertions(self): self.run_failed_login(True)

    def test_qr_fallback(self):
        args = Mock(qr=False, qr_timeout=12)
        with patch.object(p, 'login', side_effect=p.PasskeyUnavailable('missing')), patch.object(cli, 'qr_login', return_value='qr') as qr, patch.object(cli, 'runtime_dir', return_value='/unused'):
            self.assertEqual(cli.fresh_login(args), 'qr'); qr.assert_called_once_with(12)

    def test_force_qr_skips_passkey(self):
        with patch.object(p, 'login') as login, patch.object(cli, 'qr_login', return_value='qr'):
            self.assertEqual(cli.fresh_login(Mock(qr=True, qr_timeout=12)), 'qr'); login.assert_not_called()

    def test_passkey_session_conversion(self):
        session = Mock()
        with patch.object(p, 'login', return_value=(session, 'dummy-token', [])), patch.object(cli, 'runtime_dir', return_value='/unused'), patch.object(cli, 'save_session') as save, patch.object(cli, 'keepalive_ensure'), patch.object(cli, 'qr_login') as qr:
            result = cli.fresh_login(Mock(qr=False))
            self.assertIs(result.session, session); save.assert_called_once(); qr.assert_not_called()

    def test_default_browser_preferred(self):
        with patch.object(p.subprocess, 'run', return_value=Mock(stdout='com.brave.Browser.desktop')), patch.object(p.shutil, 'which', side_effect=lambda n: '/bin/'+n):
            self.assertEqual(p.browser_executable(), '/bin/brave-browser')

    def test_missing_browser(self):
        with patch.object(p.subprocess, 'run', side_effect=FileNotFoundError), patch.object(p.shutil, 'which', return_value=None):
            with self.assertRaises(p.PasskeyError): p.browser_executable()

    def test_session_priority(self):
        login = Mock(accounts=[{'sname': 'dummy', 'sid': 'dummy', 'enabled': True}])
        from argparse import Namespace
        args = Namespace(run=False, name=None, pick=None, wait_game=0, no_type=True, no_clip=True)
        with patch.object(cli, 'open_session', return_value=login), patch.object(cli, 'fresh_login') as fresh, patch.object(cli, 'keepalive_ensure'), patch.object(cli, 'load_remembered', return_value={'sname':'dummy'}), patch.object(cli.bfotp, 'get_otp', return_value='dummy'), patch.object(cli, 'show'), patch.object(cli, 'hand_over'):
            self.assertEqual(cli.cmd_otp(args), 0)
            fresh.assert_not_called(); login.close.assert_called_once()

    def test_setup_save_failure_does_not_clear_dirty(self):
        with tempfile.TemporaryDirectory() as d:
            with p.Gate(d) as gate:
                gate.state['dirty'] = True; gate.save()
            pages = self.fake_pages()
            pages.credentials.return_value = [CRED.copy()]
            with patch.object(p, 'secret', side_effect=[None, p.PasskeyError('save failed')]), patch.object(p, 'Pages', return_value=pages), patch.object(p, 'browser') as browser, patch('builtins.print'):
                browser.return_value.__enter__.return_value = Mock()
                with self.assertRaises(p.PasskeyError): p.setup(Mock(PORTAL_BASE='https://invalid/'), d, '/unused')
            with p.Gate(d) as gate: self.assertTrue(gate.state['dirty'])

    def test_user_action_stops_without_qr(self):
        with patch.object(p, 'login', side_effect=p.UserActionRequired('locked')), patch.object(cli, 'qr_login') as qr, patch.object(cli, 'runtime_dir', return_value='/unused'):
            with self.assertRaises(p.UserActionRequired): cli.fresh_login(Mock(qr=False))
            qr.assert_not_called()

    def test_locked_metadata_never_reads_secret(self):
        self.keyring.stop()
        result = Mock(returncode=0, stdout="(@ao [], [objectpath '/locked/item'])")
        with patch.object(p.subprocess, 'run', return_value=result) as run:
            with self.assertRaises(p.UserActionRequired): p.secret('lookup')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], 'gdbus')

    def test_authority_handoff_uses_latest_count(self):
        cdp = Mock()
        cdp.call.return_value = {'credentials': [dict(CRED, signCount=2)]}
        pages = p.Pages(cdp, CRED.copy())
        pages.attached = {'old': ('s1', 'a1'), 'new': ('s2', 'a2')}
        pages.activate('s1')
        pages.event({'method':'WebAuthn.credentialAsserted', 'params':{'credential':dict(CRED, signCount=2)}})
        cdp.reset_mock()
        pages.activate('s2')
        calls = cdp.call.call_args_list
        self.assertEqual([c.args[0] for c in calls], [
            'WebAuthn.setAutomaticPresenceSimulation', 'WebAuthn.getCredentials',
            'WebAuthn.removeCredential', 'WebAuthn.addCredential',
            'WebAuthn.setAutomaticPresenceSimulation'])
        self.assertFalse(calls[0].args[1]['enabled'])
        self.assertEqual(calls[3].args[1]['credential']['signCount'], 2)
        pages.event({'method':'WebAuthn.credentialAsserted', 'params':{'credential':dict(CRED, signCount=3)}})
        cdp.call.return_value = {'credentials':[dict(CRED, signCount=3)]}
        pages.activate('s1')
        self.assertEqual(cdp.call.call_args_list[-2].args[1]['credential']['signCount'], 3)

    def test_new_targets_have_no_credential_copy(self):
        def call(method, params=None, sid=None):
            if method == 'Target.getTargets': return {'targetInfos':[{'type':'page','targetId':'new'}]}
            if method == 'Target.attachToTarget': return {'sessionId':'s'}
            if method == 'WebAuthn.addVirtualAuthenticator': return {'authenticatorId':'a'}
            return {}
        cdp = Mock(); cdp.call.side_effect = call
        pages = p.Pages(cdp, CRED.copy()); pages.count = 2
        pages.refresh()
        self.assertNotIn('WebAuthn.addCredential', [c.args[0] for c in cdp.call.call_args_list])
        opts = cdp.call.call_args_list[-1].args[1]['options']
        self.assertFalse(opts['automaticPresenceSimulation'])

    def test_pipe_event_flood_hard_deadline(self):
        pipe = p.Pipe(10, 11)
        pipe.buffer = b'{"method":"event"}\0' * 100
        clock = iter([0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.1])
        with patch.object(p.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(p.select, 'select', return_value=([], [11], [])), patch.object(p.os, 'write', side_effect=lambda fd, data: len(data)):
            with self.assertRaisesRegex(p.PasskeyError, '逾時'): pipe.call('test', timeout=1)

    def test_pipe_segmented_read_partial_write_backpressure(self):
        pipe = p.Pipe(10, 11)
        written = []
        def write(fd, data):
            if not written:
                written.append(b''); raise BlockingIOError()
            written.append(data[:3]); return min(3, len(data))
        with patch.object(p.select, 'select', side_effect=lambda r,w,x,t: (r,w,[])), patch.object(p.os, 'write', side_effect=write), patch.object(p.os, 'read', side_effect=[b'{"id":', b'1,"result":', b'{"ok":true}}', b'\0']):
            self.assertEqual(pipe.call('test'), {'ok':True})
        self.assertTrue(b''.join(written).endswith(b'\0'))

    def test_pipe_eof(self):
        with patch.object(p.select, 'select', side_effect=lambda r,w,x,t: (r,w,[])), patch.object(p.os, 'write', side_effect=lambda fd,data:len(data)), patch.object(p.os, 'read', return_value=b''):
            with self.assertRaisesRegex(p.PasskeyError, '關閉'): p.Pipe(10,11).call('test')

    def test_pipe_late_response_rejected(self):
        pipe = p.Pipe(10,11); pipe.buffer = b'{"id":1,"result":{}}\0'
        with patch.object(p.time, 'monotonic', side_effect=[0,.1,.2,.3,.4,.5,2]), patch.object(p.select, 'select', return_value=([],[11],[])), patch.object(p.os, 'write', side_effect=lambda fd,data:len(data)):
            with self.assertRaises(p.PasskeyError): pipe.call('test', timeout=1)

    def test_cleanup_descendant_ignores_term(self):
        import subprocess
        script = ('import os,signal,time\n'
                  'pid=os.fork()\n'
                  'if pid==0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(60)\n'
                  'else:\n time.sleep(60)\n')
        child = subprocess.Popen([sys.executable,'-c',script], stdout=subprocess.PIPE, start_new_session=True)
        try:
            self.assertEqual(child.stdout.readline(), b'ready\n')
            p.stop_child(child, grace=.1)
            self.assertFalse(p.group_alive(child.pid))
            self.assertIsNotNone(child.poll())
        finally:
            p.stop_child(child, grace=.1)
            child.stdout.close()

    def test_store_locked_default_no_prompt(self):
        self.store_ready.stop()
        with patch.object(p.subprocess, 'run', side_effect=[Mock(returncode=0, stdout="(objectpath '/collection/default',)"), Mock(returncode=0, stdout='(<true>,)')]) as run:
            with self.assertRaises(p.UserActionRequired): p.secret('store', CRED)
            self.assertEqual(run.call_count, 2)
            self.assertTrue(all(c.args[0][0]=='gdbus' for c in run.call_args_list))

    def test_cleanup_chain_after_first_failure(self):
        before = len(list(Path('/proc/self/fd').iterdir()))
        with tempfile.TemporaryDirectory(dir='/run/user/'+str(os.getuid())) as d:
            with patch.object(p, 'browser_executable', return_value='/dummy'), patch.object(p, 'Pipe'), patch.object(p.subprocess, 'Popen', return_value=Mock()), patch.object(p, 'stop_child', side_effect=[p.PasskeyError('cleanup'), None]) as stop:
                with self.assertRaises(p.PasskeyError):
                    with p.browser(d, visible=True): pass
                self.assertEqual(stop.call_count, 2)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)

    def test_qr_has_shared_gate(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cli, 'config_dir', return_value=d), patch.object(cli, '_qr_login', return_value='qr'):
            self.assertEqual(cli.qr_login(10), 'qr')
            with p.Gate(d) as gate: self.assertEqual(gate.state, dict(dirty=False))


if __name__ == '__main__': unittest.main()
