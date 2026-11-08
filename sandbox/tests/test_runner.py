import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from broker._schemas import errors
from sandbox.runner import ImageLock, SandboxError, flags, run_job, load_lock

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    return json.loads((ROOT / 'schemas' / 'fixtures' / name).read_text())


class FakeDocker:
    def __init__(self, *, orphan=False, oom=False, overflow=False, start_error=False):
        self.commands = []
        self.orphan, self.oom, self.overflow, self.start_error = orphan, oom, overflow, start_error

    def call(self, args, *, stdin=b'', deadline=None, limit=524288):
        from sandbox.runner import CommandResult
        self.commands.append(args)
        if args[0] == 'create':
            return CommandResult(0, b'abc123\n', b'')
        if args[0] == 'version':
            return CommandResult(0, b'{"Server":{"Version":"fixture-only"}}', b'')
        if args[0] == 'start':
            if self.start_error:
                raise OSError('fixture transport failure')
            return CommandResult(0, json.dumps(fixture('sb1_response__valid_ok.json')).encode(), b'',
                                 overflow=self.overflow)
        if args[0] == 'inspect':
            return CommandResult(0, json.dumps([{'State': {'ExitCode': 137 if self.oom else 0,
                  'OOMKilled': self.oom, 'StartedAt': '2026-11-04T12:00:00Z', 'FinishedAt': '2026-11-04T12:00:01Z'}}]).encode(), b'')
        if args[0] == 'ps':
            return CommandResult(0, b'abc123\n' if self.orphan else b'', b'')
        return CommandResult(0, b'', b'')


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.job = fixture('blackbox_job__valid.json')
        self.req = fixture('sb1_request__valid.json')
        encoded = b''.join(json.dumps(e, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode() + b'\n' for e in self.req['events'])
        self.job['dataset_sha256'] = hashlib.sha256(encoded).hexdigest()
        self.lock = ImageLock('fixture-only', 'sha256:' + 'a' * 64, 'python:3.12-slim@sha256:' + 'b' * 64)

    def test_absent_lock_fails_closed(self):
        with self.assertRaises(SandboxError):
            load_lock(ROOT / 'sandbox' / 'NO_SUCH_LOCK')

    def test_real_executor_requires_disk_lock_before_dispatch(self):
        from sandbox.runner import DockerExecutor
        with self.assertRaisesRegex(SandboxError, 'G4'):
            run_job(self.job,self.req['code'],self.req['events'],lock=self.lock,
                    executor=DockerExecutor(docker='MUST-NOT-EXECUTE'),
                    operation_seconds=1,lock_path=ROOT/'sandbox'/'NO_SUCH_LOCK')

    def test_flags_bound_to_caps_no_host_mount_or_secret(self):
        cmd = flags(self.job, self.lock, attempt=1, deadline_epoch=1900000000)
        for bad in ('-v', '--mount', '--privileged', '--env-file', '--device', '--pid', 'docker.sock'):
            self.assertNotIn(bad, cmd)
        self.assertEqual(cmd[cmd.index('--network') + 1], 'none')
        self.assertEqual(cmd[cmd.index('--memory') + 1], '256m')
        self.assertIn('--cap-drop', cmd)
        self.assertEqual(cmd[cmd.index('--user') + 1], '65534:65534')

    def test_caps_can_tighten_but_not_loosen_defaults(self):
        for key, value in [('wall_seconds',31), ('memory_mb',257), ('pids',65), ('cpus',1.1), ('stdout_bytes',524289)]:
            bad = copy.deepcopy(self.job)
            bad['caps'][key] = value
            with self.subTest(key=key), self.assertRaises(SandboxError):
                flags(bad, self.lock, attempt=1, deadline_epoch=1900000000)

    def test_lifecycle_receipt_and_journal(self):
        journal = []
        fake = FakeDocker()
        result = run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=fake,
                         journal=lambda kind, data: journal.append((kind, data)), clock=lambda: '2026-11-04T12:00:00Z')
        self.assertTrue(result.destroy_verified)
        self.assertEqual(result.termination, 'normal')
        self.assertEqual([x[0] for x in fake.commands], ['version','create','start','inspect','rm','ps'])
        self.assertEqual([x[0] for x in journal], ['sandbox_created','sandbox_started','sandbox_ended','sandbox_destroyed'])
        self.assertEqual(result.flags_sha256, hashlib.sha256(json.dumps(fake.commands[1], separators=(',', ':')).encode()).hexdigest())

    def test_cleanup_even_if_transport_raises(self):
        fake = FakeDocker(start_error=True)
        with self.assertRaises(SandboxError):
            run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=fake)
        self.assertEqual([x[0] for x in fake.commands][-2:], ['rm', 'ps'])

    def test_orphan_refused(self):
        with self.assertRaisesRegex(SandboxError, 'destroy'):
            run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=FakeDocker(orphan=True))

    def test_oom_is_observed_not_inferred(self):
        result = run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=FakeDocker(oom=True))
        self.assertEqual(result.termination, 'oom_killed')

    def test_overflow_kills_and_refuses_output(self):
        fake = FakeDocker(overflow=True)
        result = run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=fake)
        self.assertEqual(result.termination, 'error')
        self.assertIsNone(result.output)
        self.assertIn('kill', [x[0] for x in fake.commands])

    def test_tampered_dataset_never_calls_docker(self):
        fake = FakeDocker()
        rows = copy.deepcopy(self.req['events'])
        rows[0]['output'] += 'tampered'
        with self.assertRaisesRegex(SandboxError, 'dataset hash'):
            run_job(self.job, self.req['code'], rows, lock=self.lock, executor=fake)
        self.assertEqual(fake.commands, [])

    def test_receipt_schema_and_observed_version_separate_from_R1(self):
        result = run_job(self.job, self.req['code'], self.req['events'], lock=self.lock, executor=FakeDocker())
        receipt = result.receipt(job=self.job, attempt=1, metrics={'exceptions_caught': 1},
                    self_metrics={'exceptions_caught': 1}, discrepancy=False,
                    claim_check=fixture('claim_check__valid.json'), journal_head_sha256='a'*64,
                    events_sha256='b'*64, events_count=3,
                    secret_scan={'canary_present_in_env': False, 'scan_passed': True})
        self.assertEqual(errors('blackbox_run.schema.json', receipt), [])
        self.assertNotIn('docker_version', receipt)  # frozen R1 forbids added fields
        self.assertEqual(result.docker_version['Server']['Version'], 'fixture-only')

    def test_golden_through_harness_plain_process_only(self):
        # Only the frozen, trusted golden program executes here; no generated/untrusted payload.
        p = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'sandbox'/'harness'/'run.py')],
                           input=json.dumps(self.req).encode(), capture_output=True, check=True)
        self.assertEqual(p.stdout.decode(), (ROOT/'schemas'/'golden'/'sb1_golden_stdout.json').read_text())


if __name__ == '__main__':
    unittest.main()
