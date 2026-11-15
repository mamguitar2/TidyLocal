const ORGANIZER_DESTINATIONS = [
  ['Taxes', 'Taxes'], ['Finances', 'Finances'], ['Career', 'Career'], ['Personal', 'Personal'],
  ['Personal/Music', 'Personal · Music'],
  ['Personal/Bad Caddy Apparel Co', 'Personal · Bad Caddy Apparel Co'],
  ['Personal/Rent', 'Personal · Rent'],
  ['Personal/Power of Attorney', 'Personal · Power of Attorney'],
  ['Personal/Wedding', 'Personal · Wedding'],
];
let currentOrganization = [];
let currentFolders = [];
let folderChoices = new Map();
let openDestinationMenu = null;
let hiddenDestinationChoices = new Set();
try {
  hiddenDestinationChoices = new Set(JSON.parse(localStorage.getItem('tidylocal-hidden-destinations') || '[]'));
} catch {
  hiddenDestinationChoices = new Set();
}

document.addEventListener('click', event => {
  if (openDestinationMenu && !openDestinationMenu.parentElement.contains(event.target)) {
    openDestinationMenu.hidden = true;
    openDestinationMenu.previousElementSibling.setAttribute('aria-expanded','false');
    openDestinationMenu = null;
  }
});

function destinationKey(item) {
  return item.category ? `${item.category}${item.subcategory ? `/${item.subcategory}` : ''}` : '';
}

function destinationName(key) {
  return ORGANIZER_DESTINATIONS.find(([value]) => value === key)?.[1] || key || 'Choose a folder';
}

async function performPathAction(action, path, button, statusNode) {
  button.disabled = true;
  try {
    const response = await fetch('/api/actions', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,job_id:window.lastCompletedJob,sources:[path]})});
    const data = await response.json();
    const result = data.results?.[0];
    if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Could not open this location.');
    statusNode.textContent = action === 'open' ? 'Opened with the default app.' : 'Opened in Finder.';
    return result;
  } catch (error) {
    statusNode.textContent = error.message;
    return null;
  } finally {
    button.disabled = false;
  }
}

function addFolderChoice(label, choice) {
  if (!folderChoices.has(label)) folderChoices.set(label, choice);
}

function suggestedFolderLabel(item, key) {
  const destination = item.destination_options?.[key];
  const existing = currentFolders.find(folder => folder.path === destination);
  return existing
    ? `${existing.location} / ${existing.relative || existing.name}`
    : `Suggested · ${destinationName(key)}`;
}

function renderDestinationFolderChecks() {
  const host = document.querySelector('#destination-folder-checks');
  host.replaceChildren();
  for (const label of folderChoices.keys()) {
    const row = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = !hiddenDestinationChoices.has(label);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) hiddenDestinationChoices.delete(label);
      else hiddenDestinationChoices.add(label);
      try { localStorage.setItem('tidylocal-hidden-destinations',JSON.stringify([...hiddenDestinationChoices])); } catch {}
      updateDestinationSelectionCount();
      renderOrganization();
    });
    const text = document.createElement('span');
    text.textContent = label;
    row.append(checkbox,text);
    host.append(row);
  }
  updateDestinationSelectionCount();
}

function updateDestinationSelectionCount() {
  const count = [...folderChoices.keys()].filter(label => !hiddenDestinationChoices.has(label)).length;
  document.querySelector('#destination-selection-count').textContent = `${count} of ${folderChoices.size} folders selected`;
}

function setAllDestinationChoices(visible) {
  for (const label of folderChoices.keys()) {
    if (visible) hiddenDestinationChoices.delete(label);
    else hiddenDestinationChoices.add(label);
  }
  try { localStorage.setItem('tidylocal-hidden-destinations',JSON.stringify([...hiddenDestinationChoices])); } catch {}
  renderDestinationFolderChecks();
  renderOrganization();
}

