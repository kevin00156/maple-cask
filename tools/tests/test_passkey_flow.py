"""Synthetic CDP loop: no secrets, website or production Gate/session."""
import contextlib
import os
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import maple_passkey as p

CRED = dict(credentialId='fixture', privateKey='fixture', userHandle='fixture', rpId=p.RP, signCount=1)

class FakeCDP:
    def __init__(self, hosts, click=True, assertion=False, captcha=False, click_error=False):
        self.hosts = iter(hosts); self.host = 'other'; self.click = click
        self.assertion = assertion
        self.captcha, self.click_error = captcha, click_error
        self.calls = []; self.on_event = lambda m: None
    def call(self, method, params=None, sid=None):
        self.calls.append((method, params, sid))
        if method == 'Target.getTargets':
            self.host = next(self.hosts, self.host)
            return {'targetInfos':[dict(type='page', targetId='fixture', url='https://'+self.host+'/')]}
        if method == 'Target.attachToTarget': return {'sessionId':'fixture-session'}
        if method == 'WebAuthn.addVirtualAuthenticator': return {'authenticatorId':'fixture-auth'}
        if method == 'WebAuthn.getCredentials': return {'credentials':[CRED.copy()]}
        if method == 'Runtime.evaluate':
            e = params['expression']
            if e == p.CAPTCHA_VISIBLE: v = self.captcha
            elif e in (p.GAMA_POINT, p.CLICK_GAMA, p.CLICK_PASS):
                if self.click_error:
                    raise p.PasskeyError('fixture click failure')
                v = dict(x=100, y=50) if e == p.GAMA_POINT and self.click else self.click
                if e == p.CLICK_PASS and self.assertion:
                    self.on_event(dict(method='WebAuthn.credentialAsserted', params=dict(credential=dict(CRED, signCount=3))))
            else: v = dict(host=p.host_class(self.host), gama=1, gama_visible=1, gama_ready=1, passkey=1, passkey_visible=1, passkey_ready=1, passkey_disabled=0)
            return {'result':{'value':v}}
        if method == 'Storage.getCookies': return {'cookies':[]}
        return {}

