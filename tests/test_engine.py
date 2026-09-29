import copy
import tempfile
import unittest

from tvbakim.demo import DemoAdb, DemoDevice
from tvbakim.engine import Engine, PlanError
from tvbakim.store import Store

SERIAL = 'demo-tv'
SETTING = {'type': 'setting', 'namespace': 'global', 'key': 'window_animation_scale', 'value': '0.5'}
PACKAGE = {'type': 'package', 'package': 'com.tcl.browser', 'value': 'disabled-user'}


class TracedAdb(DemoAdb):
    def __init__(self):
        super().__init__()
        self.writes = []
        self.fail_write = None
        self.fail_after_write = False
    def shell(self, serial, args, timeout=20):
        writing = args[0] == 'settings' and args[3] in ('put', 'delete') or args[0] == 'pm' and args[1] in ('enable', 'disable-user', 'default-state', 'disable', 'disable-until-used')
        if writing:
            self.writes.append(list(args))
            if self.fail_write == len(self.writes) and not self.fail_after_write:
                raise RuntimeError('injected transport failure')
        result = super().shell(serial, args, timeout)
        if writing and self.fail_write == len(self.writes) and self.fail_after_write:
            raise RuntimeError('injected response lost after write')
        return result


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.adb = TracedAdb()
        self.now = 1000
        self.engine = Engine(self.adb, self.store, DemoDevice, clock=lambda: self.now)

    def test_apply_and_rollback_preserve_absent_setting_and_default_package(self):
        self.adb.settings.pop(('global', 'window_animation_scale'))
        plan = self.engine.plan(SERIAL, [SETTING, PACKAGE])
        self.assertEqual(self.adb.writes, [])
        record = self.engine.apply(plan['id'], True)
        self.assertEqual(record['status'], 'succeeded')
        self.assertEqual(self.adb.package_states['com.tcl.browser'], 'disabled-user')
        restore = self.engine.rollback_plan(record['id'], SERIAL)
        restored = self.engine.apply(restore['id'], True)
        self.assertEqual(restored['status'], 'succeeded')
        self.assertNotIn(('global', 'window_animation_scale'), self.adb.settings)
        self.assertEqual(self.adb.package_states['com.tcl.browser'], 'default')
        self.assertEqual(self.store.get(record['id'])['rolled_back_by'], restored['id'])

    def test_noop_and_plan_do_not_mutate_or_create_journal(self):
        request = dict(SETTING, value='1.0')
        with self.assertRaises(PlanError): self.engine.plan(SERIAL, [request])
        self.assertEqual(self.adb.writes, [])
        self.assertEqual(self.store.history(), [])

    def test_public_plan_copy_cannot_change_stored_actions(self):
        plan = self.engine.plan(SERIAL, [SETTING])
        plan['actions'][0]['after']['value'] = '0'
        self.engine.apply(plan['id'], True)
        self.assertEqual(self.adb.settings[('global', 'window_animation_scale')], '0.5')

    def test_corrupt_journals_do_not_break_startup_recovery(self):
        from pathlib import Path
        for index, text in enumerate(['[]', 'null', '"bad"', '{invalid', '{}']):
            (Path(self.tmp.name) / (f'{index:032x}' + '.json')).write_text(text)
        self.store.recover()
        self.assertEqual(len(self.store.history()), 5)
        self.assertTrue(all(row['status'] == 'unreadable' for row in self.store.history()))

    def test_replay_and_expiry_rejected(self):
        plan = self.engine.plan(SERIAL, [SETTING])
        self.engine.apply(plan['id'], True)
        with self.assertRaises(PlanError): self.engine.apply(plan['id'], True)
        other = self.engine.plan(SERIAL, [dict(SETTING, value='0')])
        self.now += 901
        with self.assertRaises(PlanError): self.engine.apply(other['id'], True)
        self.assertEqual(len(self.adb.writes), 1)

    def test_explicit_confirmation_required(self):
        plan = self.engine.plan(SERIAL, [SETTING])
        for confirmation in [False, None, 'true', 1]:
            with self.assertRaises(PlanError): self.engine.apply(plan['id'], confirmation)
        self.assertEqual(self.adb.writes, [])

    def test_all_before_values_checked_before_first_write(self):
        plan = self.engine.plan(SERIAL, [SETTING, PACKAGE])
        self.adb.package_states['com.tcl.browser'] = 'enabled'
        with self.assertRaises(PlanError): self.engine.apply(plan['id'], True)
        self.assertEqual(self.adb.writes, [])

    def test_wrong_device_or_firmware_never_writes(self):
        plan = self.engine.plan(SERIAL, [SETTING])
        class ChangedDevice(DemoDevice):
            def inspect(self):
                result = super().inspect()
                result['identity']['fingerprint'] = 'other firmware'
                return result
        self.engine.device_factory = ChangedDevice
        with self.assertRaises(PlanError): self.engine.apply(plan['id'], True)
        self.assertEqual(self.adb.writes, [])

    def test_secondary_user_cannot_create_write_plan(self):
        class SecondaryUser(DemoDevice):
            def inspect(self):
                info = super().inspect()
                info['capabilities'].update(owner_user=False, current_user=10)
                return info
        self.engine.device_factory = SecondaryUser
        with self.assertRaises(PlanError): self.engine.plan(SERIAL, [SETTING])
        self.assertEqual(self.adb.writes, [])

    def test_protected_unknown_and_injected_settings_rejected(self):
        for request in [dict(PACKAGE, package='com.android.systemui'), dict(PACKAGE, package='com.unknown.app'), dict(PACKAGE, package='com.google.android.katniss'), dict(SETTING, key='adb_enabled'), dict(SETTING, value='0;reboot')]:
            with self.subTest(request=request), self.assertRaises(PlanError):
                self.engine.plan(SERIAL, [request])
        self.assertEqual(self.adb.writes, [])

    def test_partial_failure_rolls_back_only_changed_steps(self):
        plan = self.engine.plan(SERIAL, [SETTING, PACKAGE])
        self.adb.fail_write = 2
        record = self.engine.apply(plan['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.assertEqual([a['status'] for a in record['actions']], ['verified', 'failed'])
        self.adb.fail_write = None
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(len(rollback['actions']), 1)
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')
        self.assertEqual(self.adb.settings[('global', 'window_animation_scale')], '1.0')

    def test_response_lost_after_write_is_still_recoverable(self):
        plan = self.engine.plan(SERIAL, [SETTING])
        self.adb.fail_write = 1
        self.adb.fail_after_write = True
        record = self.engine.apply(plan['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.adb.fail_write = None
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')

    def test_interrupted_running_step_recovery_and_rollback(self):
        plan = self.engine.plan(SERIAL, [SETTING, PACKAGE])
        record = {k: copy.deepcopy(v) for k, v in plan.items() if k not in ('used', 'expires_at', 'serial')}
        record['status'] = 'running'
        record['actions'][0]['status'] = 'running'
        record['actions'][1]['status'] = 'pending'
        self.adb.settings[('global', 'window_animation_scale')] = '0.5'
        self.store.save(record)
        self.store.recover()
        self.assertEqual(self.store.get(record['id'])['status'], 'interrupted')
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(len(rollback['actions']), 1)
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')

    def test_rollback_refuses_external_changes(self):
        record = self.engine.apply(self.engine.plan(SERIAL, [SETTING])['id'], True)
        self.adb.settings[('global', 'window_animation_scale')] = '0'
        count = len(self.adb.writes)
        with self.assertRaises(PlanError): self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(len(self.adb.writes), count)

    def test_launcher_and_screensaver_restore_exact_component(self):
        old_home = self.adb.home
        requests = [{'type': 'launcher', 'component': 'com.spocky.projengmenu/.ui.home.MainActivity'},
                    {'type': 'setting', 'namespace': 'secure', 'key': 'screensaver_components', 'value': 'com.android.dreams.basic/.Dreams'}]
        record = self.engine.apply(self.engine.plan(SERIAL, requests)['id'], True)
        self.assertEqual(record['status'], 'succeeded')
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')
        self.assertEqual(self.adb.home, old_home)
        self.assertEqual(self.adb.settings[('secure', 'screensaver_components')], 'com.android.dreams.basic/.Colors')


if __name__ == '__main__': unittest.main()


class GuardAdb(TracedAdb):
    def __init__(self):
        super().__init__()
        self.installed = False
        self.appop = 'ignore'
        self.running = False
        self.service_pending = False
        self.guard_calls = []
        self.install_failure = None
        self.start_failure = False
    def install(self, serial, apk):
        self.guard_calls.append('install')
        if self.install_failure == 'before': raise RuntimeError('install failed before write')
        self.installed = True
        if self.install_failure == 'after': raise RuntimeError('install response lost after write')
        return 'Success'
    def shell(self, serial, args, timeout=20):
        if args[:3] == ['pm', 'list', 'packages'] and args[-1] == 'com.kilitkoruyucu.tv':
            return 'package:com.kilitkoruyucu.tv' if self.installed else ''
        if args[:2] == ['pm', 'uninstall']:
            self.guard_calls.append('uninstall')
            self.installed = False
            return 'Success'
        if args[:2] == ['appops', 'get']:
            if not self.installed: raise RuntimeError('package absent')
            return 'APP_AUTO_START: ' + self.appop
        if args[:2] == ['appops', 'set']:
            self.guard_calls.append('appop:' + args[-1])
            self.appop = args[-1]
            return ''
        if args[:2] == ['sh', '-c']:
            if '--stop' in args[-1]:
                self.guard_calls.append('stop-script')
                self.running = False
                return 'STOPPED'
            return 'RUNNING:1234' if self.running else 'STOPPED'
        if args[:2] == ['am', 'force-stop']:
            self.guard_calls.append('force-stop')
            self.service_pending = False
            self.running = False
            return ''
        if args[:2] == ['am', 'start']:
            self.guard_calls.append('activity')
            return ''
        if args[:2] == ['am', 'start-foreground-service']:
            self.guard_calls.append('start-service')
            self.service_pending = True
            if self.start_failure: raise RuntimeError('service response lost, retry still pending')
            self.running = True
            return ''
        return super().shell(serial, args, timeout)


class GuardDevice(DemoDevice):
    def health(self):
        result = super().health()
        result['cam_wait_evidence'] = True
        return result


class GuardEngineTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from unittest.mock import patch
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.assets = Path(self.tmp.name) / 'assets'
        (self.assets / 'guard').mkdir(parents=True)
        self.apk = self.assets / 'guard' / 'kilit-koruyucu.apk'
        self.apk.write_bytes(b'synthetic APK fixture - never installed on a device')
        patcher = patch('tvbakim.engine.resources', return_value=self.assets)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.adb = GuardAdb()
        self.store = Store(Path(self.tmp.name) / 'journal')
        self.engine = Engine(self.adb, self.store, GuardDevice)

    def test_guard_oem_appop_baseline_captured_and_full_remove_restores(self):
        plan = self.engine.guard_plan(SERIAL, 'install')
        self.assertEqual(self.adb.guard_calls, [])
        record = self.engine.apply(plan['id'], True)
        self.assertEqual(record['status'], 'succeeded')
        appop = next(a for a in record['actions'] if a['type'] == 'guard_appop')
        self.assertEqual(appop['before'], 'ignore')
        self.assertTrue(self.adb.installed)
        self.assertTrue(self.adb.running)
        rollback = self.engine.guard_plan(SERIAL, 'remove')
        restored = self.engine.apply(rollback['id'], True)
        self.assertEqual(restored['status'], 'succeeded')
        self.assertFalse(self.adb.installed)
        self.assertFalse(self.adb.running)
        self.assertFalse(self.adb.service_pending)
        self.assertEqual(self.adb.appop, 'ignore')
        self.assertNotIn(('global', 'adb_allowed_connection_time'), self.adb.settings)
        self.assertLess(self.adb.guard_calls.index('force-stop'), self.adb.guard_calls.index('uninstall'))
        self.assertLess(self.adb.guard_calls.index('force-stop'), self.adb.guard_calls.index('stop-script'))

    def test_guard_failed_install_before_write_has_nothing_to_rollback(self):
        self.adb.install_failure = 'before'
        record = self.engine.apply(self.engine.guard_plan(SERIAL, 'install')['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.assertFalse(self.adb.installed)
        with self.assertRaises(PlanError): self.engine.rollback_plan(record['id'], SERIAL)

    def test_guard_install_lost_response_rollback_removes_new_apk(self):
        self.adb.install_failure = 'after'
        record = self.engine.apply(self.engine.guard_plan(SERIAL, 'install')['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.assertTrue(self.adb.installed)
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')
        self.assertFalse(self.adb.installed)

    def test_guard_start_failure_must_stop_retrying_service_before_remove(self):
        self.adb.start_failure = True
        record = self.engine.apply(self.engine.guard_plan(SERIAL, 'install')['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.assertTrue(self.adb.service_pending)
        self.assertFalse(self.adb.running)
        rollback = self.engine.rollback_plan(record['id'], SERIAL)
        self.assertTrue(any(a['type'] == 'guard_active' and a['after'] == 'stopped' for a in rollback['actions']))
        self.assertEqual(self.engine.apply(rollback['id'], True)['status'], 'succeeded')
        self.assertFalse(self.adb.service_pending)
        self.assertLess(self.adb.guard_calls.index('force-stop'), self.adb.guard_calls.index('uninstall'))

    def test_guard_apk_changed_after_plan_never_installs(self):
        plan = self.engine.guard_plan(SERIAL, 'install')
        self.apk.write_bytes(b'changed')
        record = self.engine.apply(plan['id'], True)
        self.assertEqual(record['status'], 'partial')
        self.assertNotIn('install', self.adb.guard_calls)

    def test_guard_normal_cam_unsupported_profile_existing_install_blocked(self):
        self.engine.device_factory = DemoDevice
        with self.assertRaises(PlanError): self.engine.guard_plan(SERIAL, 'install')
        class Unsupported(GuardDevice):
            def inspect(self):
                info = super().inspect()
                info['identity']['profile'] = 'generic'
                return info
        self.engine.device_factory = Unsupported
        with self.assertRaises(PlanError): self.engine.guard_plan(SERIAL, 'install')
        self.engine.device_factory = GuardDevice
        self.adb.installed = True
        with self.assertRaises(PlanError): self.engine.guard_plan(SERIAL, 'install')
        self.assertEqual(self.adb.guard_calls, [])

    def test_legacy_guard_only_version_checked_never_started_or_replaced(self):
        class LegacyAdb(GuardAdb):
            def __init__(self):
                super().__init__()
                self.installed = True
                self.status_commands = []
            def shell(self, serial, args, timeout=20):
                if args[:2] == ['sh', '-c']:
                    self.status_commands.append(args[-1])
                    return 'UNKNOWN_LEGACY'
                return super().shell(serial, args, timeout)
        self.adb = LegacyAdb()
        self.engine.adb = self.adb
        result = self.engine.guard_plan(SERIAL, 'status')
        self.assertEqual(result['state'], 'unknown')
        self.assertTrue(self.adb.status_commands)
        for command in self.adb.status_commands:
            self.assertIn('head -n 2', command)
            self.assertIn('# TVCare Guard 1.1.', command)
            self.assertLess(command.index('head -n 2'), command.index('then sh '))
        with self.assertRaises(PlanError): self.engine.guard_plan(SERIAL, 'install')
        self.assertEqual(self.adb.guard_calls, [])
        self.assertEqual(self.adb.writes, [])
