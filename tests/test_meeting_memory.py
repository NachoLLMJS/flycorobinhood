import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
import backend

class MeetingMemoryTests(unittest.TestCase):
    def test_closing_ceo_and_agent_memory_survive_restart(self):
        calls=[]
        class Provider:
            def state(self): return {'ready':True,'name':'test','reason':''}
            def complete(self,a,f,m):
                calls.append((a['id'],a.get('memory','')))
                return 'No launch. Further research needed. [source1]' if m else 'Opening discussion [source1]'
        with tempfile.TemporaryDirectory() as tmp:
            app=backend.App(Path(tmp)/'db',Provider())
            source=dict(id='source1',title='Fixture only',url='https://docs.ponsfamily.com/v2',summary='test',agentId='hex',createdAt=backend.now())
            with patch.object(backend,'collect_sources',return_value={'findings':[source],'errors':[]}):
                app.start_meeting();app.worker.join(5)
                m=app.state()['meetings'][0]
                self.assertEqual(len(m['messages']),7)
                self.assertEqual(m['messages'][-1]['agentId'],'buzz')
                self.assertEqual(m['sources'][0]['id'],'source1')
                self.assertEqual(m['messages'][0]['sourceIds'],['source1'])
                self.assertEqual(app.state()['proposals'][0]['title'],'Proposal for human review — not a launch')
                restored=backend.App(Path(tmp)/'db',Provider())
                self.assertTrue(all(a['memory'] for a in restored.state()['agents']))
                restored.start_meeting();restored.worker.join(5)
                self.assertTrue(calls[7][1])