class FlowTests(unittest.TestCase):
    def run_flow(self, cdp, timeout=1, save_error=False, activate_error=False, sink=None, initial_state=None):
        api = Mock(PORTAL_BASE='https://tw.beanfun.com/', PORTAL_HOST='tw.beanfun.com')
        api.bfwebtoken.return_value = 'fixture-token'
        api.list_accounts.return_value = []
        records = []
        def diagnostic(record):
            records.append(record)
            if sink is not None:
                sink(record)
        clock = iter(i*.1 for i in range(1000))
        with tempfile.TemporaryDirectory() as d, patch.object(p, 'secret', side_effect=lambda action, value=None: (_ for _ in ()).throw(p.PasskeyError('fixture failure')) if action == 'store' and save_error else CRED.copy()) as keyring, patch.object(p, 'browser', return_value=contextlib.nullcontext(cdp)), patch.object(p.time, 'monotonic', side_effect=lambda:next(clock)), patch.object(p.time, 'sleep') as sleep, contextlib.ExitStack() as stack:
            if initial_state is not None:
                Path(d, 'passkey-state.json').write_text(json.dumps(initial_state))
            if activate_error:
                stack.enter_context(patch.object(p.Pages, 'activate', side_effect=p.PasskeyError('fixture activate failure')))
            try: result = p.login(api, d, '/unused', timeout=timeout, diagnostic=diagnostic)
            except Exception as exc: result = str(exc)
            self.last_dirty = json.loads(Path(d, 'passkey-state.json').read_text())['dirty']
            self.lock_state = json.loads(Path(d, 'passkey-state.json').read_text())
            self.sleep_calls = [c.args[0] for c in sleep.call_args_list]
            self.store_calls = sum(c.args[0] == 'store' for c in keyring.call_args_list)
        return result, records

    @staticmethod
    def failing_sink(record):
        raise OSError('fixture sink failure')

    def test_saved_summary_sink_failure_keeps_success_and_clean_gate(self):
        def sink(record):
            if record.get('saved') is True:
                self.failing_sink(record)
        result, records = self.run_flow(FakeCDP(['other', 'login.beanfun.com', p.RP, 'tw.beanfun.com']), sink=sink)
        self.assertIsInstance(result, tuple)
        self.assertEqual(self.store_calls, 1)
        self.assertFalse(self.last_dirty)
        self.assertFalse(any(r.get('saved') is False for r in records))

    def test_all_sink_failures_do_not_change_success(self):
        cdp = FakeCDP(['other', 'login.beanfun.com', p.RP, 'tw.beanfun.com'])
        result, records = self.run_flow(cdp, sink=self.failing_sink)
        self.assertIsInstance(result, tuple)
        self.assertTrue(any(r.get('pass_clicked') for r in records))
        self.assertEqual(self.store_calls, 1)
        self.assertFalse(self.last_dirty)

    def test_sink_failure_does_not_mask_actual_save_failure(self):
        result, records = self.run_flow(FakeCDP(['other', p.RP]), save_error=True, sink=self.failing_sink)
        self.assertIn('signCount 未能安全保存', result)
        self.assertEqual(records[-1], dict(saved=False, assertions=0))
        self.assertEqual(self.store_calls, 1)
        self.assertTrue(self.last_dirty)

    def test_sink_failure_preserves_original_timeout(self):
        result, records = self.run_flow(FakeCDP(['other', p.RP]), sink=self.failing_sink)
        self.assertIn('stage=1', result)
        self.assertEqual(records[-1], dict(saved=True, assertions=0))
        self.assertFalse(self.last_dirty)

    def test_captcha_stops_before_click_attempt(self):
        cdp = FakeCDP(['other', 'login.beanfun.com'], captcha=True)
        result, records = self.run_flow(cdp)
        self.assertIn('真人驗證', result)
        self.assertFalse(any(r.get('gama_attempted') or r.get('pass_attempted') for r in records))
        self.assertFalse(any(m == 'Runtime.evaluate' and v['expression'] in (p.CLICK_GAMA, p.CLICK_PASS) for m, v, _ in cdp.calls))

    def test_activate_failure_is_not_a_passkey_click_attempt(self):
        cdp = FakeCDP(['other', 'login.beanfun.com', p.RP])
        result, records = self.run_flow(cdp, activate_error=True)
        self.assertIn('activate failure', result)
        self.assertFalse(any(r.get('pass_attempted') for r in records))
        self.assertFalse(any(m == 'Runtime.evaluate' and v['expression'] == p.CLICK_PASS for m, v, _ in cdp.calls))

    def test_click_false_is_a_completed_attempt_not_a_click(self):
        result, records = self.run_flow(FakeCDP(['other', 'login.beanfun.com'], click=False))
        self.assertIn('stage=0', result)
        self.assertTrue(any(r.get('gama_attempted') and r.get('gama_result') == 'false' and not r['gama_clicked'] for r in records))

    def test_click_call_failure_is_recorded_without_sensitive_error(self):
        result, records = self.run_flow(FakeCDP(['other', 'login.beanfun.com'], click_error=True))
        self.assertIn('click failure', result)
        self.assertTrue(any(r.get('gama_attempted') and r.get('gama_result') == 'error' for r in records))
        self.assertNotIn('fixture', str(records))

    def test_direct_rp_is_observed_without_entry_click(self):
        result, records = self.run_flow(FakeCDP(['other', p.RP]))
        self.assertIn('stage=1', result)
        self.assertTrue(any(r.get('pass_clicked') for r in records))
        self.assertEqual(records[-1]['saved'], True)
        self.assertEqual(records[-1]['assertions'], 0)
        self.assertNotIn('fixture', str(records))

    def test_assertion_is_observed_and_saved(self):
        result, records = self.run_flow(FakeCDP(['other','login.beanfun.com',p.RP,'tw.beanfun.com'], assertion=True))
        self.assertIsInstance(result, tuple)
        self.assertEqual(records[-1], dict(saved=True, assertions=1))

    def test_save_failure_is_observed_and_stops(self):
        result, records = self.run_flow(FakeCDP(['other',p.RP]), save_error=True)
        self.assertIn('signCount 未能安全保存', result)
        self.assertEqual(records[-1], dict(saved=False, assertions=0))

    def test_true_click_without_navigation_stays_entry(self):
        cdp = FakeCDP(['other', 'login.beanfun.com'])
        result, records = self.run_flow(cdp)
        self.assertIn('stage=0', result)
        self.assertTrue(any(r.get('gama_clicked') for r in records))
        self.assertFalse(any(r.get('stage') == 1 for r in records))
        self.assertIn('未確認導航', result)

    def test_no_navigation_has_bounded_attempts(self):
        cdp = FakeCDP(['other', 'login.beanfun.com'])
        result, records = self.run_flow(cdp, timeout=10)
        self.assertIn('stage=0', result)
        clicks = [v for m, v, _ in cdp.calls if m == 'Input.dispatchMouseEvent' and v['type'] == 'mousePressed']
        self.assertEqual(len(clicks), 2)
        self.assertEqual(self.lock_state, dict(dirty=False))
        self.assertEqual(max(r.get('gama_attempts', 0) for r in records), 2)

    def test_return_to_entry_uses_observed_stage_and_counts_retry(self):
        cdp = FakeCDP(['other', 'login.beanfun.com', p.RP] + ['login.beanfun.com']*20 + [p.RP, 'tw.beanfun.com'])
        result, records = self.run_flow(cdp, timeout=10)
        self.assertIsInstance(result, tuple)
        self.assertEqual(self.lock_state, dict(dirty=False))
        self.assertTrue(any(r.get('stage') == 0 and r.get('gama_attempts') == 2 for r in records))

    def test_readiness_arrives_late_before_first_action(self):
        class LateReady(FakeCDP):
            def call(self, method, params=None, sid=None):
                result = super().call(method, params, sid)
                if method == 'Runtime.evaluate' and params['expression'] == p.OBSERVE:
                    result['result']['value'].update(gama_visible=int(len(self.calls) > 30), gama_ready=int(len(self.calls) > 30))
                return result
        cdp = LateReady(['other', 'login.beanfun.com'])
        result, records = self.run_flow(cdp, timeout=5)
        first = next(i for i, r in enumerate(records) if r.get('gama_attempted'))
        self.assertTrue(any(r.get('gama_visible') == 0 and not r.get('gama_attempted') for r in records[:first]))
        self.assertIn('stage=0', result)

    def test_successful_navigation_does_not_reclick_entry(self):
        cdp = FakeCDP(['other', 'login.beanfun.com', p.RP, 'tw.beanfun.com'])
        result, records = self.run_flow(cdp, timeout=10)
        self.assertIsInstance(result, tuple)
        self.assertEqual(self.lock_state, dict(dirty=False))
        self.assertEqual(sum(m == 'Input.dispatchMouseEvent' and v['type'] == 'mousePressed' for m, v, _ in cdp.calls), 1)
        self.assertTrue(any(r.get('navigation_confirmed') and r['stage'] == 1 for r in records))

    def test_multi_target_prefers_rp_over_leftover_entry(self):
        class Popup(FakeCDP):
            def call(self, method, params=None, sid=None):
                if method == 'Target.attachToTarget':
                    self.calls.append((method, params, sid))
                    return {'sessionId': params['targetId']}
                result = super().call(method, params, sid)
                if method == 'Target.getTargets' and self.host == p.RP:
                    result['targetInfos'].append(dict(type='page', targetId='entry', url='https://login.beanfun.com/'))
                if method == 'Runtime.evaluate' and params['expression'] == p.OBSERVE and sid == 'entry':
                    result['result']['value']['host'] = 'entry'
                return result
        cdp = Popup(['other', 'login.beanfun.com', p.RP, p.RP, 'tw.beanfun.com'])
        result, records = self.run_flow(cdp, timeout=10)
        self.assertIsInstance(result, tuple)
        self.assertFalse(any(m == 'Input.dispatchMouseEvent' and v['type'] == 'mousePressed' and sid == 'entry' for m, v, sid in cdp.calls))

    def test_hidden_disabled_backup_does_not_block_ready_passkey(self):
        class Backup(FakeCDP):
            def call(self, method, params=None, sid=None):
                result = super().call(method, params, sid)
                if method == 'Runtime.evaluate' and params['expression'] == p.OBSERVE:
                    result['result']['value'].update(passkey=2, passkey_visible=1, passkey_disabled=1, passkey_ready=1)
                return result
        result, records = self.run_flow(Backup(['other', p.RP]))
        self.assertTrue(any(r.get('pass_clicked') for r in records))

    def test_existing_portal_is_not_a_passkey_return(self):
        class LeftoverPortal(FakeCDP):
            def call(self, method, params=None, sid=None):
                if method == 'Target.attachToTarget':
                    return {'sessionId': params['targetId']}
                result = super().call(method, params, sid)
                if method == 'Target.getTargets':
                    result['targetInfos'].append(dict(type='page', targetId='leftover', url='https://tw.beanfun.com/'))
                if method == 'Runtime.evaluate' and params['expression'] == p.OBSERVE and sid == 'leftover':
                    result['result']['value']['host'] = 'portal'
                return result
        cdp = LeftoverPortal(['other', p.RP])
        result, records = self.run_flow(cdp)
        self.assertIsInstance(result, str)
        self.assertIn('stage=1', result)
        self.assertFalse(any(m == 'Storage.getCookies' for m, _, _ in cdp.calls))
        self.assertFalse(any(r.get('stage') == 2 for r in records))

    def test_new_portal_target_after_pass_is_a_return(self):
        class NewReturn(FakeCDP):
            def call(self, method, params=None, sid=None):
                if method == 'Target.attachToTarget':
                    return {'sessionId': params['targetId']}
                result = super().call(method, params, sid)
                if method == 'Target.getTargets':
                    result['targetInfos'].append(dict(type='page', targetId='leftover', url='https://tw.beanfun.com/'))
                    if self.host == 'tw.beanfun.com':
                        result['targetInfos'][0]['url'] = 'https://'+p.RP+'/'
                        result['targetInfos'].append(dict(type='page', targetId='new-return', url='https://tw.beanfun.com/'))
                if method == 'Runtime.evaluate' and params['expression'] == p.OBSERVE:
                    result['result']['value']['host'] = 'portal' if sid in ('leftover', 'new-return') else p.host_class(p.RP if self.host == 'tw.beanfun.com' else self.host)
                return result
        cdp = NewReturn(['other', p.RP, 'tw.beanfun.com'])
        result, records = self.run_flow(cdp)
        self.assertIsInstance(result, tuple)
        self.assertEqual(sum(m == 'Storage.getCookies' for m, _, _ in cdp.calls), 1)

    def test_legacy_count3_does_not_stop_bounded_repeat(self):
        cdp = FakeCDP(['other', 'login.beanfun.com'])
        state = dict(count=3, last=p.time.time(), dirty=False)
        result, records = self.run_flow(cdp, timeout=10, initial_state=state)
        self.assertIn('未確認導航', result)
        self.assertNotIn('限速', result)
        self.assertEqual(self.lock_state, state)
        self.assertEqual(sum(m == 'Input.dispatchMouseEvent' and v['type'] == 'mousePressed' for m, v, _ in cdp.calls), 2)
        self.assertFalse(self.last_dirty)

    def test_full_loop_success(self):
        result, records = self.run_flow(FakeCDP(['other','login.beanfun.com',p.RP,'tw.beanfun.com']))
        self.assertIsInstance(result, tuple)
        self.assertTrue(any(r.get('pass_clicked') for r in records))
        self.assertTrue(records[-1]['saved'])

    def test_clicked_without_navigation_stays_at_rp(self):
        result, records = self.run_flow(FakeCDP(['other','login.beanfun.com',p.RP]))
        self.assertIn('stage=1', result)
        self.assertEqual(sum(bool(r.get('pass_clicked')) for r in records), 1)
        self.assertEqual(records[-1]['assertions'], 0)

class LocalDOMTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MAPLE_LOCAL_DOM_TEST') == '1', 'explicit local Chromium fixture only')
    def test_visible_hidden_options_and_clicks(self):
        children, profiles = [], []
        popen = p.subprocess.Popen
        def tracked_popen(args, **kwargs):
            child = popen(args, **kwargs)
            children.append(child)
            profiles.extend(Path(arg.split('=', 1)[1]) for arg in args if arg.startswith('--user-data-dir='))
            return child
        with patch.object(p.subprocess, 'Popen', side_effect=tracked_popen), p.browser('/run/user/'+str(os.getuid())) as cdp:
            pages = p.Pages(cdp)
            targets = pages.refresh()
            sid = pages.attached[next(t['targetId'] for t in targets if t['type']=='page')][0]
            pages.js(sid, "document.body.innerHTML='<a onclick=\"window.g=(window.g||0)+1\">使用 gamapass</a><button onclick=\"window.p=(window.p||0)+1\">使用 Passkey</button><button style=\"display:none\">使用 Passkey</button>';true")
            observation = p.Diagnostics().observe(pages, sid)
            self.assertEqual(observation['passkey'], 2)
            self.assertEqual(observation['passkey_visible'], 1)
            records = []
            diag = p.Diagnostics(records.append)
            self.assertIs(diag.click(pages, sid, p.CLICK_GAMA, dict(stage=0), 'gama'), True)
            self.assertEqual(records[-1]['stage'], 0)
            self.assertTrue(records[-1]['gama_clicked'])
            self.assertIs(pages.js(sid, "location.href==='about:blank'"), True)
            self.assertIs(pages.js(sid, p.CLICK_PASS), True)
            self.assertIs(pages.js(sid, 'window.g===1 && window.p===1'), True)
        self.assertTrue(children)
        self.assertTrue(profiles)
        self.assertTrue(all(not p.group_alive(child.pid) for child in children))
        self.assertTrue(all(not profile.exists() for profile in profiles))

    @unittest.skipUnless(os.environ.get('MAPLE_LOCAL_DOM_TEST') == '1', 'explicit local Chromium fixture only')
    def test_ready_and_click_use_the_same_visible_enabled_candidate(self):
        with p.browser('/run/user/'+str(os.getuid())) as cdp:
            pages = p.Pages(cdp)
            targets = pages.refresh()
            sid = pages.attached[next(t['targetId'] for t in targets if t['type']=='page')][0]
            pages.js(sid, """document.body.innerHTML='<a style="display:none" onclick="window.hidden=true">使用 gamapass</a><a onclick="window.visible=true">使用 gamapass</a><button style="display:none" disabled>使用 Passkey</button><button disabled>使用 Passkey</button><button onclick="window.enabled=true">使用 Passkey</button>';true""")
            self.assertIs(pages.js(sid, p.CLICK_GAMA), True)
            self.assertIs(pages.js(sid, 'window.visible===true && window.hidden!==true'), True)
            observation = p.Diagnostics().observe(pages, sid)
            self.assertEqual(observation.get('passkey_ready'), 1)
            self.assertIs(pages.js(sid, p.CLICK_PASS), True)
            self.assertIs(pages.js(sid, 'window.enabled===true'), True)
            pages.js(sid, "document.querySelectorAll('button')[2].disabled=true;true")
            self.assertEqual(p.Diagnostics().observe(pages, sid).get('passkey_ready'), 0)
            self.assertIs(pages.js(sid, p.CLICK_PASS), False)