function rebuildFolderChoices() {
  folderChoices = new Map();
  for (const folder of currentFolders) {
    const label = `${folder.location} / ${folder.relative || folder.name}`;
    addFolderChoice(label, {kind:'folder',path:folder.path});
  }
  for (const item of currentOrganization) {
    const key = destinationKey(item);
    const destination = item.destination_options?.[key];
    const existsInList = currentFolders.some(folder => folder.path === destination);
    if (key && !existsInList) addFolderChoice(`Suggested · ${destinationName(key)}`, {kind:'category',key});
  }
  renderDestinationFolderChecks();
  document.querySelector('#folder-choices-note').textContent = currentFolders.length
    ? `${currentFolders.length}${window.folderChoicesTruncated ? '+' : ''} existing folders available from this scan. Or create a named folder below.`
    : 'No existing subfolders in the scanned locations yet. Create a named folder below, or choose a suggestion.';
}

function renderOrganizerBreakdown() {
  const host = document.querySelector('#organizer-category-chart');
  host.replaceChildren();
  const actionItems = currentOrganization.filter(item => !item.needs_review && !item.already_organized && !item.protected);
  document.querySelector('#organizer-total-count').textContent = `${actionItems.length.toLocaleString()} files`;
  const counts = new Map();
  for (const item of actionItems) {
    const key = item.file_category || 'other';
    counts.set(key,(counts.get(key)||0)+1);
  }
  window.renderFileTypeBars(host,counts,'No files have a clear organizing action in this scan.');
}

function setOrganizationData(recommendations, folders, foldersTruncated) {
  currentOrganization = recommendations || [];
  currentFolders = folders || [];
  window.folderChoicesTruncated = Boolean(foldersTruncated);
  renderOrganizerBreakdown();
  rebuildFolderChoices();
  renderOrganization();
}

function addOrganizerListItem(host, detailHost, proposal, card) {
  const row = document.createElement('button');
  row.type = 'button';
  row.className = `organizer-list-item${proposal.already_organized ? ' already-organized' : ' needs-action'}`;
  row.setAttribute('aria-pressed', 'false');
  const name = document.createElement('strong');
  name.textContent = proposal.name;
  const state = document.createElement('span');
  state.textContent = proposal.already_organized ? 'Already sorted' : proposal.protected ? 'Protected' : proposal.needs_review ? 'Needs review' : 'Needs action';
  const metadata = document.createElement('small');
  metadata.textContent = `${proposal.location || 'Selected folder'} · ${formatBytes(proposal.size || 0)}`;
  row.append(name,state,metadata);
  card.organizerListRow = row;
  row.addEventListener('click', () => {
    host.querySelectorAll('.organizer-list-item').forEach(item => {
      item.classList.toggle('selected', item === row);
      item.setAttribute('aria-pressed', String(item === row));
    });
    detailHost.replaceChildren(card);
  });
  host.append(row);
}

