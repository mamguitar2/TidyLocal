const formatBytes = (bytes) => {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};
const TYPE_LABELS = {images:'Photos',videos:'Videos',documents:'Documents',audio:'Audio',archives:'Archives',installers:'Installers',code:'Code',system:'macOS metadata',other:'Other'};
const TYPE_COLORS = {images:'#70a889',videos:'#6d8fc1',documents:'#d3a455',audio:'#9b7dc5',archives:'#d17c70',installers:'#83949d',code:'#55a4a2',system:'#9da79f',other:'#b9aaa0'};
window.FILE_TYPE_LABELS = TYPE_LABELS;
window.FILE_TYPE_COLORS = TYPE_COLORS;
window.renderFileTypeBars = (host,counts,emptyMessage) => {
  host.replaceChildren();
  const largest = Math.max(1,...counts.values());
  for (const [key,label] of Object.entries(TYPE_LABELS).filter(([type])=>!['code','system'].includes(type))) {
    const count = counts.get(key) || 0;
    if (!count) continue;
    const row = document.createElement('div');
    row.className = 'organizer-category-row';
    const name = document.createElement('span');
    name.textContent = label;
    const track = document.createElement('div');
    track.className = 'organizer-category-track';
    const fill = document.createElement('i');
    fill.style.width = `${Math.max(3,count/largest*100)}%`;
    fill.style.backgroundColor = TYPE_COLORS[key] || TYPE_COLORS.other;
    track.append(fill);
    const amount = document.createElement('strong');
    amount.textContent = count.toLocaleString();
    row.append(name,track,amount);
    host.append(row);
  }
  if (!counts.size) {
    const empty = document.createElement('p');
    empty.className = 'organizer-detail-empty';
    empty.textContent = emptyMessage;
    host.append(empty);
  }
};

function drawDonut(canvas, slices, center, subtitle) {
  const context = canvas.getContext('2d');
  const width = 260, height = 230, ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  context.setTransform(ratio,0,0,ratio,0,0);
  context.clearRect(0,0,width,height);
  const total = slices.reduce((sum,item)=>sum+item.value,0);
  if (!total) slices = [{value:1,color:'#e6ebe5'}];
  const chartTotal = slices.reduce((sum,item)=>sum+item.value,0);
  let angle = -Math.PI / 2;
  for (const item of slices) {
    const next = angle + item.value / chartTotal * Math.PI * 2;
    context.beginPath();
    context.arc(120,115,78,angle,next);
    context.strokeStyle = item.color;
    context.lineWidth = 30;
    context.stroke();
    angle = next;
  }
  context.textAlign = 'center';
  context.fillStyle = '#263b32';
  context.font = '600 17px DM Sans, sans-serif';
  context.fillText(center,120,112);
  context.fillStyle = '#7d8981';
  context.font = '11px DM Sans, sans-serif';
  context.fillText(subtitle,120,132);
}

function renderStorageChart(files) {
  const totals = new Map();
  for (const file of files) {
    const key = file.category || 'other';
    const item = totals.get(key) || {bytes:0,count:0};
    item.bytes += file.size || 0;
    item.count += 1;
    totals.set(key,item);
  }
  const groups = [...totals.entries()].map(([key,value]) => ({key,label:TYPE_LABELS[key] || 'Other',color:TYPE_COLORS[key] || TYPE_COLORS.other,...value})).sort((a,b)=>b.bytes-a.bytes);
  const totalBytes = groups.reduce((sum,item)=>sum+item.bytes,0);
  const weights = groups.map(item => totalBytes ? item.bytes : item.count);
  drawDonut(document.querySelector('#type-chart'), groups.map((item,index)=>({value:weights[index],color:item.color})), formatBytes(totalBytes), `${files.length} files`);

  const legend = document.querySelector('#type-legend');
  legend.replaceChildren();
  const largestGroup = Math.max(1, ...groups.map(item => item.bytes));
  for (const item of groups) {
    const row = document.createElement('div');
    row.className = 'type-legend-row';
    const marker = document.createElement('i');
    marker.style.backgroundColor = item.color;
    const copy = document.createElement('div');
    copy.className = 'type-legend-copy';
    const label = document.createElement('span');
    label.textContent = `${item.label} · ${item.count} files`;
    const track = document.createElement('div');
    track.className = 'type-bar-track';
    const fill = document.createElement('i');
    fill.style.width = `${item.bytes ? Math.max(2, item.bytes / largestGroup * 100) : 0}%`;
    fill.style.backgroundColor = item.color;
    track.append(fill);
    copy.append(label,track);
    const size = document.createElement('strong');
    size.textContent = formatBytes(item.bytes);
    row.append(marker,copy,size);
    legend.append(row);
  }
}

function renderFolderChart(files) {
  const totals = new Map();
  for (const file of files) {
    const key = `${file.location || 'Location'}\u0000${file.top_folder || '(root files)'}`;
    const item = totals.get(key) || {location:file.location || 'Location',name:file.top_folder || '(root files)',bytes:0,count:0};
    item.bytes += file.size || 0;
    item.count += 1;
    totals.set(key,item);
  }
  const folders = [...totals.values()].sort((left,right)=>right.bytes-left.bytes).slice(0,8);
  const host = document.querySelector('#folder-chart');
  host.replaceChildren();
  if (!folders.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No folders with files in this scan.';
    host.append(empty);
    return;
  }
  const largest = Math.max(1,folders[0].bytes);
  for (const folder of folders) {
    const row = document.createElement('div');
    row.className = 'folder-chart-row';
    const title = document.createElement('div');
    title.className = 'folder-chart-title';
    const name = document.createElement('strong');
    name.textContent = folder.name === '(root files)' ? `Files directly in ${folder.location}` : folder.name;
    const location = document.createElement('span');
    location.textContent = `${folder.location} · ${folder.count} files`;
    title.append(name,location);
    const amount = document.createElement('strong');
    amount.className = 'folder-chart-size';
    amount.textContent = formatBytes(folder.bytes);
    const line = document.createElement('div');
    line.className = 'folder-chart-track';
    const fill = document.createElement('i');
    fill.style.width = `${Math.max(2,folder.bytes/largest*100)}%`;
    line.append(fill);
    row.append(title,amount,line);
    host.append(row);
  }
}

function renderDuplicateChart(groups) {
  const savings = groups.reduce((sum,item)=>sum+item.estimated_savings,0);
  const counts = new Map();
  for (const group of groups) {
    const copies = [...group.files].sort((left,right)=>left.path.localeCompare(right.path)).slice(1);
    for (const file of copies) {
      const key = file.category || 'other';
      counts.set(key,(counts.get(key)||0)+1);
    }
  }
  const duplicateCopies = [...counts.values()].reduce((sum,count)=>sum+count,0);
  document.querySelector('#duplicate-copy-total').textContent = `${duplicateCopies.toLocaleString()} copies`;
  const host = document.querySelector('#duplicate-chart');
  window.renderFileTypeBars(host,counts,'No exact duplicate copies found.');
  const note = document.querySelector('#duplicate-chart-note');
  note.textContent = groups.length
    ? `${duplicateCopies.toLocaleString()} extra copies across ${groups.length.toLocaleString()} exact groups · estimated reclaimable ${formatBytes(savings)}`
    : 'No exact duplicate copies found.';
}