class PointerTests(unittest.TestCase):
    def test_normal_input_routes_coordinates_to_selected_session(self):
        cdp = Mock()
        pages = p.Pages(cdp)
        pages.js = Mock(return_value=dict(x=120.5, y=42))
        records = []
        self.assertIs(p.Diagnostics(records.append).click(pages, 'selected-session', p.CLICK_GAMA, {}, 'gama'), True)
        inputs = [c for c in cdp.call.call_args_list if c.args[0] == 'Input.dispatchMouseEvent']
        self.assertEqual(len(inputs), 2)
        self.assertEqual([c.args[1]['type'] for c in inputs], ['mousePressed', 'mouseReleased'])
        self.assertTrue(all(c.args[2] == 'selected-session' for c in inputs))
        self.assertTrue(all(c.args[1]['x'] == 120.5 and c.args[1]['y'] == 42 for c in inputs))
        self.assertEqual(records[-1]['gama_mode'], 'cdp_mouse')
        self.assertNotIn('x', records[-1])

    def test_release_failure_is_error_not_success(self):
        cdp = Mock()
        cdp.call.side_effect = [{}, p.PasskeyError('fixture failure')]
        pages = p.Pages(cdp)
        pages.js = Mock(return_value=dict(x=10, y=20))
        records = []
        with self.assertRaises(p.PasskeyError):
            p.Diagnostics(records.append).click(pages, 'selected-session', p.CLICK_GAMA, {}, 'gama')
        self.assertEqual(records[-1]['gama_result'], 'error')
        self.assertFalse(records[-1].get('gama_clicked', False))

    def test_invalid_coordinates_never_claim_input_call(self):
        for value in (False, None, dict(x=float('nan'), y=1), dict(x=True, y=1)):
            cdp = Mock()
            pages = p.Pages(cdp)
            pages.js = Mock(return_value=value)
            records = []
            self.assertIs(p.Diagnostics(records.append).click(pages, 'selected-session', p.CLICK_GAMA, {}, 'gama'), False)
            self.assertFalse(any(c.args[0] == 'Input.dispatchMouseEvent' for c in cdp.call.call_args_list))
            self.assertFalse(records[-1]['gama_clicked'])
            self.assertEqual(records[-1]['gama_mode'], 'cdp_mouse')

    @unittest.skipUnless(os.environ.get('MAPLE_LOCAL_DOM_TEST') == '1', 'explicit local Chromium fixture only')
    def test_trusted_pointer_navigation_frame_and_session_route(self):
        children, profiles = [], []
        popen = p.subprocess.Popen
        def tracked(args, **kwargs):
            child = popen(args, **kwargs)
            children.append(child)
            profiles.extend(Path(a.split('=', 1)[1]) for a in args if a.startswith('--user-data-dir='))
            return child
        with patch.object(p.subprocess, 'Popen', side_effect=tracked), p.browser('/run/user/'+str(os.getuid())) as cdp:
            pages = p.Pages(cdp)
            targets = pages.refresh()
            sid = pages.attached[next(t['targetId'] for t in targets if t['type']=='page')][0]
            # A different page must never receive the selected page's input.
            other = cdp.call('Target.createTarget', dict(url='about:blank'))['targetId']
            pages.refresh()
            other_sid = pages.attached[other][0]
            pages.js(other_sid, "document.body.innerHTML='<a onclick=\"window.wrong=true\">使用 gamapass</a>';true")
            cdp.call('Target.activateTarget', dict(targetId=targets[0]['targetId']))
            pages.js(sid, """document.body.innerHTML='<iframe></iframe><a style="display:none">使用 gamapass</a><a aria-disabled="true">使用 gamapass</a><a href="#completed">使用 gamapass</a>';window.trusted=0;document.querySelectorAll('a')[2].onclick=e=>{if(!e.isTrusted){e.preventDefault();return}window.trusted++};document.querySelector('iframe').contentDocument.body.innerHTML='<a onclick="window.wrong=true">使用 gamapass</a>';true""")
            self.assertIs(pages.js(sid, p.CLICK_GAMA), True)  # JS baseline: true is not completion.
            self.assertIs(pages.js(sid, "location.hash==='' && window.trusted===0"), True)
            records = []
            self.assertIs(p.Diagnostics(records.append).click(pages, sid, p.CLICK_GAMA, {}, 'gama'), True)
            self.assertIs(pages.js(sid, "location.hash==='#completed' && window.trusted===1 && document.querySelector('iframe').contentWindow.wrong!==true"), True)
            self.assertIs(pages.js(other_sid, 'window.wrong!==true'), True)
            self.assertEqual(records[-1]['gama_mode'], 'cdp_mouse')
            pages.js(sid, "document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;z-index:999\"></div>');true")
            self.assertIs(p.Diagnostics(records.append).click(pages, sid, p.CLICK_GAMA, {}, 'gama'), False)
            pages.js(sid, "document.querySelector('div').remove();true")
            pages.js(sid, "document.querySelectorAll('a')[2].setAttribute('aria-disabled','true');true")
            self.assertIs(p.Diagnostics(records.append).click(pages, sid, p.CLICK_GAMA, {}, 'gama'), False)
        self.assertTrue(all(not p.group_alive(c.pid) for c in children))
        self.assertTrue(profiles and all(not f.exists() for f in profiles))

