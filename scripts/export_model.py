"""Export ORIGINAL scientific meshes and original step-table kinematic replay.
Derived asset: material colors preserved, no geometry recreation. mj_forward
calculates poses, NOT a dynamics rollout and NOT MaleCNS neural simulation.
Run: .venv/Scripts/python scripts/export_model.py
"""
from pathlib import Path
import json, math
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'source-model'
out=ROOT/'public/assets/neuromechfly'; out.mkdir(parents=True,exist_ok=True)
m=mujoco.MjModel.from_xml_path(str(source/'fly.xml'))
d=mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m,d,0)
meta=json.loads((source/'model_meta.json').read_text())
game=json.loads((source/'game_meta.json').read_text())
# Store coordinates relative to thorax origin; Three.js maps x-forward,z-up to z-forward,y-up.
d.qpos[0:3]=0
mujoco.mj_forward(m,d)
chunks=[]; offset=0; meshes=[]
for i in range(m.nmesh):
    va,vn=int(m.mesh_vertadr[i]),int(m.mesh_vertnum[i]); fa,fn=int(m.mesh_faceadr[i]),int(m.mesh_facenum[i])
    vertices=m.mesh_vert[va:va+vn].astype('<f4').tobytes()
    indices=m.mesh_face[fa:fa+fn].astype('<u4').tobytes()
    meshes.append({'vertexOffset':offset,'vertexCount':vn,'indexOffset':offset+len(vertices),'indexCount':fn*3})
    chunks.extend([vertices,indices]);offset+=len(vertices)+len(indices)
parts=[]
for g in range(m.ngeom):
    if m.geom_dataid[g]<0:continue
    parts.append({'geomId':g,'name':m.geom(g).name,'mesh':int(m.geom_dataid[g]),'rgba':meta['geom_rgba'][g]})
def poses():
    result=[]
    for part in parts:
        g=part['geomId']; q=np.zeros(4);mujoco.mju_mat2Quat(q,d.geom_xmat[g])
        result.append(np.round(np.r_[d.geom_xpos[g],q],7).tolist())
    return result
neutral=poses(); frames=[]
byjoint={a['joint']:a['qposadr'] for a in meta['actuators']}
for f in range(48):
    for leg_i,leg in enumerate(game['control']['leg_order']):
        sample=int(((f/48 +game['control']['tripod_map'][leg_i]*.5)%1)*game['preprogrammed']['n_samples'])
        angles=game['preprogrammed']['legs'][leg]['angles'][sample]
        for dof_i,ctrl in enumerate(game['ctrl_index_by_leg_dof'][leg_i]):
            joint=game['actuators'][ctrl]['joint'];d.qpos[byjoint[joint]]=angles[dof_i]
    mujoco.mj_forward(m,d);frames.append(poses())
# Bounds of neutral geometry in original frame, reliable normalization/support.
verts=[]
for part in parts:
    g=part['geomId'];mesh=part['mesh'];va,vn=int(m.mesh_vertadr[mesh]),int(m.mesh_vertnum[mesh])
    p=neutral[len(verts)]
    rot=np.zeros(9);mujoco.mju_quat2Mat(rot,np.array(p[3:]));vertices=m.mesh_vert[va:va+vn]@rot.reshape(3,3).T+np.array(p[:3])
    verts.append(vertices)
a=np.vstack(verts)
result={'source':'NeuroMechFly v2','license':'Apache-2.0','sourceUrl':'https://github.com/NeLy-EPFL/flygym','sourceManifest':'source-model/manifest.json','motion':'Kinematic replay of upstream preprogrammed walking joint-angle tables, posed with MuJoCo mj_forward. No live dynamics or MaleCNS controller.','axis':'X forward, Z up; millimeters','meshes':meshes,'parts':parts,'neutral':neutral,'walkFrames':frames,'bounds':{'min':a.min(0).tolist(),'max':a.max(0).tolist()},'walkDuration':0.9}
(out/'geometry.bin').write_bytes(b''.join(chunks))
(out/'model.json').write_text(json.dumps(result,separators=(',',':')))
print('EXPORTED',len(parts),'anatomical parts',sum(v['indexCount']//3 for v in meshes),'triangles',len(frames),'kinematic frames',offset,'geometry bytes')
print('BOUNDS',result['bounds'])
