import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sandbox.reaper import reap
from sandbox.runner import SandboxError, run_job
from sandbox.tests import test_runner

FakeDocker = test_runner.FakeDocker

class ExtraBoundaryTests(unittest.TestCase):
    setUp = test_runner.SandboxTests.setUp
    def test_expired_labels_only_reaper(self):
        calls = []
        def command(argv, **kwargs):
            from types import SimpleNamespace
            calls.append(argv)
            if argv[1:3] == ['ps','-aq'] and 'label=dr.deadline' in argv:
                return SimpleNamespace(stdout='abcdef123456\n')
            if argv[1] == 'inspect':
                return SimpleNamespace(stdout=json.dumps([{'Config': {'Labels': {'dr.run':'run-001','dr.deadline':'100'}}}]))
            return SimpleNamespace(stdout='')
        with patch('sandbox.reaper.subprocess.run',command):
            self.assertEqual(reap(docker='fixture-docker',operation_seconds=1,now=111),['abcdef123456'])
        self.assertEqual(calls[-2][1:4],['rm','-f','-v'])
        self.assertIn('label=dr.deadline',calls[0])

    def test_invalid_stdout_cleans_up(self):
        fake = FakeDocker()
        original = fake.call
        def call(args, **kwargs):
            result = original(args, **kwargs)
            if args[0] == 'start':
                result.stdout = b'not JSON'
            return result
        fake.call = call
        with self.assertRaisesRegex(SandboxError,'SB1 JSON'):
            run_job(self.job,self.req['code'],self.req['events'],lock=self.lock,executor=fake)
        self.assertEqual([x[0] for x in fake.commands][-2:],['rm','ps'])

    def test_lock_version_mismatch_never_creates(self):
        fake = FakeDocker()
        original = fake.call
        def call(args, **kwargs):
            result = original(args, **kwargs)
            if args[0] == 'version':
                result.stdout = b'{"Server":{"Version":"different"}}'
            return result
        fake.call = call
        with self.assertRaisesRegex(SandboxError,'version'):
            run_job(self.job,self.req['code'],self.req['events'],lock=self.lock,executor=fake)
        self.assertEqual([x[0] for x in fake.commands],['version'])