class DiagnosticSafetyTests(unittest.TestCase):
    def test_observation_rejects_untrusted_fields(self):
        pages = Mock()
        pages.js.return_value = dict(host='https://secret/?token=secret', passkey=True,
                                    gama=-1, passkey_visible=1, cookie='secret')
        self.assertEqual(p.Diagnostics().observe(pages, 'fixture'),
                         dict(host='unknown', passkey_visible=1))

if __name__ == '__main__': unittest.main()

class SessionInterruptTests(unittest.TestCase):
    def test_unreturned_session_closed_on_interrupt(self):
        for target in ('bfwebtoken', 'list_accounts', 'sync'):
            for exception_type in (KeyboardInterrupt, SystemExit):
                with self.subTest(target=target, exception=exception_type.__name__):
                    api = Mock(PORTAL_BASE='https://tw.beanfun.com/',
                               DEFAULT_SERVICE_CODE='fixture', DEFAULT_SERVICE_REGION='fixture')
                    session = Mock()
                    api.new_session.return_value = session
                    api.bfwebtoken.return_value = 'fixture'
                    api.list_accounts.return_value = []
                    cdp = FakeCDP(['other', 'login.beanfun.com', p.RP, 'tw.beanfun.com'], assertion=True)
                    clock = iter(i*.1 for i in range(1000))
                    interruption = exception_type()
                    with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
                        keyring = stack.enter_context(patch.object(p, 'secret', return_value=CRED.copy()))
                        stack.enter_context(patch.object(p, 'browser', return_value=contextlib.nullcontext(cdp)))
                        stack.enter_context(patch.object(p.time, 'monotonic', side_effect=lambda:next(clock)))
                        stack.enter_context(patch.object(p.time, 'sleep'))
                        if target == 'sync':
                            stack.enter_context(patch.object(p.Pages, 'sync', side_effect=interruption))
                        else:
                            getattr(api, target).side_effect = interruption
                        with self.assertRaises(exception_type) as caught:
                            p.login(api, directory, '/unused', timeout=2, diagnostic=lambda record:None)
                        self.assertIs(caught.exception, interruption)
                        api.new_session.assert_called_once(); session.close.assert_called_once()
                        state = json.loads(Path(directory, 'passkey-state.json').read_text())
                        self.assertNotIn('count', state)
                        self.assertEqual(state['dirty'], target == 'sync')
                        self.assertEqual(sum(c.args[0]=='store' for c in keyring.call_args_list),
                                         0 if target == 'sync' else 1)


class QuietDiagnosticsTests(unittest.TestCase):
    """預設 sink：成功不印，失敗才把整段診斷倒到 stderr。"""
    def run_login(self, outcome):
        def fake(bfotp, directory, runtime, timeout, diag):
            diag.emit(dict(target=1, stage=0)); diag.emit(dict(target=1, stage=1))
            if isinstance(outcome, BaseException): raise outcome
            return outcome
        err = __import__('io').StringIO()
        with patch.object(p, '_login', side_effect=fake), patch('sys.stderr', err):
            try: result = p.login(Mock(), '/unused', '/unused')
            except BaseException as exc: result = exc
        return result, err.getvalue()

    def test_success_is_silent(self):
        result, err = self.run_login(('s', 't', []))
        self.assertEqual(result, ('s', 't', [])); self.assertEqual(err, '')

    def test_failure_flushes_held_records(self):
        for exc in (p.PasskeyError('fixture'), KeyboardInterrupt()):
            with self.subTest(exc=type(exc).__name__):
                result, err = self.run_login(exc)
                self.assertIs(result, exc)
                self.assertEqual(err.count('passkey 診斷：'), 2)
                self.assertIn('"stage": 1', err)
