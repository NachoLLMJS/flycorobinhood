import * as THREE from 'three';

// Derived from the Apache-2.0 NeuroMechFly v2 meshes and step tables.
// Pose replay, not live physics; no MaleCNS emulation is claimed.
export async function loadFlyModel({fetcher=globalThis.fetch,onProgress=()=>{}}={}) {
 const base='/assets/neuromechfly/';
 onProgress('Loading original anatomical model');
 const [mr,br]=await Promise.all([fetcher(base+'model.json'),fetcher(base+'geometry.bin')]);
 if(!mr.ok||!br.ok)throw new Error('Original fly assets could not be loaded');
 const [data,buffer]=await Promise.all([mr.json(),br.arrayBuffer()]);
 if(data.parts.length!==69||!data.walkFrames.length)throw new Error('Incomplete scientific model');
 const geometries=data.meshes.map(m=>{
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(buffer,m.vertexOffset,m.vertexCount*3),3));
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer,m.indexOffset,m.indexCount),1));
  g.computeVertexNormals();g.computeBoundingBox(); return g;
 });
 const materials=data.parts.map(p=>{
  const [r,g,b,a]=p.rgba;
  return new THREE.MeshStandardMaterial({color:new THREE.Color().setRGB(r,g,b,THREE.SRGBColorSpace),roughness:p.name.includes('eye')?.38:.7,metalness:.04,transparent:a<1,opacity:a,depthWrite:a>=1,side:THREE.DoubleSide});
 });
 // Proper rotation maps source X->Z, Y->X, Z->Y without mirroring.
 const basis=new THREE.Matrix4().set(0,1,0,0, 0,0,1,0, 1,0,0,0, 0,0,0,1);
 const rotation=new THREE.Quaternion().setFromRotationMatrix(basis);
 const scale=1.4/(data.bounds.max[0]-data.bounds.min[0]);
 const center=(data.bounds.max[0]+data.bounds.min[0])/2;
 const tmpQ=new THREE.Quaternion();
 function setPose(mesh,p){mesh.position.set(p[0],p[1],p[2]);mesh.quaternion.set(p[4],p[5],p[6],p[3]);}
 function createFly(){
  const root=new THREE.Group();root.name='NeuroMechFly';
  const body=new THREE.Group();body.quaternion.copy(rotation);body.scale.setScalar(scale);
  body.position.set(0,-data.bounds.min[2]*scale,-center*scale);root.add(body);
  const anatomy=data.parts.map((part,i)=>{
   const mesh=new THREE.Mesh(geometries[part.mesh],materials[i]);mesh.name=part.name;
   mesh.castShadow=true;mesh.receiveShadow=true;setPose(mesh,data.neutral[i]);body.add(mesh);return mesh;
  });
  root.userData.anatomy=anatomy;root.userData.body=body;
  root.userData.modelSource=data.sourceUrl;root.userData.motionKind='upstream kinematic joint replay';
  root.userData.walkMix=0;
  return root;
 }
 function animateFly(group,time,walking=false){
  const anatomy=group.userData.anatomy;if(!anatomy)return;
  const target=walking?1:0;
  group.userData.walkMix=THREE.MathUtils.lerp(group.userData.walkMix,target,.1);
  const mix=group.userData.walkMix;
  if(mix<.001){if(group.userData.posedIdle)return; anatomy.forEach((mesh,i)=>setPose(mesh,data.neutral[i]));group.userData.posedIdle=true;return;}
  group.userData.posedIdle=false;
  const f=((time/data.walkDuration%1+1)%1)*data.walkFrames.length;
  const a=data.walkFrames[Math.floor(f)],b=data.walkFrames[(Math.floor(f)+1)%data.walkFrames.length],alpha=f%1;
  anatomy.forEach((mesh,i)=>{
   const p=a[i],q=b[i],n=data.neutral[i];
   mesh.position.set(THREE.MathUtils.lerp(n[0],THREE.MathUtils.lerp(p[0],q[0],alpha),mix),THREE.MathUtils.lerp(n[1],THREE.MathUtils.lerp(p[1],q[1],alpha),mix),THREE.MathUtils.lerp(n[2],THREE.MathUtils.lerp(p[2],q[2],alpha),mix));
   mesh.quaternion.set(p[4],p[5],p[6],p[3]);tmpQ.set(q[4],q[5],q[6],q[3]);mesh.quaternion.slerp(tmpQ,alpha);
   tmpQ.copy(mesh.quaternion);mesh.quaternion.set(n[4],n[5],n[6],n[3]);mesh.quaternion.slerp(tmpQ,mix);
  });
 }
 onProgress('69 anatomical parts ready');
 return {createFly,animateFly,provenance:'NeuroMechFly v2 · original anatomy · Apache-2.0 · kinematic replay, not neural emulation'};
}