function renderOrganization() {
  const host = document.querySelector('#organization-list');
  const detailHost = document.querySelector('#organizer-details');
  host.replaceChildren();
  detailHost.replaceChildren();
  const proposals = currentOrganization
    .filter(item => !item.already_organized && !item.needs_review && !item.protected)
    .sort((left,right)=>left.name.localeCompare(right.name));
  document.querySelector('#organizer-summary').textContent = `${proposals.length.toLocaleString()} files have a clear organizing action.`;
  if (!proposals.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No files have a clear organizing action in this scan.';
    host.append(empty);
    const noSelection = document.createElement('p');
    noSelection.className = 'organizer-detail-empty';
    noSelection.textContent = 'No file selected.';
    detailHost.append(noSelection);
    return;
  }

  for (const proposal of proposals) {
    const card = document.createElement('article');
    card.className = `organization-card${proposal.needs_review?' needs-review':''}${proposal.already_organized?' already-organized':' needs-action'}`;
    const heading = document.createElement('div');
    heading.className = 'organizer-file-heading';
    const name = document.createElement('strong');
    name.className = 'organizer-file-name';
    name.textContent = proposal.name;
    const badge = document.createElement('span');
    badge.className = `confidence${proposal.already_organized?' already':''}${proposal.needs_review?' review':''}`;
    badge.textContent = proposal.recommended_action === 'trash' ? 'Recommended for Trash' : proposal.protected ? 'System file' : proposal.already_organized ? 'Already sorted' : proposal.file_type || 'File';
    heading.append(name,badge);

    let currentFilePath = proposal.source;
    let destinationPath = '';
    const sourceFolder = proposal.source.slice(0,proposal.source.lastIndexOf('/'));
    const location = document.createElement('p');
    location.className = 'organizer-details';
    location.textContent = `Current folder · ${sourceFolder} · ${formatBytes(proposal.size || 0)}`;
    const openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'reveal-file';
    openButton.textContent = 'Open file';
    const statusMessage = document.createElement('span');
    statusMessage.className = 'organize-status';
    openButton.addEventListener('click', () => performPathAction('open',currentFilePath,openButton,statusMessage));
    const openCurrentFolder = document.createElement('button');
    openCurrentFolder.type = 'button';
    openCurrentFolder.className = 'reveal-file';
    openCurrentFolder.textContent = 'Open current folder';
    openCurrentFolder.addEventListener('click', () => performPathAction('reveal',sourceFolder,openCurrentFolder,statusMessage));
    const openDestinationFolder = document.createElement('button');
    openDestinationFolder.type = 'button';
    openDestinationFolder.className = 'reveal-file';
    openDestinationFolder.textContent = 'Open destination folder';
    openDestinationFolder.disabled = true;
    openDestinationFolder.addEventListener('click', () => {
      if (destinationPath) performPathAction('reveal',destinationPath,openDestinationFolder,statusMessage);
    });
    const openFolderActions = document.createElement('div');
    openFolderActions.className = 'organizer-folder-actions';
    openFolderActions.append(openCurrentFolder,openDestinationFolder);

    if (proposal.recommended_action === 'trash') {
      const recommendation = document.createElement('p');
      recommendation.className = 'installer-recommendation';
      recommendation.textContent = proposal.reason;
      const trashButton = document.createElement('button');
      trashButton.type = 'button';
      trashButton.className = 'installer-trash';
      trashButton.textContent = 'Move installer to Trash';
      const status = document.createElement('span');
      status.className = 'organize-status';
      trashButton.addEventListener('click', async () => {
        if (!window.confirm(`Move the installer file “${proposal.name}” to the Mac Trash? This will not uninstall any installed app.`)) return;
        trashButton.disabled = true;
        status.textContent = 'Moving installer to Trash…';
        try {
          const response = await fetch('/api/actions', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'trash',job_id:window.lastCompletedJob,sources:[proposal.source]})});
          const data = await response.json();
          const result = data.results?.[0];
          if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Could not move installer to Trash.');
          status.textContent = 'Installer moved to Trash. Restore it there if needed.';
          trashButton.textContent = 'Moved to Trash';
          card.classList.add('moved');
        } catch (error) {
          status.textContent = error.message;
          trashButton.disabled = false;
        }
      });
      card.append(heading,location,openButton,openCurrentFolder,recommendation,trashButton,status);
      addOrganizerListItem(host,detailHost,proposal,card);
      continue;
    }

    const key = destinationKey(proposal);
    const suggestion = key ? suggestedFolderLabel(proposal,key) : '';
    const choice = document.createElement('button');
    choice.type = 'button';
    choice.className = 'organizer-destination';
    choice.setAttribute('aria-label',`Destination folder for ${proposal.name}`);
    choice.setAttribute('aria-expanded','false');
    choice.value = folderChoices.has(suggestion) && !hiddenDestinationChoices.has(suggestion) ? suggestion : '';
    choice.textContent = choice.value || 'Choose a folder';
    const destinationPicker = document.createElement('div');
    destinationPicker.className = 'destination-picker';
    const optionsMenu = document.createElement('div');
    optionsMenu.className = 'destination-options';
    optionsMenu.setAttribute('role','listbox');
    optionsMenu.hidden = true;
    destinationPicker.append(choice,optionsMenu);
    choice.addEventListener('click', () => {
      if (!optionsMenu.hidden) {
        optionsMenu.hidden = true;
        choice.setAttribute('aria-expanded','false');
        openDestinationMenu = null;
        return;
      }
      if (openDestinationMenu && openDestinationMenu !== optionsMenu) {
        openDestinationMenu.hidden = true;
        openDestinationMenu.previousElementSibling.setAttribute('aria-expanded','false');
      }
      optionsMenu.replaceChildren();
      const entries = [['','Choose a folder'], ...[...folderChoices.keys()].filter(label => !hiddenDestinationChoices.has(label)).map(label => [label,label])];
      for (const [value,label] of entries) {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'destination-option';
        option.setAttribute('role','option');
        option.setAttribute('aria-selected',String(value === choice.value));
        option.textContent = label;
        option.addEventListener('click', () => {
          choice.value = value;
          choice.textContent = value || 'Choose a folder';
          optionsMenu.hidden = true;
          choice.setAttribute('aria-expanded','false');
          openDestinationMenu = null;
          choice.dispatchEvent(new Event('change'));
        });
        optionsMenu.append(option);
      }
      optionsMenu.hidden = false;
      choice.setAttribute('aria-expanded','true');
      openDestinationMenu = optionsMenu;
    });
    const preview = document.createElement('p');
    preview.className = 'destination-preview';
    const updatePreview = () => {
      preview.replaceChildren();
      const selected = folderChoices.get(choice.value.trim());
      if (!selected) {
        destinationPath = '';
        openDestinationFolder.disabled = true;
        preview.textContent = choice.value ? 'Choose a folder from the list or create one below.' : 'Choose where this file belongs.';
        return;
      }
      const label = document.createElement('strong');
      const detail = document.createElement('span');
      let exists = selected.kind === 'folder';
      if (selected.kind === 'category') {
        destinationPath = proposal.destination_options?.[selected.key] || `${proposal.location_root}/${selected.key}`;
        exists = Boolean(proposal.existing_destinations?.[selected.key]);
        label.textContent = 'Suggested folder';
        detail.textContent = `${destinationPath.split(/[\\/]/).filter(Boolean).slice(-2).join(' / ')} · ${exists?'existing folder':'created only if you move'}`;
      } else {
        destinationPath = selected.path;
        const isSuggested = key && choice.value === suggestedFolderLabel(proposal,key);
        label.textContent = isSuggested ? 'Suggested folder' : 'Selected folder';
        detail.textContent = `${selected.path} · Existing folder`;
      }
      openDestinationFolder.disabled = !exists;
      preview.append(label,detail);
    };
    updatePreview();

    const change = document.createElement('div');
    change.className = 'change-destination';
    const changeLabel = document.createElement('span');
    changeLabel.className = 'destination-label';
    changeLabel.textContent = 'Change destination';
    change.append(changeLabel,destinationPicker);
    const move = document.createElement('button');
    move.type = 'button';
    move.className = 'organize-move';
    const updateMoveButton = () => {
      const selected = folderChoices.get(choice.value.trim());
      if (!selected) {
        move.textContent = 'Choose a folder first';
        move.disabled = true;
        return;
      }
      const sourceParent = proposal.source.slice(0,proposal.source.lastIndexOf('/'));
      const alreadyHere = selected.kind === 'folder' && selected.path === sourceParent;
      move.textContent = alreadyHere ? 'Already in this folder' : 'Move file';
      const original = selected.kind === 'category' && selected.key === key && proposal.already_organized;
      move.disabled = Boolean(proposal.protected || original || alreadyHere);
    };
    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'delete-file';
    deleteButton.textContent = 'Move file to Trash';
    const status = document.createElement('span');
    status.className = 'organize-status';
    choice.addEventListener('change',()=>{updatePreview();updateMoveButton();});
    updateMoveButton();
    deleteButton.addEventListener('click',async()=>{
      if (!window.confirm(`Move “${proposal.name}” to the Mac Trash? You can restore it from Trash if needed.`)) return;
      deleteButton.disabled = true;
      status.textContent = 'Moving file to Trash…';
      try {
        const response = await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'trash',job_id:window.lastCompletedJob,sources:[proposal.source]})});
        const data = await response.json();
        const result = data.results?.[0];
        if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Could not move file to Trash.');
        status.textContent = 'Moved to Trash. Restore it from Trash if needed.';
        deleteButton.textContent = 'Moved to Trash';
        move.textContent = 'Moved to Trash';
        move.disabled = true;
        openButton.disabled = true;
        card.classList.remove('needs-action','needs-review');
        card.classList.add('moved','already-organized');
        badge.classList.add('already');
        badge.textContent = 'Moved to Trash';
        const listRow = card.organizerListRow;
        listRow?.classList.remove('needs-action');
        listRow?.classList.add('already-organized');
        const listState = listRow?.querySelector('span');
        if (listState) listState.textContent = 'Moved to Trash';
      } catch(error) {
        status.textContent = error.message;
        deleteButton.disabled = false;
      }
    });
    move.addEventListener('click',async()=>{
      const selected=folderChoices.get(choice.value.trim());
      if (!selected) return;
      const target=selected.kind==='folder'?selected.path:(proposal.destination_options?.[selected.key]||`${proposal.location_root}/${selected.key}`);
      if (!window.confirm(`Move “${proposal.name}” to ${target}? Existing files will never be overwritten.`)) return;
      move.disabled=true;
      status.textContent='Moving…';
      try {
        const body=selected.kind==='category'
          ? {action:'organize',job_id:window.lastCompletedJob,source:proposal.source,category:selected.key.split('/')[0],subcategory:selected.key.split('/').slice(1).join('/')}
          : {action:'move',job_id:window.lastCompletedJob,source:proposal.source,destination:selected.path};
        const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const data=await response.json();
        const result=data.results?.[0];
        if (!response.ok || !result?.success) throw new Error(result?.message||data.detail||'Move failed.');
        status.textContent=`Moved to ${result.destination}. You can undo this above.`;
        currentFilePath = result.destination;
        destinationPath = result.destination.slice(0,result.destination.lastIndexOf('/'));
        location.textContent = `Current folder · ${destinationPath} · ${formatBytes(proposal.size || 0)}`;
        openButton.textContent = 'Open moved file';
        openCurrentFolder.textContent = 'Open original folder';
        openDestinationFolder.disabled = false;
        card.classList.remove('needs-action','needs-review');
        card.classList.add('moved','already-organized');
        badge.classList.add('already');
        badge.classList.remove('review');
        badge.textContent = 'Moved · sorted';
        move.textContent = 'Moved · now sorted';
        deleteButton.disabled = true;
        deleteButton.textContent = 'File moved';
        const listRow = card.organizerListRow;
        listRow?.classList.remove('needs-action');
        listRow?.classList.add('already-organized');
        const listState = listRow?.querySelector('span');
        if (listState) listState.textContent = 'Moved · sorted';
      } catch(error) {
        status.textContent=error.message;
        move.disabled=false;
      }
    });
    const why=document.createElement('details');
    why.className='suggestion-reason';
    const whySummary=document.createElement('summary');
    whySummary.textContent='Why this suggestion?';
    const reason=document.createElement('p');
    reason.textContent=proposal.reason;
    why.append(whySummary,reason);
    if (proposal.already_organized || proposal.protected) {
      const disposition = document.createElement('p');
      disposition.className = 'organizer-details';
      disposition.textContent = proposal.already_organized ? 'Already in the recommended folder · leaving it in place.' : 'Protected system file · no move action available.';
      card.append(heading,location,openButton,openCurrentFolder,disposition,why);
    } else {
      card.append(heading,location,openButton,openFolderActions,preview,change,move,deleteButton,status,why);
    }
    addOrganizerListItem(host,detailHost,proposal,card);
  }
  const firstItem = host.querySelector('.organizer-list-item');
  if (firstItem) firstItem.click();
}

