const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};
let rows = [], polling = false, activeJob = null;
function cell(row, value) { const td = document.createElement('td'); td.textContent = value; row.append(td); }
function render() {
  const query = document.querySelector('#search').value.toLowerCase(), category = document.querySelector('#category').value, sort = document.querySelector('#sort').value;
  const list = rows.filter(f => (!category || f.category === category) && `${f.name} ${f.path}`.toLowerCase().includes(query));
  list.sort((a,b) => sort === 'size' ? b.size-a.size : sort === 'modified' ? b.modified.localeCompare(a.modified) : a.path.localeCompare(b.path));
  const body = document.querySelector('#file-list'); body.replaceChildren();
  for (const file of list) { const tr = document.createElement('tr'); const td=document.createElement('td'); const check=document.createElement('input'); check.type='checkbox'; check.className='file-select'; check.value=file.path; check.setAttribute('aria-label',`Select ${file.name}`); td.append(check,document.createTextNode(` ${file.name} — ${file.path}`)); tr.append(td); cell(tr, file.category); cell(tr, formatBytes(file.size)); cell(tr, new Date(file.modified).toLocaleString()); cell(tr, [file.large && 'Large file', file.old_download && 'Older download (age only; not a recommendation)'].filter(Boolean).join(' · ') || '—'); body.append(tr); }
}
async function loadDashboard() {
  const [dr,sr] = await Promise.all([fetch('/api/disk'),fetch('/api/samples')]), disk=await dr.json(), samples=await sr.json();
  document.querySelector('#total').textContent=formatBytes(disk.total); document.querySelector('#used').textContent=formatBytes(disk.used); document.querySelector('#available').textContent=formatBytes(disk.available); document.querySelector('#usedbar').style.width=`${disk.total ? disk.used/disk.total*100 : 0}%`;
  rows=samples.files.map(f=>({...f,path:f.name,category:f.kind,modified:f.modified,size:0})); render();
}
async function scan() {
  const locations=[...document.querySelectorAll('.choices input[type=checkbox]:checked')].map(i=>i.value); if(!locations.length||polling)return;
  const status=document.querySelector('#scan-status'); status.textContent='Starting read-only scan…'; polling=true; document.querySelector('#cancel-scan').disabled=false;
  try { const response=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({locations})}), started=await response.json(); if(!response.ok)throw new Error(started.detail||'Could not start scan'); activeJob=started.job_id; let state;
    do { await new Promise(r=>setTimeout(r,500)); state=await (await fetch(`/api/scan/${encodeURIComponent(started.job_id)}`)).json(); status.textContent=`${state.status==='running'?'Scanning':state.status} · ${state.progress} files visited`; } while(state.status==='running');
    if(state.result){window.lastCompletedJob=started.job_id;showResults(state.result);}
  } catch(error){status.textContent=error.message;} finally{polling=false;activeJob=null;document.querySelector('#cancel-scan').disabled=true;}
}
function renderProposals(result) {
  const host=document.querySelector('#recommendations'); host.replaceChildren();
  const scanned=new Set(result.files.map(file=>file.path));
  for(const proposal of (result.recommendations || [])) {
    if(!scanned.has(proposal.source)) continue;
    const sourceRow=result.files.find(file=>file.path===proposal.source);
    if(!sourceRow || sourceRow.location!=='Downloads') continue;
    const section=document.createElement('div'); section.className='proposal'; section.dataset.source=proposal.source;
    const reason=document.createElement('p'); reason.textContent=proposal.reason; section.append(reason);
    const source=document.createElement('p'); source.textContent=`Source: ${proposal.source}`; section.append(source);
    const label=document.createElement('label'); label.textContent='Proposed destination';
    const destination=document.createElement('input'); destination.type='text'; destination.value=proposal.destination; destination.className='destination';
    const root=sourceRow.path.slice(0,sourceRow.path.indexOf('/Downloads') + '/Downloads'.length);
    const valid=()=>{const value=destination.value; const inside=value.startsWith(root+'/') && !value.split('/').includes('..') && ['Installers','Archives','Documents'].some(name=>value.startsWith(`${root}/${name}/`)); destination.setCustomValidity(inside?'':'Destination must remain inside an approved Downloads organization folder.'); return inside;};
    destination.addEventListener('input',valid); destination.classList.add('plan-destination'); label.append(destination); section.append(label);
    const include=document.createElement('input'); include.type='checkbox'; include.checked=true; include.className='plan-include'; include.setAttribute('aria-label','Include this proposal'); section.prepend(include);
    const remove=document.createElement('button'); remove.type='button'; remove.textContent='Remove proposal'; remove.addEventListener('click',()=>section.remove()); section.append(remove);
    const validation=document.createElement('small'); validation.textContent='Preview only — destination is editable; no changes will be made.'; section.append(validation);
    host.append(section);
  }
}
function showResults(result) {
  rows=result.files; document.querySelector('#table-label').textContent='READ-ONLY SCAN';
  const select=document.querySelector('#category'); select.replaceChildren(new Option('All categories','')); [...new Set(rows.map(f=>f.category))].sort().forEach(c=>select.add(new Option(c,c)));
  document.querySelector('#location-summary').textContent=Object.entries(result.locations).map(([n,v])=>`${n}: ${v.count} files · ${formatBytes(v.size)}${v.available?'':' (unavailable)'}`).join(' | ');
  const duplicates=document.querySelector('#duplicates'); duplicates.replaceChildren();
  for(const group of result.duplicates){const p=document.createElement('p');p.textContent=`${group.files.map(f=>f.path).join(' ↔ ')} — ${formatBytes(group.size)} each; estimated savings ${formatBytes(group.estimated_savings)} (logical estimate)`;duplicates.append(p);}
  const note=document.createElement('p');note.textContent=`Savings are estimated from duplicate logical bytes; APFS clones, compression, or hard links may mean less (or zero) space reclaimed. ${result.apfs_note || ''}`;duplicates.append(note);
  renderProposals(result);
  document.querySelector('#problems').textContent=result.problems.map(p=>`${p.location}: ${p.message}`).join(' ');render();
}
document.querySelector('#scan').addEventListener('click',scan);
async function resolveCollisions(action, results, target) {
  const resolved=[];
  for(const conflict of results){
    if(!conflict.collision){resolved.push(conflict);continue;}
    const nl=String.fromCharCode(10);
    const alternate=prompt(`Destination already exists:${nl}${conflict.destination}${nl}Enter an alternate basename, or cancel to skip:`,conflict.destination.split('/').pop());
    if(!alternate){resolved.push({...conflict,message:'Collision skipped; no file changed.'});continue;}
    if(alternate==='.'||alternate==='..'||alternate.includes('/')||alternate.includes(String.fromCharCode(92))||[...alternate].some(ch=>ch.charCodeAt(0)<32)){resolved.push({...conflict,message:'Unsafe alternate name; skipped.'});continue;}
    const altPath=`${conflict.destination.slice(0,conflict.destination.lastIndexOf('/')+1)}${alternate}`;
    if(!window.confirm(`Review alternate destination:${nl}${conflict.source} → ${altPath}${nl}${nl}Confirm this non-overwriting rename?`)){resolved.push({...conflict,message:'Alternate destination declined; skipped.'});continue;}
    const retryBody=action==='move'?{action,job_id:window.lastCompletedJob,sources:[conflict.source],destination:target,alternate_name:alternate}:{action:'apply-plan',job_id:window.lastCompletedJob,plan:[{source:conflict.source,destination:altPath}]};
    const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(retryBody)});
    resolved.push(...((await response.json()).results||[]));
  }
  return resolved;
}
async function act(action, destination=null, name=null) {
  const selected=[...document.querySelectorAll('.file-select:checked')].map(box=>box.value);
  let paths=selected;
  if(action==='undo') { const history=(await (await fetch('/api/activity')).json()).items||[]; const undoneIds=new Set(history.filter(item=>item.action==='undo'&&item.success).map(item=>item.undo_of)); const undoneLegacy=new Set(history.filter(item=>item.action==='undo'&&item.success).map(item=>`${item.source}|${item.destination}`)); const candidate=[...history].reverse().find(item=>(item.action==='move'||item.action==='create-folder')&&item.success&&(item.operation_id?!undoneIds.has(item.operation_id):item.action==='move'&&!undoneLegacy.has(`${item.destination}|${item.source}`))); if(!candidate){document.querySelector('#action-status').textContent='No restorable move or empty created folder; Trash must be restored in Finder.';return;} paths=[candidate.action==='move'?`${candidate.destination} → ${candidate.source}`:`Remove empty created folder: ${candidate.destination}`]; }
  if(!paths.length && action!=='undo' && action!=='create-folder') return;
  let target=destination;
  if(action==='move') {target=prompt('Destination folder (must be an existing approved folder):');if(!target)return;}
  const lineBreak=String.fromCharCode(10);
  const moveTargets=action==='move'?selected.map(source=>`${source} → ${target}/${source.split('/').pop()}`).join(lineBreak):'';
  const summary=`Review ${action}:${lineBreak}${moveTargets||paths.join(lineBreak)}${target&&action!=='move'?`${lineBreak}Destination: ${target}${name?`/${name}`:''}`:''}${lineBreak}${lineBreak}Confirm?`;
  if(!window.confirm(summary)) return;
  const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,job_id:window.lastCompletedJob,sources:selected,destination:target,name})});
  const data=await response.json();
  const results=(action==='move'||action==='apply-plan')?await resolveCollisions(action,data.results||[],target):(data.results||[]);
  document.querySelector('#action-status').textContent=results.map(x=>`${x.success?'Success':'Failed'}: ${x.source||''} ${x.message||x.destination||''}`).join(' · ')||data.detail||'Done'; loadHistory();
}
document.querySelector('#move-selected').addEventListener('click',()=>act('move'));
document.querySelector('#apply-plan').addEventListener('click',async()=>{
  const selected=[...document.querySelectorAll('.proposal')].filter(section=>section.querySelector('.plan-include').checked);
  if(!selected.length)return;
  for(const section of selected){const input=section.querySelector('.plan-destination');input.dispatchEvent(new Event('input'));if(!input.reportValidity())return;}
  const plan=selected.map(section=>({source:section.dataset.source,destination:section.querySelector('.plan-destination').value}));
  const summary=plan.map(item=>`${item.source} → ${item.destination}`).join(String.fromCharCode(10));
  if(!window.confirm(`Review organization plan:${String.fromCharCode(10)}${summary}${String.fromCharCode(10)}${String.fromCharCode(10)}Confirm all moves?`))return;
  const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'apply-plan',job_id:window.lastCompletedJob,plan})});
  const data=await response.json();const results=await resolveCollisions('apply-plan',data.results||[]);document.querySelector('#action-status').textContent=results.map(x=>`${x.success?'Success':'Failed'}: ${x.source||''} ${x.message||x.destination||''}`).join(' · ');loadHistory();
});
document.querySelector('#trash-selected').addEventListener('click',()=>act('trash'));
document.querySelector('#reveal-selected').addEventListener('click',()=>act('reveal'));
document.querySelector('#undo-move').addEventListener('click',()=>act('undo'));
document.querySelector('#create-folder').addEventListener('click',()=>{const parent=prompt('Existing approved parent folder path:'); const name=prompt('New folder name:'); if(parent&&name)act('create-folder',parent,name);});
async function loadHistory(){const data=await (await fetch('/api/activity')).json();const host=document.querySelector('#history-list');host.replaceChildren();for(const item of [...(data.items||[])].reverse()){const row=document.createElement('p');row.textContent=`${item.timestamp||''} · ${item.action||''} · ${item.success?'Success':'Recorded'} · ${item.source||item.destination||item.message||''}`;host.append(row);}}
loadHistory();
document.querySelector('#load-apps').addEventListener('click',async()=>{const data=await (await fetch('/api/applications')).json();const host=document.querySelector('#app-list');host.replaceChildren();for(const app of data.applications){const row=document.createElement('p');row.textContent=`${app.name} — ${app.size===null?'Unknown size':formatBytes(app.size)} — Last used: ${app.last_used||'Unknown'}`;host.append(row);}});
document.querySelector('#ollama-run').addEventListener('click',async()=>{const enabled=document.querySelector('#ollama-enabled').checked;if(!enabled){document.querySelector('#ollama-status').textContent='Enable explicitly to contact local Ollama.';return;}const metadata=rows.slice(0,100).map(f=>({category:f.category,size:f.size,reason:f.large?'large file':'review'}));const response=await fetch('/api/ollama',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,metadata,endpoint:document.querySelector('#ollama-endpoint').value,model:document.querySelector('#ollama-model').value})});const data=await response.json();document.querySelector('#ollama-status').textContent=data.text||data.detail||'No response';});
document.querySelector('#cancel-scan').addEventListener('click', async () => {
  if (!activeJob) return;
  const response = await fetch(`/api/scan/${encodeURIComponent(activeJob)}/cancel`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  if (!response.ok) document.querySelector('#scan-status').textContent = 'Could not cancel scan';
});
for(const selector of ['#search','#category','#sort'])document.querySelector(selector).addEventListener('input',render);
loadDashboard().catch(()=>{document.querySelector('#total').textContent='Unavailable';document.querySelector('#used').textContent='—';document.querySelector('#available').textContent='—';});
