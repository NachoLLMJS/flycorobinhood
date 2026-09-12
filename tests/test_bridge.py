import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'hermes_bridge.py'

class BridgeTests(unittest.TestCase):
    def load(self):
        self.assertTrue(PATH.exists(), 'bridge implementation missing')
        spec = importlib.util.spec_from_file_location('hermes_bridge', PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_final_parser_fails_closed(self):
        b = self.load()
        self.assertEqual(b.parse_worker_output('{"content":"Hola","tools":0,"completed":true}'), 'Hola')
        for value in ['', 'log\n{"content":"ok"}', '{"content":"","tools":0,"completed":true}', '{"content":"ok","tools":1,"completed":true}', '{"content":"ok","tools":0,"completed":false}']:
            with self.subTest(value=value), self.assertRaises(b.BridgeError):
                b.parse_worker_output(value)

    def test_safe_command_and_payload(self):
        b = self.load()
        self.assertTrue(hasattr(b, 'cli_args'), 'safe CLI builder missing')
        args = b.cli_args('literal $(whoami) !rm /skills')
        for flag in ['--safe-mode', '--ignore-rules', '--ignore-user-config', '-Q', '--cli']:
            self.assertIn(flag, args)
        self.assertEqual(args[args.index('--max-turns') + 1], '1')
        self.assertEqual(args[args.index('-t') + 1], 'context_engine')
        self.assertEqual(args[args.index('--provider') + 1], 'openai-codex')
        self.assertEqual(args[-1], 'literal $(whoami) !rm /skills')
        data = {'model': 'gpt-6-astra', 'messages': [{'role': 'user', 'content': 'Hola'}]}
        self.assertIn('Hola', b.validate_request(data))
        for bad in [{}, dict(data, stream=True), dict(data, tools=[{}]), dict(data, model='other'), dict(data, messages=[{'role':'tool','content':'x'}]), dict(data, messages=[{'role':'user','content':'x'*17000}])]:
            with self.subTest(bad=str(bad)[:100]), self.assertRaises(b.BridgeError):
                b.validate_request(bad)

    def test_agent_guard_refuses_tools_and_partial(self):
        b = self.load()
        self.assertTrue(hasattr(b, 'guarded_turn'), 'runtime safety guard missing')
        from types import SimpleNamespace
        agent = SimpleNamespace(tools=[], valid_tool_names=set(), max_iterations=1, _memory_enabled=False, _user_profile_enabled=False, skip_context_files=True)
        final = {'final_response': 'real answer', 'completed': True}
        self.assertEqual(b.guarded_turn(agent, lambda: final), 'real answer')
        for name, value in [('tools', [{'function': {'name':'terminal'}}]), ('valid_tool_names', {'terminal'}), ('max_iterations', 2), ('_memory_enabled', True), ('_user_profile_enabled', True), ('skip_context_files', False)]:
            original = getattr(agent, name)
            setattr(agent, name, value)
            with self.subTest(name=name), self.assertRaises(b.BridgeError):
                b.guarded_turn(agent, lambda: self.fail('unsafe model turn executed'))
            setattr(agent, name, original)
        for result in [dict(final, partial=True), dict(final, failed=True), dict(final, completed=False), dict(final, final_response='')]:
            with self.assertRaises(b.BridgeError):
                b.guarded_turn(agent, lambda: result)

    def test_worker_subprocess_roundtrip(self):
        b = self.load()
        self.assertTrue(hasattr(b, 'run_completion'), 'bounded subprocess bridge missing')
        from unittest.mock import patch
        import subprocess
        fake = subprocess.CompletedProcess([], 0, '{"content":"ok","tools":0,"completed":true}', '')
        with patch.object(b.subprocess, 'run', return_value=fake) as run:
            self.assertEqual(b.run_completion('safe text', timeout=9), 'ok')
            args, kw = run.call_args
            self.assertTrue(pathlib.Path(args[0][0]).is_absolute())
            self.assertFalse(kw['shell'])
            self.assertEqual(kw['input'], 'safe text')
            self.assertEqual(kw['timeout'], 9)
            self.assertEqual(kw['env']['HERMES_SAFE_MODE'], '1')
            self.assertNotIn('HERMES_KANBAN_TASK', kw['env'])
        with patch.object(b.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker', 1)):
            with self.assertRaises(b.BridgeError):
                b.run_completion('safe', timeout=1)

if __name__ == '__main__':
    unittest.main()
