"""Fail-closed local chat adapter for the authenticated Hermes CLI."""
import json
import os
import sys
import subprocess
from pathlib import Path


def run_completion(prompt, timeout=120):
    python = Path.home() / 'AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe'
    env = dict(os.environ, HERMES_SAFE_MODE='1', HERMES_IGNORE_RULES='1', HERMES_IGNORE_USER_CONFIG='1', PYTHONIOENCODING='utf-8')
    for key in list(env):
        if key.startswith('HERMES_KANBAN'):
            del env[key]
    try:
        result = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker'], input=prompt, text=True, encoding='utf-8', capture_output=True, timeout=timeout, shell=False, env=env)
        if result.returncode:
            # Never reflect logs/credentials; a public bounded diagnostic only.
            raise BridgeError('Hermes model request failed (authentication, quota, or isolation); no simulated response supplied')
        return parse_worker_output(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise BridgeError('Hermes model timed out') from exc


def worker():
    from contextlib import redirect_stdout, redirect_stderr
    import logging
    prompt = sys.stdin.read(MAX_PROMPT + 1)
    if len(prompt) > MAX_PROMPT:
        raise BridgeError('Prompt too large')
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from run_agent import AIAgent
        runtime = resolve_runtime_provider(requested='openai-codex', target_model=MODEL)
        agent = AIAgent(api_key=runtime.get('api_key'), base_url=runtime.get('base_url'), provider=runtime.get('provider'), requested_provider=runtime.get('requested_provider'), api_mode=runtime.get('api_mode'), credential_pool=runtime.get('credential_pool'), model=MODEL, enabled_toolsets=['context_engine'], max_iterations=1, quiet_mode=True, skip_memory=True, skip_context_files=True, platform='tool', max_tokens=1400, reasoning_config={'effort':'low'})
        try:
            if os.getenv('FLY_BRIDGE_DIAGNOSTIC') == '1':
                raise BridgeError(str({k:getattr(agent,k,None) for k in ['max_turns','max_iterations','skip_memory','skip_context_files']} ) + ' tool_count=' + str(len(agent.tools)) + ' valid_count=' + str(len(agent.valid_tool_names)))
            text = guarded_turn(agent, lambda: agent.run_conversation(prompt))
        finally:
            agent.close()
    print(json.dumps({'content':text,'tools':0,'completed':True}, ensure_ascii=False))


MODEL = 'gpt-6-astra'
MAX_PROMPT = 16000


def cli_args(prompt):
    return ['hermes', 'chat', '--safe-mode', '--ignore-user-config', '--ignore-rules',
            '--cli', '-Q', '-t', 'context_engine', '--max-turns', '1',
            '--source', 'tool', '--provider', 'openai-codex', '-m', MODEL, '-q', prompt]


def validate_request(data):
    if not isinstance(data, dict):
        raise BridgeError('Expected JSON object')
    if data.get('model', MODEL) != MODEL or data.get('stream', False) is not False:
        raise BridgeError('Only gpt-6-astra non-streaming requests are supported')
    if any(key in data for key in ('tools', 'functions', 'tool_choice', 'function_call')):
        raise BridgeError('Tool requests are forbidden')
    messages = data.get('messages')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 80:
        raise BridgeError('messages must contain 1..80 text messages')
    clean = []
    for message in messages:
        if (not isinstance(message, dict) or message.get('role') not in ('system', 'user', 'assistant')
                or not isinstance(message.get('content'), str) or not message['content'].strip()
                or '\x00' in message['content']):
            raise BridgeError('Only nonempty text system/user/assistant messages are supported')
        clean.append({'role': message['role'], 'content': message['content']})
    prompt = ('Respond to the final user message in this JSON conversation. '
              'Return only the assistant answer, not the conversation envelope.\n'
              + json.dumps(clean, ensure_ascii=False))
    if len(prompt.encode('utf-8')) > MAX_PROMPT:
        raise BridgeError('Conversation exceeds 16000 UTF-8 bytes')
    return prompt


class BridgeError(Exception):
    pass


def guarded_turn(agent, call):
    # Fail before a model request if a Hermes update widens the tool surface.
    if (getattr(agent, 'tools', None) != [] or getattr(agent, 'valid_tool_names', None) != set()
            or getattr(agent, 'max_iterations', None) != 1
            or getattr(agent, '_memory_enabled', None) is not False
            or getattr(agent, '_user_profile_enabled', None) is not False
            or getattr(agent, 'skip_context_files', None) is not True):
        raise BridgeError('Hermes isolation invariant failed')
    result = call()
    if (not isinstance(result, dict) or result.get('completed') is not True
            or result.get('failed') or result.get('partial')):
        raise BridgeError('Hermes turn incomplete')
    return parse_worker_output(json.dumps({'content': result.get('final_response'), 'tools': 0, 'completed': True}))


def parse_worker_output(text):
    try:
        data = json.loads(text)
        if (not isinstance(data, dict) or data.get('tools') != 0
                or data.get('completed') is not True
                or not isinstance(data.get('content'), str)
                or not data['content'].strip() or len(data['content']) > 65536):
            raise ValueError('invalid worker result')
        return data['content']
    except (ValueError, TypeError, KeyError) as exc:
        raise BridgeError('Hermes did not produce a verified final response') from exc


if __name__ == '__main__':
    try:
        if '--worker' in sys.argv:
            worker()
        else:
            print(run_completion('Reply only: FLYCOROBINHOOD_MODEL_OK'))
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