async function undoOrganizationMove() {
  if (!window.confirm('Undo the most recent move or remove the most recently created empty folder? It will proceed only if the original location is safe.')) return;
  const status = document.querySelector('#organizer-status');
  status.textContent = 'Undoing last action…';
  try {
    const response = await fetch('/api/actions', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'undo'})});
    const data = await response.json();
    const result = data.results?.[0];
    if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Undo failed.');
    status.textContent = result.message;
  } catch (error) {
    status.textContent = error.message;
  }
}

async function loadFolderRoots() {
  const select = document.querySelector('#create-folder-parent');
  try {
    const response = await fetch('/api/roots');
    const data = await response.json();
    select.replaceChildren(...['Desktop','Downloads','Documents'].filter(name=>data.locations?.includes(name)).map(name=>new Option(name,name)));
  } catch {
    document.querySelector('#create-folder-status').textContent = 'Could not load approved folder locations.';
  }
}

async function createNamedFolder() {
  const parent=document.querySelector('#create-folder-parent').value;
  const input=document.querySelector('#create-folder-name');
  const name=input.value.trim();
  const status=document.querySelector('#create-folder-status');
  if (!parent || !name) {status.textContent='Choose a parent folder and enter a name.';return;}
  if (!window.confirm(`Create “${name}” in ${parent}?`)) return;
  const button=document.querySelector('#create-folder-button');
  button.disabled=true;
  status.textContent='Creating folder…';
  try {
    const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'create-folder',destination:parent,name})});
    const data=await response.json();
    const result=data.results?.[0];
    if (!response.ok || !result?.success) throw new Error(result?.message||data.detail||'Could not create folder.');
    const relative=`${parent} / ${name}`;
    const choice={kind:'folder',path:result.destination};
    addFolderChoice(relative,choice);
    hiddenDestinationChoices.delete(relative);
    try { localStorage.setItem('tidylocal-hidden-destinations',JSON.stringify([...hiddenDestinationChoices])); } catch {}
    renderDestinationFolderChecks();
    renderOrganization();
    status.textContent=`Created “${name}” in ${parent}. It is available in destination menus.`;
    input.value='';
  } catch(error) {
    status.textContent=error.message;
  } finally {
    button.disabled=false;
  }
}

