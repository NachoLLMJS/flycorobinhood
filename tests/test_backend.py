import unittest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.app = backend.App(self.path, provider=backend.Provider({}))

    def test_unavailable_provider_blocks_without_fake_messages(self):
        with self.assertRaises(backend.Blocked):
            self.app.start_meeting()
        self.assertEqual(self.app.state()['meetings'], [])
        self.assertFalse(self.app.state()['running'])

    def test_research_persists_only_real_extracted_sources(self):
        from unittest.mock import patch
        rss = b'<rss><channel><item><title>Robinhood Chain test fixture</title><link>https://www.coindesk.com/test</link><description>Evidence fixture</description></item></channel></rss>'
        def fetch(url):
            return rss if url.rstrip('/').endswith('rss') else b'<html><title>Official docs fixture</title><body>Documented launch workflow and human review.</body></html>'
        with patch.object(backend, 'fetch_source', side_effect=fetch):
            result = self.app.research()
        self.assertEqual(len(result['findings']), 3)
        self.assertEqual(len(backend.App(self.path, backend.Provider({})).state()['findings']), 3)
        self.assertIn('https://docs.robinhood.com/chain/', backend.SOURCES)
        self.assertIn('https://docs.ponsfamily.com/v2', backend.SOURCES)
        with self.assertRaises(ValueError):
            backend.fetch_source('http://127.0.0.1/secrets')

    def test_async_meeting_sequential_context_and_overlap(self):
        import threading
        from unittest.mock import patch
        entered, release = threading.Event(), threading.Event()
        contexts = []
        class FakeProvider:
            def state(self): return dict(ready=True, name='test fixture', reason='')
            def complete(self, agent, findings, messages):
                contexts.append(len(messages))
                entered.set()
                release.wait(3)
                return 'Respuesta de prueba; no es evidencia real.'
        self.app.provider = FakeProvider()
        evidence = [dict(id='source1', title='fixture', url='https://docs.ponsfamily.com/v2', summary='fixture', agentId='hex', createdAt=backend.now())]
        with patch.object(backend, 'collect_sources', return_value=dict(findings=evidence, errors=[])):
            meeting = self.app.start_meeting()
            self.assertTrue(entered.wait(2))
            with self.assertRaises(backend.Busy): self.app.start_meeting()
            with self.assertRaises(backend.Busy): self.app.research()
            release.set()
            self.app.worker.join(4)
        self.assertFalse(self.app.state()['running'])
        saved = self.app.state()['meetings'][0]
        self.assertEqual(saved['id'], meeting['id'])
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(contexts, [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(len(saved['messages']), 7)
        self.assertEqual(len(self.app.state()['proposals']), 1)

    def test_atomic_state_mutation_does_not_lose_cross_process_updates(self):
        import threading
        other = backend.App(self.path, provider=backend.Provider({}))
        def increment(app):
            for _ in range(40):
                def mutate(state):
                    state['counter'] = state.get('counter', 0) + 1
                app.mutate_state(mutate)
        threads = [threading.Thread(target=increment, args=(app,)) for app in (self.app, other)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(self.app.load()['counter'], 80)

    def test_shared_meeting_lease_blocks_a_second_process(self):
        import threading
        from unittest.mock import patch
        entered, release = threading.Event(), threading.Event()
        class BlockingProvider:
            def state(self): return dict(ready=True, name='lease fixture', reason='')
            def complete(self, agent, findings, messages):
                entered.set()
                release.wait(3)
                return 'English meeting contribution [source1]'
        self.app.provider = BlockingProvider()
        other = backend.App(self.path, provider=BlockingProvider())
        evidence = [dict(id='source1', title='fixture', url='https://docs.ponsfamily.com/v2', summary='fixture', agentId='hex', createdAt=backend.now())]
        with patch.object(backend, 'collect_sources', return_value=dict(findings=evidence, errors=[])):
            first = self.app.start_meeting()
            self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(backend.Busy):
                    other.start_meeting()
            finally:
                release.set()
                self.app.worker.join(5)
                if hasattr(other, 'worker'):
                    other.worker.join(5)
        self.assertEqual(self.app.state()['meetings'][0]['id'], first['id'])

    def test_stale_task_cannot_release_a_newer_lease_from_same_process(self):
        first_token = self.app._acquire_task('research')
        self.app.mutate_state(lambda state: state['lease'].update(expiresAt='2000-01-01T00:00:00Z'))
        second_token = self.app._acquire_task('meeting')
        self.app._release_task(first_token)
        lease = self.app.load()['lease']
        self.assertEqual(lease['token'], second_token)
        self.app._release_task(second_token)

    def test_stale_task_cannot_persist_after_a_newer_lease_takes_over(self):
        meeting = dict(id='old', status='running', startedAt=backend.now(), endedAt=None, summary='', messages=[])
        first_token = self.app._acquire_task('meeting', meeting)
        self.app.mutate_state(lambda state: state['lease'].update(expiresAt='2000-01-01T00:00:00Z'))
        second_token = self.app._acquire_task('meeting')
        meeting.update(status='completed', summary='stale result', endedAt=backend.now())
        with self.assertRaises(backend.LeaseLost):
            self.app._persist_meeting(meeting, first_token)
        saved = next(item for item in self.app.load()['meetings'] if item['id'] == 'old')
        self.assertEqual(saved['status'], 'interrupted')
        self.app._release_task(second_token)

    def test_run_once_waits_for_the_hermes_meeting_to_finish(self):
        from unittest.mock import patch
        class FakeProvider:
            def state(self): return dict(ready=True, name='Hermes fixture', reason='')
            def complete(self, agent, findings, messages): return 'English meeting contribution [source1]'
        self.app.provider = FakeProvider()
        evidence = [dict(id='source1', title='fixture', url='https://docs.ponsfamily.com/v2', summary='fixture', agentId='hex', createdAt=backend.now())]
        with patch.object(backend, 'collect_sources', return_value=dict(findings=evidence, errors=[])):
            result = self.app.run_once()
        self.assertFalse(self.app.state()['running'])
        self.assertEqual(result['meetings'][0]['status'], 'completed')
        self.assertEqual(len(result['proposals']), 1)

    def test_provider_http_contract(self):
        from unittest.mock import patch
        import io, json
        provider = backend.Provider(dict(LLM_API_KEY='test-secret', LLM_BASE_URL='https://example.com/v1', LLM_MODEL='test-model'))
        response = io.BytesIO(json.dumps({'choices':[{'message':{'content':'respuesta fixture'}}]}).encode())
        class Opener:
            def open(inner, req, timeout):
                body = json.loads(req.data)
                self.assertEqual(body['model'], 'test-model')
                self.assertIn('contexto fixture', body['messages'][-1]['content'])
                self.assertEqual(req.full_url, 'https://example.com/v1/chat/completions')
                return response
        with patch.object(backend.urllib.request, 'build_opener', return_value=Opener()):
            self.assertEqual(provider.complete(backend.AGENTS[0], [], [{'text':'contexto fixture'}]), 'respuesta fixture')

    def test_scheduler_claim_and_restart_recovery(self):
        from unittest.mock import patch
        self.app.set_scheduler(True)
        state = self.app.load()
        state['scheduler']['nextRunAt'] = '2000-01-01T00:00:00Z'
        state['meetings'] = [dict(id='interrupted',status='running',startedAt=backend.now(),endedAt=None,summary='',messages=[])]
        self.app.save(state)
        recovered = backend.App(self.path, backend.Provider({}))
        self.assertEqual(recovered.state()['meetings'][0]['status'], 'interrupted')
        with patch.object(recovered, 'start_meeting', side_effect=backend.Blocked('no key')) as start:
            recovered.tick()
            recovered.tick()
            self.assertEqual(start.call_count, 1)
        self.assertGreater(recovered.state()['scheduler']['nextRunAt'], backend.now())

    def test_failed_tick_does_not_overwrite_a_newer_scheduler_disable(self):
        from unittest.mock import patch
        other = backend.App(self.path, backend.Provider({}))
        self.app.mutate_state(lambda state: state['scheduler'].update(enabled=True, nextRunAt='2000-01-01T00:00:00Z'))
        def disable_then_block():
            other.set_scheduler(False)
            raise backend.Blocked('fixture')
        with patch.object(self.app, 'start_meeting', side_effect=disable_then_block):
            self.app.tick()
        scheduler = self.app.load()['scheduler']
        self.assertFalse(scheduler['enabled'])
        self.assertIsNone(scheduler['nextRunAt'])

    def test_state_persists_scheduler(self):
        self.app.set_scheduler(True)
        state = backend.App(self.path, provider=backend.Provider({})).state()
        self.assertEqual(len(state['agents']), 6)
        self.assertTrue(state['scheduler']['enabled'])
        self.assertEqual(state['scheduler']['intervalHours'], 2)
        self.assertTrue(state['scheduler']['nextRunAt'].endswith('Z'))
        self.assertFalse(state['provider']['ready'])
        self.assertEqual(state['findings'], [])

    def test_state_changes_are_available_as_realtime_events(self):
        self.app.set_scheduler(True)
        events = self.app.events_after(0)
        self.assertTrue(events)
        self.assertEqual(events[-1]['type'], 'scheduler.updated')
        self.assertEqual(events[-1]['payload']['enabled'], True)

    def test_postgres_schema_uses_conflict_safe_insert(self):
        from unittest.mock import patch
        class FakeCursor:
            def fetchone(self):
                return None
        class FakeConnection:
            def execute(self, sql, params=()):
                statements.append(sql)
                return FakeCursor()
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass
        statements = []
        with patch.dict('os.environ', {'DATABASE_URL':'postgresql://fixture'}, clear=False), patch.dict(sys.modules, {'psycopg': type('P', (), {'connect': lambda *a, **k: FakeConnection()})}):
            with self.assertRaises(TypeError):
                backend.App(self.path, provider=backend.Provider({}))
        self.assertTrue(any('ON CONFLICT' in statement for statement in statements))

    def test_postgres_atomic_mutation_locks_state_row_for_update(self):
        import contextlib
        import json
        from unittest.mock import patch
        statements = []
        stored = {'findings': [], 'meetings': [], 'proposals': [], 'scheduler': {'enabled': True, 'nextRunAt': backend.later(), 'intervalHours': 2}, 'lease': None, 'counter': 0}
        class Cursor:
            def __init__(self, row=None): self.row = row
            def fetchone(self): return self.row
        class FakeDB:
            postgres = True
            def execute(self, sql, params=()):
                statements.append(sql)
                if sql.startswith('SELECT value'):
                    return Cursor((json.dumps(stored),))
                if sql.startswith('UPDATE state'):
                    stored.clear()
                    stored.update(json.loads(params[0]))
                return Cursor()
        @contextlib.contextmanager
        def fake_db():
            yield FakeDB()
        with patch.object(self.app, 'db', fake_db):
            self.app.mutate_state(lambda state: state.update(counter=state['counter'] + 1))
        self.assertEqual(stored['counter'], 1)
        self.assertIn('SELECT value FROM state WHERE id=1 FOR UPDATE', statements)

class HTTPTests(unittest.TestCase):
    def setUp(self):
        import server, threading
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        public = root / 'public'
        public.mkdir()
        (public / 'index.html').write_text('<h1>FlyCoRobinhood fixture</h1>')
        (root / '.env').write_text('SECRET=do-not-serve')
        self.app = backend.App(root / 'data' / 'state.sqlite3', backend.Provider({}))
        self.http = server.make_server(self.app, public, port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)

    def request(self, path, method='GET', body=None, headers=None):
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        result = conn.getresponse()
        data = result.read()
        status = result.status
        conn.close()
        return status, data

    def test_static_path_confinement_and_secret_denial(self):
        public = Path(self.tmp.name) / 'public'
        (public / '.env').write_text('SHOULD_NOT_SERVE')
        (public / 'oops.sqlite3').write_bytes(b'secret database')
        for path in ['/../.env', '/%2e%2e/.env', '/%2e%2e%5c.env', '/.env', '/oops.sqlite3', '/server.py', '/C:/Windows/win.ini']:
            with self.subTest(path=path):
                code, body = self.request(path)
                self.assertIn(code, (403, 404))
                self.assertNotIn(b'SHOULD_NOT_SERVE', body)
                self.assertNotIn(b'do-not-serve', body)

    def test_posts_json_guard_and_routes(self):
        import json
        good = {'Content-Type':'application/json'}
        for body in ['{', '[]', 'null', '{"enabled":1}']:
            self.assertEqual(self.request('/api/scheduler', 'POST', body, good)[0], 400)
        self.assertEqual(self.request('/api/scheduler', 'POST', '{}', {'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/scheduler', 'POST', 'x'*17000, good)[0], 413)
        for hostile in [{'Origin':'https://evil.example'}, {'Host':'evil.example'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request('/api/scheduler','POST','{"enabled":true}', dict(good, **hostile))[0], 403)
        code, body = self.request('/api/scheduler','POST','{"enabled":true}',good)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)['enabled'])
        self.assertEqual(self.request('/api/meeting','POST','{}',good)[0], 503)
        self.assertEqual(self.request('/api/unknown','POST','{}',good)[0], 404)
        from unittest.mock import patch
        with patch.object(backend, 'collect_sources', return_value=dict(findings=[],errors=[{'reason':'fixture failure'}])):
            code, body = self.request('/api/research','POST','{}',good)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)['errors'])

    def test_approval_persists_without_network_or_broadcast(self):
        import json
        from unittest.mock import patch
        state = self.app.load()
        state['proposals'] = [dict(id='plan1',status='pending',execution='planning-only',approvedAt=None)]
        self.app.save(state)
        with patch.object(backend.urllib.request, 'build_opener', side_effect=AssertionError('Approval must never use network')):
            code, body = self.request('/api/proposals/plan1/approve','POST','{}',{'Content-Type':'application/json'})
            self.assertEqual(code, 200)
            proposal = json.loads(body)
            self.assertEqual(proposal['status'], 'approved')
            self.assertEqual(proposal['execution'], 'planning-only')
            self.assertTrue(proposal['approvedAt'].endswith('Z'))
            code, repeated = self.request('/api/proposals/plan1/approve','POST','{}',{'Content-Type':'application/json'})
            self.assertEqual(json.loads(repeated)['approvedAt'], proposal['approvedAt'])
        self.assertEqual(self.app.load()['proposals'][0]['status'], 'approved')
        self.assertEqual(self.request('/api/proposals/missing/approve','POST','{}',{'Content-Type':'application/json'})[0],404)

    def test_http_state_and_public_index(self):
        import json
        code, body = self.request('/api/state')
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)['agents']), 6)
        code, body = self.request('/')
        self.assertEqual(code, 200)
        self.assertIn(b'FlyCoRobinhood fixture', body)

    def test_public_x_profile_config_is_separate_and_optional(self):
        import json
        from unittest.mock import patch
        with patch.dict('os.environ', {'FLYCOROBINHOOD_PUBLIC_X_PROFILE_URL': 'https://x.com/new_fly_account'}, clear=False):
            code, body = self.request('/api/config')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {'xProfileUrl': 'https://x.com/new_fly_account'})

    def test_public_deployment_is_read_only_even_without_origin_headers(self):
        import json
        state = self.app.load()
        state['proposals'] = [dict(id='public-plan', status='pending', execution='planning-only', approvedAt=None)]
        self.app.save(state)
        self.http.public_mode = True
        try:
            before = self.app.load()
            headers = {'Content-Type':'application/json', 'Host':'app.example'}
            cases = [
                ('/api/scheduler', '{"enabled":false}'),
                ('/api/research', '{}'),
                ('/api/meeting', '{}'),
                ('/api/proposals/public-plan/approve', '{}'),
            ]
            for path, payload in cases:
                with self.subTest(path=path):
                    code, body = self.request(path, 'POST', payload, headers)
                    self.assertEqual(code, 403)
                    self.assertEqual(json.loads(body), {'error': 'Public deployment is read-only'})
            after = self.app.load()
            self.assertEqual(after['scheduler'], before['scheduler'])
            self.assertEqual(after['meetings'], before['meetings'])
            self.assertEqual(after['findings'], before['findings'])
            self.assertEqual(after['proposals'], before['proposals'])
            code, body = self.request('/api/state')
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(body)['publicReadOnly'])
        finally:
            self.http.public_mode = False

    def test_explicit_public_mode_cannot_be_disabled_by_loopback_binding(self):
        import server
        public = Path(self.tmp.name) / 'public'
        httpd = server.make_server(self.app, public, port=0, bind_host='127.0.0.1', public_mode=True)
        try:
            self.assertTrue(httpd.public_mode)
        finally:
            httpd.server_close()

    def test_events_endpoint_replays_persisted_events(self):
        import json
        self.app.set_scheduler(True)
        code, body = self.request('/api/events?after=0&once=1')
        self.assertEqual(code, 200)
        self.assertIn(b'event: scheduler.updated', body)
        self.assertIn(b'data:', body)

if __name__ == '__main__':
    unittest.main()
