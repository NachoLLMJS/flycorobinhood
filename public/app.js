export function flyPosition(index,time,meeting=false) {
  const angle=index*Math.PI/3 + Math.PI/6;
  const radius=meeting?3.25:4.5+1.15*Math.sin(time*.075+index*1.7);
  const a=angle+(meeting?0:.13*Math.sin(time*.12+index));
  return {x:Math.sin(a)*radius,y:0,z:Math.cos(a)*radius,heading:a+Math.PI};
}
export function safeURL(value) { try { const u=new URL(value); return /^https?:$/.test(u.protocol)?u.href:'#'; } catch { return '#'; } }
if (typeof document !== 'undefined') boot();

function boot() {
  const $=s=>document.querySelector(s), esc=escapeHTML;
  let state=null, tab='office', selected=null, selectedMeeting=null, replayIndex=-1, replayTimer=null, sceneAPI=null, busy=false, connected=false, lastError='', eventSource=null, eventReconnect=null, eventCursor=0, brainScene=null;
  const date=value=>value&&Number.isFinite(new Date(value).getTime())?new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'Not scheduled';
  const agent=id=>state?.agents?.find(a=>a.id===id);
  const meeting=()=>state?.meetings?.find(m=>m.id===selectedMeeting);
  const empty=text=>`<div class="empty">${esc(text)}</div>`;
  function notice(text){$('#notice span').textContent=text;$('#notice').hidden=false;}
  $('#notice button').onclick=()=>$('#notice').hidden=true;
  async function request(path,body){
    const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(120000)});
    let data;try{data=await response.json();}catch{throw new Error(`Server returned an unreadable response (${response.status}).`);}
    if(!response.ok||data.error)throw new Error(typeof data.error==='string'?data.error:data.error?.message||data.message||`Request failed (${response.status}).`);
    return data;
  }
  function sources(ids){return (ids||[]).map(id=>{const f=meeting()?.sources?.find(f=>f.id===id)||state?.findings?.find(f=>f.id===id);return f?`<a class="source-link" target="_blank" rel="noopener noreferrer" href="${esc(safeURL(f.url))}">↗ ${esc(f.title)}</a>`:`<span class="timestamp">Source ${esc(id)} · not in current findings</span>`;}).join('<br>');}
  function findings(items){return items.length?items.map(f=>`<article class="finding"><span class="timestamp">${esc(agent(f.agentId)?.name||'Research')} / ${esc(date(f.createdAt))}</span><h3>${esc(f.title)}</h3><p>${esc(f.summary)}</p><a target="_blank" rel="noopener noreferrer" href="${esc(safeURL(f.url))}">Read original source ↗</a></article>`).join(''):empty('No findings yet. Start a research cycle to collect real, linked sources.');}
  function setPanel(open){$('#inspector').classList.toggle('closed',!open);$('#toggle-inspector').setAttribute('aria-expanded',String(open));}
  function selectTab(next){$('.scene-title').hidden=false;tab=next;selected=null;document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-pressed',String(b.dataset.tab===tab));});setPanel(next!=='office'||innerWidth>760);renderPanel();}
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>selectTab(b.dataset.tab));
  $('.brand').onclick=e=>{e.preventDefault();selectTab('office');sceneAPI?.reset();};
  $('#close-inspector').onclick=()=>setPanel(false);
  $('#toggle-inspector').onclick=()=>setPanel($('#inspector').classList.contains('closed'));
  $('#reset-camera').onclick=()=>{$('.scene-title').hidden=false;sceneAPI?.reset();};
  function selectAgent(id){$('.scene-title').hidden=true;selected=id;tab='agent';setPanel(true);sceneAPI?.focus(id);renderPanel();renderDock();openBrainModal(id);}
  function latestInterventions(id){
    return (state?.meetings||[]).flatMap(m=>(m.messages||[]).filter(msg=>msg.agentId===id).map(msg=>({msg,meeting:m}))).slice(0,5);
  }
  function renderBrainInterventions(id){
    const a=agent(id), target=$('#brain-interventions'); if(!target)return;
    const items=latestInterventions(id);
    target.innerHTML=`<div class="brain-interventions-head"><div><div class="brain-modal-role">${esc(a?.role||'Research agent')}</div><h3>${esc(a?.name||'Fly')}</h3></div><div class="brain-modal-section-label">LATEST MEETING INTERVENTIONS</div></div><div class="brain-intervention-list">${items.length?items.map(({msg,meeting:m})=>`<article class="brain-intervention"><span>${esc(date(m.startedAt))} · ${esc(m.status||'meeting')}</span><p>${esc(msg.text)}</p></article>`).join(''):empty('No meeting interventions recorded yet.')}</div>`;
  }
  async function openBrainModal(id){
    const a=agent(id); if(!a)return;
    $('#brain-modal-title').textContent=`${a.name} · mapped brain`;
    renderBrainInterventions(id); $('#brain-modal').hidden=false; document.body.classList.add('modal-open');
    if(brainScene){brainScene.dispose();brainScene=null;}
    try{
      const T=await import('three'); const {OrbitControls}=await import('three/addons/controls/OrbitControls.js'); const {GLTFLoader}=await import('three/addons/loaders/GLTFLoader.js');
      const host=$('#brain-view');host.replaceChildren();const renderer=new T.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor(0,0);host.append(renderer.domElement);
      const scene=new T.Scene(),camera=new T.PerspectiveCamera(38,1,.01,100);camera.position.set(0,.05,3.45);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enableZoom=false;controls.enablePan=false;controls.autoRotate=true;controls.autoRotateSpeed=1.1;controls.target.set(0,0,0);
      scene.add(new T.HemisphereLight('#fff7dc','#624d24',2.4));const key=new T.DirectionalLight('#fff0b0',4);key.position.set(2,3,4);scene.add(key);
      const root=new T.Group();scene.add(root);const loader=new GLTFLoader();
      const gltf=await loader.loadAsync('/assets/flywire/fly-brain.glb');const content=gltf.scene;content.traverse(o=>{o.visible=true;if(o.isMesh){o.frustumCulled=false;o.material=new T.MeshBasicMaterial({color:'#ffd36a',wireframe:true,transparent:true,opacity:.34,side:T.DoubleSide});}});const box=new T.Box3().setFromObject(content),size=box.getSize(new T.Vector3()),center=box.getCenter(new T.Vector3()),fit=2.7/Math.max(size.x,size.y,size.z);content.scale.setScalar(fit);content.position.set(-center.x*fit,-center.y*fit,-center.z*fit);content.rotation.set(-.08,0,.02);root.add(content);
      const flyHost=$('#fly-view');flyHost.replaceChildren();const flyRenderer=new T.WebGLRenderer({antialias:true,alpha:true});flyRenderer.setPixelRatio(Math.min(devicePixelRatio,2));flyRenderer.setClearColor(0,0);flyHost.append(flyRenderer.domElement);const flyScene=new T.Scene();const flyCamera=new T.PerspectiveCamera(30,1,.01,100);flyCamera.position.set(0,1.05,3.8);const flyControls=new OrbitControls(flyCamera,flyRenderer.domElement);flyControls.enableDamping=true;flyControls.enableZoom=false;flyControls.enablePan=false;flyControls.autoRotate=true;flyControls.autoRotateSpeed=.8;flyControls.target.set(0,.45,0);flyScene.add(new T.HemisphereLight('#fff8e5','#65543c',2.5));const flyKey=new T.DirectionalLight('#fff3c0',3.5);flyKey.position.set(2,4,3);flyScene.add(flyKey);const {loadFlyModel}=await import('/fly-model.js');const flyModel=await loadFlyModel();const fly=flyModel.createFly();fly.scale.setScalar(.82);fly.position.y=.08;fly.rotation.y=Math.PI*.5;flyScene.add(fly);
      const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(w&&h){renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}const fw=flyHost.clientWidth,fh=flyHost.clientHeight;if(fw&&fh){flyRenderer.setSize(fw,fh,false);flyCamera.aspect=fw/fh;flyCamera.updateProjectionMatrix();}};const ro=new ResizeObserver(resize);ro.observe(host);ro.observe(flyHost);resize();let active=true;renderer.setAnimationLoop(()=>{if(active){controls.update();renderer.render(scene,camera);flyControls.update();flyModel.animateFly(fly,performance.now()/1000,false);flyRenderer.render(flyScene,flyCamera);}});brainScene={dispose(){active=false;ro.disconnect();renderer.setAnimationLoop(null);flyRenderer.setAnimationLoop(null);renderer.dispose();flyRenderer.dispose();controls.dispose();flyControls.dispose();}};
    }catch(e){$('#brain-loading').textContent='The mapped brain could not be loaded.';console.error(e);}
  }
  function closeBrainModal(){if(brainScene){brainScene.dispose();brainScene=null;}$('#brain-modal').hidden=true;document.body.classList.remove('modal-open');}
  $('#close-brain-modal').onclick=closeBrainModal;$('#brain-modal').onclick=e=>{if(e.target===$('#brain-modal'))closeBrainModal();};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeBrainModal();});
  function renderDock(){
    const agents=state?.agents||[];
    $('#agent-dock').innerHTML=agents.length?agents.slice(0,6).map(a=>`<button class="agent ${selected===a.id?'selected':''}" data-agent="${esc(a.id)}"><span class="agent-avatar">✳</span><span><strong>${esc(a.name)}</strong><small>${esc(a.status||'Unknown')}</small></span></button>`).join(''):'<span class="dock-empty">Waiting for agent identities from the server…</span>';
    $('#agent-dock').querySelectorAll('[data-agent]').forEach(b=>{const a=agent(b.dataset.agent);if(/^#[\da-f]{3,8}$/i.test(a?.color||''))b.style.setProperty('--agent-color',a.color);b.onclick=()=>selectAgent(b.dataset.agent);});
    sceneAPI?.identities(agents,selected);
  }
  function renderPanel(){
    const panel=$('#panel-content'), scroll=panel.scrollTop;
    const titles={office:'The observation desk',research:'Research journal',meetings:'Around the table',launch:'The launch desk',science:'A body of real science',agent:agent(selected)?.name||'Agent'};
    $('#panel-title').textContent=titles[tab];
    if(tab==='office') panel.innerHTML=`<span class="panel-kicker">A VERY SMALL COMPANY</span><h3 class="panel-heading">Good questions.<br>Shared discoveries.</h3><p class="muted">An open office for six research agents. Follow their sources, sit in on a meeting, and watch ideas take shape.</p><div class="section-rule"><span class="eyebrow">LATEST FIELD NOTES</span>${findings((state?.findings||[]).slice(0,2))}</div>`;
    if(tab==='research')panel.innerHTML=`<span class="panel-kicker">SOURCES BEFORE OPINIONS</span><p>Findings collected automatically by the team. Every entry links back to its original source.</p>${findings(state?.findings||[])}`;
    if(tab==='agent'){const a=agent(selected);panel.innerHTML=a?`<span class="panel-kicker">${esc(a.role)}</span><h3 class="panel-heading">${esc(a.name)}</h3>${a.memory?`<div class="provider-note"><strong>Persistent memory / last meeting</strong><p>${esc(a.memory)}</p></div>`:''}<p class="muted">Current state: ${esc(a.status||'Unknown')}. Movement is a visual representation, not a neural simulation.</p><div class="section-rule"><span class="eyebrow">THIS AGENT’S SOURCES</span>${findings((state?.findings||[]).filter(f=>f.agentId===a.id))}</div>`:empty('Agent information is unavailable.');}
    if(tab==='meetings'){
      const m=meeting();
      panel.innerHTML=`<span class="panel-kicker">THE CONFERENCE ROOM</span><p class="muted">Real meeting transcripts, replayed in sequence. No scripted agent dialogue.</p>${m?`<div class="provider-note"><strong>${esc(m.status)} · ${esc(date(m.startedAt))}</strong><p>${esc(m.summary||'No summary available yet.')}</p></div><div class="replay-controls"><button id="replay">${replayTimer?'Restart':'Replay'} transcript ▷</button><button id="stop-replay">Stop □</button></div>${(m.messages||[]).map((msg,i)=>`<article class="message ${i===replayIndex?'current':''}"><strong>${esc(agent(msg.agentId)?.name||msg.agentId)}</strong><p>${esc(msg.text)}</p>${sources(msg.sourceIds)}</article>`).join('')||empty('No messages have been recorded for this meeting.')}`:empty('Choose a previous meeting or gather the team to begin.')}<div class="section-rule"><span class="eyebrow">MEETING HISTORY</span>${(state?.meetings||[]).map(m=>`<div class="meeting-item"><button data-meeting="${esc(m.id)}">${esc(date(m.startedAt))}<span class="timestamp"> / ${esc(m.status)}</span></button></div>`).join('')||empty('No meetings yet.')}</div>`;
      panel.querySelectorAll('[data-meeting]').forEach(b=>b.onclick=()=>{stopReplay();selectedMeeting=b.dataset.meeting;renderPanel();});
      if($('#replay'))$('#replay').onclick=startReplay;
      if($('#stop-replay'))$('#stop-replay').onclick=()=>{stopReplay();renderPanel();};
    }
    if(tab==='launch')panel.innerHTML=`<span class="panel-kicker">HUMAN APPROVAL REQUIRED</span><h3 class="panel-heading">Ideas, not<br>automatic launches.</h3><p class="muted">This desk is a proposal queue. Nothing here deploys a contract, signs a transaction, or moves funds. If the founder eventually approves a launch, the intended venue is Pons on Robinhood Chain. That intent does not establish eligibility, readiness, or a live token.</p>${(state?.proposals||[]).map(p=>`<article class="proposal"><span class="chip">${esc(p.status||'Pending review')} · approval only</span><h3>${esc(p.title||p.name||'Untitled proposal')}</h3>${p.status==='pending'&&!state?.publicReadOnly?`<button data-approve="${esc(p.id)}">Mark plan reviewed · no transaction</button>`:''}${Object.entries(p).filter(([k])=>!['id','title','name','status'].includes(k)).map(([k,v])=>`<div class="field"><b>${esc(k.replace(/([A-Z])/g,' $1'))}</b>${esc(typeof v==='object'?JSON.stringify(v,null,2):v)}</div>`).join('')}</article>`).join('')||empty('No proposals submitted. The desk is intentionally empty until the team produces one.')}`;
    if(tab==='science')panel.innerHTML=`<span class="panel-kicker">HONEST ABOUT THE MODEL</span><h3 class="panel-heading">A scientific body.<br>Not a digital brain.</h3><p class="muted">The flies use original NeuroMechFly anatomical meshes. Their walking and office behavior are visual animation, not a complete brain emulation or a validated biomechanical simulation.</p><p class="muted">MaleCNS is a connectome map, not an LLM. Research cycles are generated by the connected local Hermes worker. This project has no affiliation with Google.</p><div class="provider-note"><strong>Geometry provenance</strong><p>${esc(sceneAPI?.provenance||'Original NeuroMechFly assets. Detailed loader provenance appears after the scene loads.')}</p></div><div class="science-links"><a href="/specimen.html">Inspect the original fly in 3D ↗</a><a href="/licenses/NeuroMechFly-Apache-2.0.txt">Model license ↗</a><a href="https://github.com/NeLy-EPFL/flygym" target="_blank" rel="noopener noreferrer">NeuroMechFly / FlyGym — original project ↗</a><a href="https://neuromechfly.org/" target="_blank" rel="noopener noreferrer">NeuroMechFly research ↗</a><a href="https://www.janelia.org/project-team/flyem" target="_blank" rel="noopener noreferrer">FlyEM / connectomics context ↗</a></div><div class="section-rule"><span class="eyebrow">CREDITS & LICENSES</span><p class="muted">NeuroMechFly / FlyGym contributors: original model and step tables distributed in the Apache-2.0 repository. Three.js: MIT. MaleCNS data is not loaded or simulated by this application.</p></div>`;
    panel.querySelectorAll('[data-approve]').forEach(b=>b.onclick=()=>action('/api/proposals/'+encodeURIComponent(b.dataset.approve)+'/approve'));
    panel.scrollTop=scroll;
  }
  function stopReplay(){clearInterval(replayTimer);replayTimer=null;replayIndex=-1;$('#speech').hidden=true;}
  function startReplay(){stopReplay();if(!meeting()?.messages?.length){notice('This meeting has no recorded messages to replay.');return;}replayIndex=0;showMessage();replayTimer=setInterval(()=>{replayIndex++;if(replayIndex>=meeting().messages.length){stopReplay();renderPanel();return;}showMessage();},8500);renderPanel();}
  function showMessage(){const msg=meeting()?.messages?.[replayIndex];if(!msg)return;$('#speech').innerHTML=`<strong>${esc(agent(msg.agentId)?.name||msg.agentId)} / TRANSCRIPT REPLAY</strong><p>${esc(msg.text)}</p>`;$('#speech').hidden=false;renderPanel();}
  async function refresh(){try{state=await request('/api/state');connected=true;
    if(!replayTimer){const live=state.meetings?.find(m=>m.status==='running');const msg=live?.messages?.at(-1);if(msg){$('#speech').innerHTML=`<strong>${esc(agent(msg.agentId)?.name||msg.agentId)} / LIVE MEETING</strong><p>${esc(msg.text)}</p>`;$('#speech').hidden=false;}else{$('#speech').hidden=true;}}
    lastError='';$('#provider-chip').textContent=`${state.provider?.ready?'●':'○'} ${stateLabel(state)}`;$('#schedule-chip').textContent=state.scheduler?.enabled?'Automatic 2h cycle':'Cycle unavailable';$('#next-run').textContent=state.scheduler?.enabled?`Next automatic cycle: ${date(state.scheduler.nextRunAt)}`:'Automatic cycle is unavailable.';renderDock();renderPanel();if(!$('#brain-modal').hidden&&selected)renderBrainInterventions(selected);}catch(e){connected=false;$('#provider-chip').textContent='○ Server disconnected';$('#schedule-chip').textContent='Schedule unavailable';$('#next-run').textContent='Live company state unavailable.';if(lastError!==e.message){notice(`State unavailable: ${e.message}`);lastError=e.message;}renderPanel();}}
  function connectRealtime(){
    if(!('EventSource' in window))return;
    clearTimeout(eventReconnect);eventSource?.close();
    eventSource=new EventSource('/api/events?after='+eventCursor);
    const onEvent=event=>{eventCursor=Math.max(eventCursor,Number(event.lastEventId)||0);refresh();};
    ['research.updated','meeting.updated','proposal.updated','scheduler.updated'].forEach(type=>eventSource.addEventListener(type,onEvent));
    eventSource.onerror=()=>{eventSource.close();eventReconnect=setTimeout(connectRealtime,5000);};
  }
  async function action(path,body={}){if(busy)return;busy=true;document.querySelectorAll('#research-button,#meeting-button,#scheduler').forEach(el=>el.disabled=true);try{const result=await request(path,body);notice(result.errors?.length?`Research completed with ${result.errors.length} source errors: ${result.errors.map(e=>e.url+' ('+e.reason+')').join('; ')}`:path==='/api/scheduler'?'Scheduler updated.':'Request accepted. The server state will reflect the result.');await refresh();if(path==='/api/meeting'){selectedMeeting=state?.meetings?.[0]?.id;selectTab('meetings');}}catch(e){notice(e.message);}finally{busy=false;document.querySelectorAll('#research-button,#meeting-button,#scheduler').forEach(el=>el.disabled=false);}}
  if($('#research-button'))$('#research-button').onclick=()=>action('/api/research');if($('#meeting-button'))$('#meeting-button').onclick=()=>action('/api/meeting');if($('#scheduler'))$('#scheduler').onchange=e=>action('/api/scheduler',{enabled:e.target.checked});
  if(innerWidth<=760)setPanel(false);
  renderPanel();refresh();connectRealtime();setInterval(refresh,15000);

  let loading=false;
  async function loadScene(){
    if(loading)return;loading=true;$('#loading').hidden=false;$('#retry-scene').hidden=true;$('#load-progress').value=0;$('#load-message').textContent='Preparing the WebGL renderer…';
    try{
      const THREE=await import('three'); const {OrbitControls}=await import('three/addons/controls/OrbitControls.js');
      $('#load-progress').value=1;$('#load-message').textContent='Loading original NeuroMechFly anatomy…';
      const {loadFlyModel}=await import('/fly-model.js');
      let timer;const model=await Promise.race([loadFlyModel(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Anatomy loading timed out. Check the model assets and retry.')),90000);})]).finally(()=>clearTimeout(timer));
      $('#load-progress').value=2;$('#load-message').textContent='Building the office and placing six anatomical models…';
      sceneAPI=makeScene(THREE,OrbitControls,model,$('#scene'),selectAgent,()=>!!replayTimer||(state?.meetings||[]).some(m=>['running','in_progress','active'].includes(m.status)));
      sceneAPI.identities(state?.agents||[],selected);$('#load-progress').value=3;$('#loading').hidden=true;if(tab==='science')renderPanel();
    }catch(e){$('#load-message').textContent=`Scene unavailable: ${e.message}. Research controls remain available.`;$('#retry-scene').hidden=false;$('#load-progress').removeAttribute('value');console.error(e);}finally{loading=false;}
  }
  $('#retry-scene').onclick=loadScene;loadScene();
}

function makeScene(T,OrbitControls,model,container,onSelect,inMeeting){
  const scene=new T.Scene();scene.background=new T.Color('#e7e2d8');scene.fog=new T.Fog('#e7e2d8',25,65);
  const renderer=new T.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.27;container.replaceChildren(renderer.domElement);
  const camera=new T.PerspectiveCamera(36,1,.1,100);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.055;controls.minDistance=5;controls.maxDistance=33;controls.maxPolarAngle=Math.PI*.47;controls.minPolarAngle=.15;controls.target.set(0,.4,0);
  const reset=()=>{camera.position.set(15.7,17.8,20.5);controls.target.set(0,.25,0);};reset();
  scene.add(new T.HemisphereLight('#fff8e8','#888a77',2.1));const sun=new T.DirectionalLight('#fff1cd',4.4);sun.position.set(-7,15,5);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);Object.assign(sun.shadow.camera,{left:-13,right:13,top:13,bottom:-13,near:.5,far:45});sun.shadow.bias=-.0004;sun.shadow.normalBias=.025;sun.shadow.radius=4;scene.add(sun);
  const material=(color,roughness=.7,metalness=0)=>new T.MeshStandardMaterial({color,roughness,metalness});const cream=material('#dbd3bc'),dark=material('#363e36'),gold=material('#b4924f',.35,.55),wood=material('#82765d'),white=material('#eee8d7'),screen=material('#344b40');
  function mesh(geo,mat,x,y,z){const m=new T.Mesh(geo,mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;scene.add(m);return m;}
  const box=(w,h,d,mat,x,y,z)=>mesh(new T.BoxGeometry(w,h,d),mat,x,y,z);
  const cyl=(r,h,mat,x,y,z)=>mesh(new T.CylinderGeometry(r,r,h,72),mat,x,y,z);
  // Architectural objects are procedural; every insect comes exclusively from loadFlyModel.
  const base=box(18,.42,14,cream,0,-.27,0);box(18.15,.09,14.15,gold,0,-.46,0);const floor=box(17.85,.06,13.85,material('#c9c4b4'),0,-.025,0);
  const grid=new T.GridHelper(18,36,'#aaa692','#b8b3a3');grid.position.y=.011;grid.material.transparent=true;grid.material.opacity=.28;scene.add(grid);grid.scale.z=14/18;
  // Low perimeter retains a clear view of the original anatomical models.
  box(18,.55,.19,cream,0,.27,-6.9);box(.19,.55,14,cream,-8.9,.27,0);
  box(18,3.7,.2,material('#d5cfbb'),0,1.85,-7.05);
  for(let i=0;i<15;i++)box(.05,3.4,.09,wood,-8.3+i*1.18,1.85,-6.88);
  box(6.7,2.15,.12,dark,-4.4,2.3,-6.87);
  const signCanvas=document.createElement('canvas');signCanvas.width=1024;signCanvas.height=360;const ctx=signCanvas.getContext('2d');ctx.fillStyle='#343d35';ctx.fillRect(0,0,1024,360);ctx.fillStyle='#e5d9b9';ctx.font='500 68px Arial';ctx.fillText('FLYCO ROBINHOOD',50,166);ctx.font='22px monospace';ctx.fillStyle='#acaa8b';ctx.fillText('SMALL MINDS. BIG QUESTIONS.',72,230);const signTexture=new T.CanvasTexture(signCanvas);signTexture.colorSpace=T.SRGBColorSpace;mesh(new T.PlaneGeometry(6.3,2.12),new T.MeshBasicMaterial({map:signTexture}),-4.4,2.3,-6.79);
  // Circular forum, recessed bronze ring, notebooks and warm task lighting.
  cyl(3.05,.025,material('#a8a48e'),0,.015,0);cyl(2.25,.15,dark,0,.88,0);cyl(2.27,.035,gold,0,.82,0);cyl(.85,.8,dark,0,.4,0);cyl(1.02,.055,gold,0,.06,0);cyl(.46,.012,gold,0,.968,0);
  for(let i=0;i<6;i++){const a=i*Math.PI/3;const x=Math.sin(a),z=Math.cos(a);const book=box(.39,.035,.28,white,x*1.72,.98,z*1.72);book.rotation.y=a;const pencil=box(.26,.018,.022,gold,x*1.72,1.01,z*1.72+.17);pencil.rotation.y=a;}
  // Work bays are at the edge; agents move in the unobstructed central annulus.
  for(const [x,z,rot] of [[-6,-4.7,0],[0,-5.4,0],[6,-4.7,0],[-6,4.7,Math.PI],[0,5.4,Math.PI],[6,4.7,Math.PI]]){
    const desk=new T.Group();desk.position.set(x,0,z);desk.rotation.y=rot;scene.add(desk);
    function part(w,h,d,mat,px,py,pz){const m=new T.Mesh(new T.BoxGeometry(w,h,d),mat);m.position.set(px,py,pz);m.castShadow=true;m.receiveShadow=true;desk.add(m);return m;}
    part(2.25,.12,1,wood,0,.92,0);part(2.25,.035,1.02,gold,0,.86,0);part(.1,.87,.7,dark,-.91,.43,0);part(.1,.87,.7,dark,.91,.43,0);part(.88,.59,.055,dark,0,1.4,-.22);part(.77,.47,.017,screen,0,1.4,-.181);part(.06,.19,.06,gold,0,1.04,-.22);part(.35,.035,.22,dark,0,.995,-.22);part(.6,.025,.2,cream,0,1,.23);part(.32,.035,.42,white,.7,1,.1);
    part(.035,.62,.035,gold,-.8,1.29,-.26);part(.35,.055,.21,gold,-.7,1.59,-.23);const light=new T.PointLight('#ffcf77',5,3,2);light.position.set(-.7,1.49,-.1);desk.add(light);
  }
  for(const [x,z] of [[-7.8,-5.8],[7.8,-5.8],[-7.8,5.8],[7.8,5.8]]){cyl(.38,.62,dark,x,.31,z);for(let i=0;i<7;i++){const a=i*2.4;const leaf=mesh(new T.SphereGeometry(1,10,8),material(i%2?'#636e47':'#747f52'),x+Math.cos(a)*.22,1.05+Math.sin(i)*.15,z+Math.sin(a)*.22);leaf.scale.set(.16,.65,.22);leaf.rotation.z=Math.cos(a)*.45;}}
  const halo=new T.Mesh(new T.TorusGeometry(2.05,.026,8,100),gold);halo.rotation.x=Math.PI/2;halo.position.y=4.9;scene.add(halo);const pendant=new T.PointLight('#ffd68a',12,10,2);pendant.position.set(0,4.3,0);scene.add(pendant);
  const labels=document.querySelector('#labels');labels.replaceChildren();const flies=[];let identities=[];
  const shadowCanvas=document.createElement('canvas');shadowCanvas.width=64;shadowCanvas.height=64;const sc=shadowCanvas.getContext('2d'),gradient=sc.createRadialGradient(32,32,1,32,32,32);gradient.addColorStop(0,'rgba(32,24,10,.42)');gradient.addColorStop(1,'rgba(32,24,10,0)');sc.fillStyle=gradient;sc.fillRect(0,0,64,64);const shadowTexture=new T.CanvasTexture(shadowCanvas);
  for(let i=0;i<6;i++){
    const fly=model.createFly();fly.userData.agentIndex=i;scene.add(fly);const p=flyPosition(i,0);fly.position.set(p.x,0,p.z);fly.rotation.y=p.heading;fly.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});
    const label=document.createElement('span');label.className='fly-label';label.hidden=true;labels.append(label);const shadow=new T.Mesh(new T.PlaneGeometry(1.9,1.9),new T.MeshBasicMaterial({map:shadowTexture,transparent:true,depthWrite:false}));shadow.rotation.x=-Math.PI/2;shadow.position.y=.019;scene.add(shadow);flies.push({group:fly,label,shadow});
  }
  const pointer=new T.Vector2(),raycaster=new T.Raycaster();let down=null;
  renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);renderer.domElement.addEventListener('pointerup',e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>6)return;const r=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(pointer,camera);const hits=raycaster.intersectObjects(flies.map(f=>f.group),true);if(hits.length){let o=hits[0].object;while(o&&o.userData.agentIndex===undefined)o=o.parent;const a=identities[o?.userData.agentIndex];if(a)onSelect(a.id);}});
  new ResizeObserver(()=>{const w=container.clientWidth,h=container.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(container);
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;const clock=new T.Clock();let time=0;const projection=new T.Vector3();
  renderer.setAnimationLoop(()=>{const dt=Math.min(clock.getDelta(),.05);if(!reduced)time+=dt;const gathered=inMeeting();for(let i=0;i<flies.length;i++){const f=flies[i],p=flyPosition(i,time,gathered),old=f.group.position.clone();f.group.position.lerp(new T.Vector3(p.x,0,p.z),1-Math.exp(-dt*1.8));const motion=f.group.position.clone().sub(old);const moving=motion.length()>.0001;const heading=moving?Math.atan2(motion.x,motion.z):p.heading;f.group.rotation.y+=Math.atan2(Math.sin(heading-f.group.rotation.y),Math.cos(heading-f.group.rotation.y))*Math.min(1,dt*3);model.animateFly(f.group,time+i*1.9,!reduced&&moving);f.shadow.position.x=f.group.position.x;f.shadow.position.z=f.group.position.z;projection.copy(f.group.position).add(new T.Vector3(0,1.22,0)).project(camera);f.label.style.left=`${(projection.x*.5+.5)*container.clientWidth}px`;f.label.style.top=`${(-projection.y*.5+.5)*container.clientHeight}px`;f.label.hidden=!identities[i]||projection.z>1||Math.abs(projection.x)>1||Math.abs(projection.y)>1;}
    controls.update();renderer.render(scene,camera);
  });
  renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();const el=document.querySelector('#loading');el.hidden=false;document.querySelector('#load-message').textContent='WebGL context lost. Reload the page to restore the scene. Research remains available.';document.querySelector('#retry-scene').hidden=false;document.querySelector('#retry-scene').onclick=()=>location.reload();});
  return {provenance:model.provenance,reset,focus(id){const i=identities.findIndex(a=>a.id===id),f=flies[i];if(!f)return;controls.target.copy(f.group.position).add(new T.Vector3(0,.35,0));camera.position.copy(f.group.position).add(new T.Vector3(3,3.7,4.6));},identities(agents,selected){identities=agents.slice(0,6);flies.forEach((f,i)=>{f.label.textContent=identities[i]?.name||'';f.label.classList.toggle('selected',identities[i]?.id===selected);if(/^#[\da-f]{3,8}$/i.test(identities[i]?.color||''))f.label.style.setProperty('--agent-color',identities[i].color);});}};
}

export function stateLabel(state) { return !state ? 'Connecting' : state.running ? 'Hermes working' : 'Hermes local worker'; }
export function escapeHTML(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