document.querySelector('#continue-organize').addEventListener('click',()=>{
  const available = [...folderChoices.keys()].some(label => !hiddenDestinationChoices.has(label));
  if (!available) {
    document.querySelector('#destination-selection-count').textContent = 'Select at least one folder before continuing.';
    return;
  }
  document.querySelector('#organizer-step-one').hidden = true;
  document.querySelector('#organizer-step-two').hidden = false;
  document.querySelector('#organizer-step-two').scrollIntoView({behavior:'smooth',block:'start'});
});
document.querySelector('#back-to-step-one').addEventListener('click',()=>{
  document.querySelector('#organizer-step-two').hidden = true;
  document.querySelector('#organizer-step-one').hidden = false;
  document.querySelector('#organizer-step-one').scrollIntoView({behavior:'smooth',block:'start'});
});
document.querySelector('#destination-add-folder').addEventListener('click',()=>{
  const panel=document.querySelector('.folder-create-panel');
  panel.open=true;
  panel.scrollIntoView({behavior:'smooth',block:'center'});
  document.querySelector('#create-folder-name').focus({preventScroll:true});
});
document.querySelector('#destination-select-all').addEventListener('click',()=>setAllDestinationChoices(true));
document.querySelector('#destination-select-none').addEventListener('click',()=>setAllDestinationChoices(false));
document.querySelector('#undo-organize').addEventListener('click',undoOrganizationMove);
document.querySelector('#create-folder-button').addEventListener('click',createNamedFolder);
loadFolderRoots();
