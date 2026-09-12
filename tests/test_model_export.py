import unittest, json, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ModelExportTests(unittest.TestCase):
    def test_original_meshes_have_complete_geometry_and_motion(self):
        p=ROOT/'public/assets/neuromechfly/model.json'
        self.assertTrue(p.exists(), 'Original NeuroMechFly export must exist')
        d=json.loads(p.read_text())
        self.assertEqual(d['source'],'NeuroMechFly v2')
        self.assertEqual(d['license'],'Apache-2.0')
        self.assertEqual(len(d['parts']),69)
        names=[p['name'] for p in d['parts']]
        for name in ['nmf/c_head','nmf/l_eye','nmf/r_eye','nmf/l_wing','nmf/r_wing','nmf/lf_tarsus5','nmf/rh_tarsus5']:
            self.assertIn(name,names)
        binary=(p.parent/'geometry.bin').read_bytes()
        for mesh in d['meshes']:
            self.assertGreater(mesh['vertexCount'],3)
            self.assertGreater(mesh['indexCount'],3)
            self.assertLessEqual(mesh['indexOffset']+mesh['indexCount']*4,len(binary))
        self.assertEqual(len(d['walkFrames']),48)
        self.assertNotEqual(d['walkFrames'][0],d['walkFrames'][12])
        self.assertTrue(all(len(f)==len(d['parts']) for f in d['walkFrames']))
        self.assertIn('kinematic',d['motion'].lower())
if __name__=='__main__':unittest.main()
