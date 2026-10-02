"""Optional GamaPass helper. Secrets stay in memory/Secret Service, never diagnostics.

Only our Chromium child uses CDP (fd3/fd4, NUL JSON). No TCP debug port.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

ATTRS = ['service', 'maple-login', 'account', 'gamapass']
RP = 'accounts.gamania.com'
FIELDS = ('credentialId', 'rpId', 'privateKey', 'userHandle', 'signCount')
OPTIONS = dict(protocol='ctap2', transport='internal', hasResidentKey=True,
               hasUserVerification=True, isUserVerified=True, automaticPresenceSimulation=True)


class PasskeyError(Exception):
    """Only fixed, non-sensitive messages may leave this module."""


class PasskeyUnavailable(PasskeyError):
    """No dedicated credential/dependency; authentication has not been attempted."""


class UserActionRequired(PasskeyError):
    """Stop, do not automatically start another login flow."""


def keyring_available():
    """Search metadata only; never invoke Secret Service Unlock/Prompt."""
    try:
        r = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.secrets',
            '--object-path', '/org/freedesktop/secrets', '--method',
            'org.freedesktop.Secret.Service.SearchItems',
            "{'service': 'maple-login', 'account': 'gamapass'}"],
            capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        raise PasskeyUnavailable('缺少 gdbus（libglib2.0-bin）供不提示解鎖的前置檢查') from None
    except (OSError, subprocess.SubprocessError):
        raise UserActionRequired('無法確認 keyring 狀態；請使用者確認 Secret Service') from None
    lists = re.findall(r'\[([^\]]*)\]', r.stdout)
    if r.returncode or len(lists) != 2:
        raise UserActionRequired('無法確認 keyring 狀態；請使用者確認 Secret Service')
    if '/' in lists[1]:
        raise UserActionRequired('專用 passkey 所在 keyring 已鎖住；請使用者解鎖')
    return '/' in lists[0]


def keyring_store_ready():
    base = ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.secrets']
    try:
        alias = subprocess.run(base + ['--object-path', '/org/freedesktop/secrets',
            '--method', 'org.freedesktop.Secret.Service.ReadAlias', 'default'],
            capture_output=True, text=True, timeout=5)
        match = re.search(r"objectpath '([^']+)'", alias.stdout)
        if alias.returncode or not match or match[1] == '/':
            raise UserActionRequired('請使用者建立並解鎖預設 keyring')
        locked = subprocess.run(base + ['--object-path', match[1], '--method',
            'org.freedesktop.DBus.Properties.Get', 'org.freedesktop.Secret.Collection', 'Locked'],
            capture_output=True, text=True, timeout=5)
        if locked.returncode or locked.stdout.strip() != '(<false>,)':
            raise UserActionRequired('請使用者解鎖預設 keyring 後再保存')
    except (OSError, subprocess.SubprocessError):
        raise UserActionRequired('無法確認保存用 keyring；請使用者確認') from None


def secret(action, value=None):
    if not shutil.which('secret-tool'):
        raise PasskeyUnavailable('缺少 secret-tool')
    exists = keyring_available()
    if action == 'lookup' and not exists:
        return None
    cmd = ['secret-tool', action]
    if action == 'store':
        keyring_store_ready()
        cmd += ['--label=maple-login GamaPass passkey']
    try:
        r = subprocess.run(cmd + ATTRS, input=json.dumps(value).encode() if value else None,
                           capture_output=True, timeout=15)
    except FileNotFoundError:
        raise PasskeyUnavailable('缺少 secret-tool') from None
    except (OSError, subprocess.SubprocessError):
        raise UserActionRequired('Secret Service 無法完成；請使用者確認或解鎖') from None
    if action == 'lookup' and not r.stdout.strip() and r.returncode == 1:
        return None
    if r.returncode:
        raise UserActionRequired('keyring 讀取/保存失敗；請使用者確認已解鎖')
    if action == 'store':
        if secret('lookup') != value:
            raise PasskeyError('keyring 保存驗證失敗')
        return None
    try:
        c = json.loads(r.stdout)
        if not all(c.get(k) for k in FIELDS[:-1]) or c['rpId'] != RP:
            raise ValueError()
        if type(c['signCount']) is not int or c['signCount'] < 0:
            raise ValueError()
        return {k: c[k] for k in FIELDS}
    except (ValueError, KeyError, TypeError):
        raise PasskeyError('keyring 憑證格式無效') from None


def browser_executable():
    # Resolve known Chromium desktop IDs only; never execute arbitrary desktop Exec.
    names = ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable',
             'brave-browser', 'brave', 'microsoft-edge']
    preferred = None
    try:
        desktop = subprocess.run(['xdg-settings', 'get', 'default-web-browser'],
                                 capture_output=True, text=True, timeout=3).stdout.lower()
        preferred = next((n for marker, n in (
            ('brave', 'brave-browser'), ('chromium', 'chromium'),
            ('google-chrome', 'google-chrome'), ('edge', 'microsoft-edge'))
            if marker in desktop), None)
        if preferred:
            names.remove(preferred)
            names.insert(0, preferred)
    except (OSError, subprocess.SubprocessError):
        pass
    if preferred:
        aliases = {'brave-browser': 'brave', 'chromium': 'chromium-browser',
                   'google-chrome': 'google-chrome-stable'}
        alias = aliases.get(preferred)
        if alias:
            names.remove(alias)
            names.insert(1, alias)
    for n in names:
        if shutil.which(n):
            return shutil.which(n)
    raise PasskeyUnavailable('沒有可用的 Chromium 瀏覽器')


def group_alive(pgid):
    # Zombies cannot hold profile/fds. Linux /proc lets us exclude them even
    # when PID 1 has not reaped orphan descendants yet.
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry/'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == pgid and fields[0] != 'Z':
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def stop_child(p, grace=5):
    if p is None:
        return
    def send(sig):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            pass
    send(signal.SIGTERM)
    end = time.monotonic() + grace
    while group_alive(p.pid) and time.monotonic() < end:
        p.poll()
        time.sleep(.05)
    if group_alive(p.pid):
        send(signal.SIGKILL)
    end = time.monotonic() + 5
    while group_alive(p.pid) and time.monotonic() < end:
        p.poll()
        time.sleep(.05)
    p.wait(timeout=5)
    if group_alive(p.pid):
        raise PasskeyError('自己的瀏覽器子行程未能清理')


class Pipe:
    def __init__(self, read_fd, write_fd):
        self.read_fd, self.write_fd = read_fd, write_fd
        self.buffer = b''
        self.seq = 0
        self.on_event = lambda message: None

    def call(self, method, params=None, sid=None, timeout=15):
        self.seq += 1
        ident = self.seq
        msg = dict(id=ident, method=method, params=params or {})
        if sid:
            msg['sessionId'] = sid
        data = json.dumps(msg).encode() + b'\0'
        # Pipe writes may be partial; bounded nonblocking writes and reads.
        end = time.monotonic() + timeout
        def remaining():
            left = end - time.monotonic()
            if left <= 0:
                raise PasskeyError('CDP 指令逾時')
            return left

        while data:
            remaining()
            if not select.select([], [self.write_fd], [], remaining())[1]:
                raise PasskeyError('CDP 寫入逾時')
            remaining()
            try:
                written = os.write(self.write_fd, data)
                if not written:
                    raise PasskeyError('瀏覽器 pipe 已關閉')
                data = data[written:]
            except BlockingIOError:
                continue
        while True:
            remaining()
            while b'\0' in self.buffer:
                remaining()
                raw, self.buffer = self.buffer.split(b'\0', 1)
                m = json.loads(raw)
                remaining()
                if m.get('id') == ident:
                    if 'error' in m:
                        raise PasskeyError('CDP 指令失敗')
                    return m.get('result', {})
                if 'method' in m:
                    self.on_event(m)
            if not select.select([self.read_fd], [], [], remaining())[0]:
                raise PasskeyError('CDP 回應逾時')
            remaining()
            chunk = os.read(self.read_fd, 65536)
            if not chunk:
                raise PasskeyError('瀏覽器 pipe 已關閉')
            self.buffer += chunk


def tmpfs_path(path):
    resolved = str(Path(path).resolve())
    mounts = []
    with open('/proc/self/mountinfo') as f:
        for line in f:
            left, right = line.split(' - ', 1)
            mount = left.split()[4].replace('\\040', ' ')
            if resolved == mount or resolved.startswith(mount.rstrip('/') + '/'):
                mounts.append((len(mount), right.split()[0]))
    return bool(mounts) and max(mounts)[1] == 'tmpfs'


@contextlib.contextmanager
def browser(runtime, visible=False):
    exe = browser_executable()
    # tmpfs is mandatory: Chromium itself writes cookies/profile state.
    if not str(Path(runtime).resolve()).startswith('/run/user/') or not tmpfs_path(runtime):
        raise PasskeyError('瀏覽器 profile 需要 /run/user 下的 tmpfs runtime')
    os.makedirs(runtime, mode=0o700, exist_ok=True)
    xvfb = child = None
    fds = []
    with tempfile.TemporaryDirectory(prefix='passkey-', dir=runtime) as profile:
        try:
            env = os.environ.copy()
            if not visible and shutil.which('Xvfb'):
                # -displayfd asks Xvfb for an unused display, no global process cleanup.
                r, w = os.pipe(); fds += [r, w]
                xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(w), '-screen', '0', '1280x800x24', '-nolisten', 'tcp'],
                                        pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                os.close(w); fds.remove(w)
                if not select.select([r], [], [], 5)[0]:
                    raise PasskeyError('Xvfb 啟動逾時')
                display = os.read(r, 32).decode().strip()
                if not display.isdigit():
                    raise PasskeyError('Xvfb 啟動失敗')
                env['DISPLAY'] = ':' + display
            r, w = os.pipe(); rr, ww = os.pipe(); fds += [r, w, rr, ww]
            child = subprocess.Popen(['bash', '-c',
                'exec 3<&"$1" 4>&"$2"; shift 2; exec "$@"', 'cdp', str(r), str(ww), exe,
                '--remote-debugging-pipe', '--user-data-dir=' + profile,
                '--no-first-run', '--no-default-browser-check', 'about:blank'],
                pass_fds=(r, ww), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            for fd in (r, ww):
                os.close(fd); fds.remove(fd)
            os.set_blocking(w, False)
            cdp = Pipe(rr, w)
            cdp.call('Browser.getVersion')
            yield cdp
        finally:
            try:
                stop_child(child)
            finally:
                try:
                    stop_child(xvfb)
                finally:
                    for fd in fds:
                        with contextlib.suppress(OSError):
                            os.close(fd)


class CredentialLock:
    """Persistent nonsecret state; one lock spans credential read/assert/save.

    dirty remains set after an unclean exit/save failure, so stale counters cannot
    silently be reused. Recovery requires registering a new credential via setup.
    """
    def __init__(self, directory):
        self.directory = Path(directory)

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fd = os.open(self.directory/'passkey.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = self.directory/'passkey-state.json'
            self.state = json.loads(path.read_text()) if path.exists() else dict(dirty=False)
            # Legacy count/last are inert: validate only credential safety state.
            if not isinstance(self.state, dict) or type(self.state['dirty']) is not bool:
                raise ValueError()
            return self
        except (OSError, ValueError, KeyError, TypeError):
            os.close(self.fd)
            raise PasskeyError('憑證忙碌或安全狀態無效；不進行登入') from None

    def save(self):
        fd, tmp = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self.state, f); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.directory/'passkey-state.json')
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def __exit__(self, *exc):
        os.close(self.fd)


# Compatibility for callers using the previous lock name; no quota API.
Gate = CredentialLock


class NavigationTimeout(UserActionRequired):
    """Stop automatic fallback on unconfirmed navigation, not a human challenge."""


class Pages:
    def __init__(self, cdp, credential=None):
        self.cdp, self.credential = cdp, credential
        self.attached = {}
        self.count = credential['signCount'] if credential else 0
        self.active = None
        self.assertions = 0
        cdp.on_event = self.event

    def event(self, m):
        if m.get('method') == 'WebAuthn.credentialAsserted':
            self.assertions += 1
            self.count = max(self.count, m['params']['credential']['signCount'])

    def refresh(self):
        targets = self.cdp.call('Target.getTargets')['targetInfos']
        for t in targets:
            if t['type'] != 'page' or t['targetId'] in self.attached:
                continue
            sid = self.cdp.call('Target.attachToTarget', dict(targetId=t['targetId'], flatten=True))['sessionId']
            self.cdp.call('WebAuthn.enable', dict(enableUI=False), sid)
            options = dict(OPTIONS, automaticPresenceSimulation=not bool(self.credential))
            auth = self.cdp.call('WebAuthn.addVirtualAuthenticator', dict(options=options), sid)['authenticatorId']
            self.attached[t['targetId']] = (sid, auth)
        return targets

    def activate(self, sid):
        """Move the sole assertion-capable credential, never clone counters.

        Disable old presence, poll its final count, remove it, then seed the new
        authenticator. Any handoff failure aborts rather than enabling a copy.
        No CDP calls inside event callbacks (Pipe is deliberately synchronous).
        """
        if not self.credential or self.active and self.active[0] == sid:
            return
        if self.active:
            oldsid, oldauth = self.active
            self.cdp.call('WebAuthn.setAutomaticPresenceSimulation',
                          dict(authenticatorId=oldauth, enabled=False), oldsid)
            creds = self.cdp.call('WebAuthn.getCredentials', dict(authenticatorId=oldauth), oldsid)['credentials']
            mine = next(c for c in creds if c['credentialId'] == self.credential['credentialId'])
            self.count = max(self.count, mine['signCount'])
            self.cdp.call('WebAuthn.removeCredential',
                          dict(authenticatorId=oldauth, credentialId=self.credential['credentialId']), oldsid)
            self.active = None
        auth = next(auth for s, auth in self.attached.values() if s == sid)
        self.cdp.call('WebAuthn.addCredential', dict(authenticatorId=auth,
                      credential=dict(self.credential, signCount=self.count, isResidentCredential=True)), sid)
        self.active = (sid, auth)
        self.cdp.call('WebAuthn.setAutomaticPresenceSimulation', dict(authenticatorId=auth, enabled=True), sid)

    def js(self, sid, expression):
        return self.cdp.call('Runtime.evaluate', dict(expression=expression, returnByValue=True), sid).get('result', {}).get('value')

    def pointer_click(self, sid):
        """Normal CDP press/release on the same ready main-document anchor.

        Coordinates stay in memory. Completion here means input was sent, not
        navigation, user activation, or an assertion. No event properties forged.
        """
        point = self.js(sid, GAMA_POINT)
        if not isinstance(point, dict) or not all(
                type(point.get(k)) in (int, float) and math.isfinite(point[k]) and point[k] >= 0
                for k in ('x', 'y')):
            return False
        for kind in ('mousePressed', 'mouseReleased'):
            self.cdp.call('Input.dispatchMouseEvent', dict(type=kind, x=point['x'], y=point['y'],
                          button='left', buttons=1 if kind == 'mousePressed' else 0, clickCount=1), sid)
        return True

    def credentials(self, strict=False):
        values = []
        sources = ([self.active] if self.active else []) if self.credential else self.attached.values()
        for sid, auth in sources:
            try:
                values += self.cdp.call('WebAuthn.getCredentials', dict(authenticatorId=auth), sid)['credentials']
            except PasskeyError:
                if strict:
                    raise PasskeyError('無法確認 signCount；暫停 passkey 直到重新註冊') from None
                continue  # setup may have closed a tab
        return values

    def sync(self):
        found = False
        for c in self.credentials(strict=True):
            if c['credentialId'] == self.credential['credentialId']:
                found = True
                self.count = max(self.count, c['signCount'])
        if not found and self.active:
            raise PasskeyError('無法確認憑證計數；請重新 setup 或使用 QR')
        self.credential['signCount'] = self.count
        secret('store', self.credential)


CAPTCHA_VISIBLE = """(() => [...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.cf-turnstile')].some(e => {const r=e.getBoundingClientRect();return r.width>0 && r.height>0 && getComputedStyle(e).visibility!='hidden'}))()"""


# Observation and the click seam must qualify exactly the same candidates.
# Recheck at click time: readiness may change after observation.
DOM_CANDIDATES = """
 const visible=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);
   return r.width>0 && r.height>0 && s.visibility!='hidden' && s.display!='none'};
 const ready=e=>visible(e) && !e.disabled && e.getAttribute('aria-disabled')!='true';
 const g=[...document.querySelectorAll('a')].filter(e=>e.textContent.includes('使用 gamapass'));
 const p=[...document.querySelectorAll('button')].filter(e=>e.textContent.includes('使用 Passkey'));
"""
CLICK_GAMA = "(() => {" + DOM_CANDIDATES + "let e=g.find(ready);if(!e)return false;e.click();return true})()"
GAMA_POINT = "(() => {" + DOM_CANDIDATES + """
 const e=g.find(ready);if(!e)return false;
 e.scrollIntoView({block:'center',inline:'center'});
 if(!ready(e))return false;
 const r=e.getBoundingClientRect();
 const x=(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2;
 const y=(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;
 const hit=document.elementFromPoint(x,y);
 if(x<0||y<0||x>=innerWidth||y>=innerHeight||!hit||!(hit===e||e.contains(hit)))return false;
 return {x,y};
})()"""
CLICK_PASS = "(() => {" + DOM_CANDIDATES + "let e=p.find(ready);if(!e)return false;e.click();return true})()"


def host_class(host):
    return {'login.beanfun.com': 'entry', RP: 'rp', 'tw.beanfun.com': 'portal'}.get(host, 'other')


# Only aggregate counts/fixed classifications cross the JS boundary. No DOM/URL.
OBSERVE = "(() => {" + DOM_CANDIDATES + """
 return {host:({'login.beanfun.com':'entry','accounts.gamania.com':'rp','tw.beanfun.com':'portal'})[location.hostname]||'other',
 iframes:document.querySelectorAll('iframe').length,
 gama:g.length,gama_visible:g.filter(visible).length,gama_ready:g.filter(ready).length,
 passkey:p.length,passkey_visible:p.filter(visible).length,passkey_ready:p.filter(ready).length,
 passkey_disabled:p.filter(e=>e.disabled).length};
})()"""


class Diagnostics:
    def __init__(self, sink=None):
        # 沒給 sink 就先存著，只在登入失敗時 flush 到 stderr；成功不出聲。
        self.held = []
        self.sink = sink or self.held.append
        self.last = {}

    def flush(self):
        for record in self.held:
            print('passkey 診斷：'+json.dumps(record, ensure_ascii=False), file=sys.stderr)
        self.held.clear()

    def emit(self, record):
        # All callers supply only fixed strings/integers/booleans. Never serialize
        # an evaluate response or target object directly, including on failure.
        key = record.get('target', 'summary')
        if self.last.get(key) != record:
            self.last[key] = record.copy()
            try:
                self.sink(record.copy())
            except Exception:
                # Best-effort diagnostics must never change login, click or
                # persistence outcomes. Do not print a possibly sensitive sink
                # exception, nor retry it through another failing output path.
                pass

    def click(self, pages, sid, expression, record, option):
        """Attempt means a real locator/input or JS call, never branch entry.

        True means the press/release pair was sent (entry) or JS .click() was
        called (Passkey); neither proves navigation or an assertion.
        """
        record = dict(record)
        pointer = expression == CLICK_GAMA
        record[option+'_mode'] = 'cdp_mouse' if pointer else 'js_click'
        record[option+'_attempted'] = True
        record[option+'_result'] = 'calling'
        self.emit(record)
        try:
            result = pages.pointer_click(sid) if pointer else pages.js(sid, expression)
        except Exception:
            record[option+'_result'] = 'error'
            record['assertions'] = pages.assertions
            self.emit(record)
            raise
        clicked = bool(result)
        record[option+'_clicked'] = clicked
        record[option+'_result'] = 'true' if clicked else 'false' if result is False else 'no_value'
        record['assertions'] = pages.assertions
        self.emit(record)
        return result

    def observe(self, pages, sid):
        value = pages.js(sid, OBSERVE)
        result = {'host': 'unknown'}
        if isinstance(value, dict):
            if value.get('host') in ('entry', 'rp', 'portal', 'other'):
                result['host'] = value['host']
            for k in ('iframes', 'gama', 'gama_visible', 'passkey', 'passkey_visible', 'passkey_disabled', 'gama_ready', 'passkey_ready'):
                n = value.get(k)
                if type(n) is int and 0 <= n <= 10000:
                    result[k] = n
        return result


def login(bfotp, directory, runtime, timeout=90, diagnostic=None):
    diag = Diagnostics(diagnostic)
    try:
        return _login(bfotp, directory, runtime, timeout, diag)
    except BaseException:
        diag.flush()
        raise


def _login(bfotp, directory, runtime, timeout, diag):
    with CredentialLock(directory) as gate:
        if gate.state['dirty']:
            raise PasskeyError('上次 signCount 未安全保存；請重新 passkey-setup 或使用 QR')
        cred = secret('lookup')
        if cred is None:
            raise PasskeyUnavailable('沒有專用 passkey')
        with browser(runtime) as cdp:
            pages = Pages(cdp, cred)
            targets = pages.refresh()
            sid = pages.attached[next(t['targetId'] for t in targets if t['type']=='page')][0]
            gate.state['dirty'] = True; gate.save()
            session = None
            try:
                cdp.call('Page.navigate', dict(url=bfotp.PORTAL_BASE+'beanfun_block/bflogin/default.aspx?service=999999_T0'), sid)
                end = time.monotonic()+timeout
                stage = 0
                ordinals = {}
                attempts = dict(gama=0, passkey=0)
                last_attempt = dict(gama=-float('inf'), passkey=-float('inf'))
                pass_sent = False
                portal_before_pass = set()
                previous_host = None
                pass_visit_clicked = False
                while time.monotonic() < end:
                    targets = pages.refresh()
                    target_count = sum(t['type'] == 'page' for t in targets)
                    observed = []
                    for t in targets:
                        if t['targetId'] not in pages.attached:
                            continue
                        s = pages.attached[t['targetId']][0]
                        snapshot = host_class(urlsplit(t.get('url', '')).hostname)
                        ordinal = ordinals.setdefault(t['targetId'], len(ordinals)+1)
                        observation = diag.observe(pages, s)
                        observed.append((s, snapshot, ordinal, observation))
                    # Prefer the advanced document over an entry tab left behind
                    # by a popup. Require both snapshots to agree before acting.
                    eligible = [item for item in observed if item[1] == item[3]['host']]
                    # A portal already present when pass was clicked is not
                    # evidence of this login's return. Only a document reaching
                    # portal after the action (or a new portal target) qualifies.
                    priority = {'entry': 0, 'rp': 1, 'portal': 2}
                    selected = max((item for item in eligible if item[1] in priority and
                                    (item[1] != 'portal' or pass_sent and item[0] not in portal_before_pass)),
                                   key=lambda item: priority[item[1]], default=None)
                    if selected:
                        current_host = selected[1]
                        stage = {'entry': 0, 'rp': 1, 'portal': 2 if pass_sent else 0}[current_host]
                        if current_host != previous_host:
                            pass_visit_clicked = False
                        previous_host = current_host
                    for s, snapshot, ordinal, observation in observed:
                        record = dict(observation, snapshot_host=snapshot, target=ordinal,
                                      targets=target_count, stage=stage,
                                      navigation_confirmed=bool(selected and selected[1] in ('rp', 'portal') and stage > 0),
                                      gama_attempts=attempts['gama'], pass_attempts=attempts['passkey'],
                                      gama_attempted=False, pass_attempted=False,
                                      gama_result='not_run', pass_result='not_run',
                                      gama_clicked=False, pass_clicked=False, assertions=pages.assertions)
                        diag.emit(record)
                        if snapshot in ('entry', 'rp') and pages.js(s, CAPTCHA_VISIBLE):
                            raise UserActionRequired('網站要求真人驗證；請使用者操作，不自動重試')
                        if not selected or s != selected[0]:
                            continue
                        option = 'gama' if snapshot == 'entry' else 'passkey'
                        ready = observation.get(option+'_ready', 0) > 0
                        now = time.monotonic()
                        # At most two calls per option across ALL targets, with a
                        # three-second navigation/readiness grace. This is a
                        # command-local bound, not a persistent user cooldown.
                        if snapshot in ('entry', 'rp') and ready and attempts[option] < 2 and now-last_attempt[option] >= 3 and not (option == 'passkey' and pass_visit_clicked):
                            if option == 'passkey':
                                pages.activate(s)
                            attempts[option] += 1
                            last_attempt[option] = now
                            record['gama_attempts'] = attempts['gama']
                            record['pass_attempts'] = attempts['passkey']
                            clicked = diag.click(pages, s, CLICK_GAMA if option == 'gama' else CLICK_PASS,
                                                 record, 'gama' if option == 'gama' else 'pass')
                            if option == 'passkey' and clicked:
                                portal_before_pass = {item[0] for item in observed
                                                      if item[1] == 'portal' or item[3]['host'] == 'portal'}
                                pass_sent = pass_visit_clicked = True
                        elif snapshot == 'portal' and pass_sent:
                            cookies = cdp.call('Storage.getCookies')['cookies']
                            session = bfotp.new_session()
                            try:
                                for c in cookies:
                                    domain = c['domain'].lstrip('.')
                                    if domain == 'beanfun.com' or domain.endswith('.beanfun.com'):
                                        session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
                                token = bfotp.bfwebtoken(session)
                                if not token:
                                    raise PasskeyError('網站未完成登入')
                                accounts = bfotp.list_accounts(session, token, bfotp.DEFAULT_SERVICE_CODE, bfotp.DEFAULT_SERVICE_REGION)
                                return session, token, accounts
                            except BaseException:
                                # 尚未交付呼叫端：中止亦須清理，仍由 finally 同步計數。
                                session.close()
                                session = None
                                raise
                    time.sleep(.3)
                raise NavigationTimeout(f'passkey 登入逾時：未確認導航或登入完成，stage={stage}，assertions={pages.assertions}；不自動重試')
            finally:
                try:
                    pages.sync()  # includes assertions followed by website/API failure
                    gate.state['dirty'] = False; gate.save()
                except (KeyboardInterrupt, SystemExit):
                    if session is not None:
                        session.close()
                    raise  # 不清 dirty、不重試；保留原始中止訊號。
                except Exception:
                    diag.emit(dict(saved=False, assertions=pages.assertions))
                    if session is not None:
                        session.close()
                    raise UserActionRequired('signCount 未能安全保存；請使用者確認 keyring，暫停登入') from None
                else:
                    # Output is not part of the persistence transaction.
                    diag.emit(dict(saved=True, assertions=pages.assertions))


def setup(bfotp, directory, runtime, timeout=900):
    with CredentialLock(directory) as gate:
        if secret('lookup') is not None:
            if input('已有專用憑證（不刪除）；註冊新的一把並取代 keyring？輸入 yes：') != 'yes':
                raise PasskeyError('未取代既有憑證')
        print('請在新視窗自行登入、處理確認/CAPTCHA，並新增一把 maple-login 專用 passkey。不要選 Bitwarden。')
        with browser(runtime, visible=True) as cdp:
            pages = Pages(cdp)
            targets = pages.refresh()
            sid = pages.attached[next(t['targetId'] for t in targets if t['type']=='page')][0]
            cdp.call('Page.navigate', dict(url=bfotp.PORTAL_BASE+'beanfun_block/bflogin/default.aspx?service=999999_T0'), sid)
            end = time.monotonic()+timeout
            while time.monotonic() < end:
                pages.refresh()
                for c in pages.credentials():
                    if c.get('rpId') == RP:
                        secret('store', {k: c[k] for k in FIELDS})
                        gate.state['dirty'] = False; gate.save()
                        print('專用 passkey 已存入 Secret Service。')
                        return
                time.sleep(.3)
            raise PasskeyError('註冊逾時；未保存憑證')
