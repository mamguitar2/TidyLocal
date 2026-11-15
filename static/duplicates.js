async function openScannedFile(path, button) {
  button.disabled = true;
  try {
    const response = await fetch('/api/actions', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'open',job_id:window.lastCompletedJob,sources:[path]})});
    const data = await response.json();
    const result = data.results?.[0];
    if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Could not open file.');
  } catch (error) {
    window.alert(error.message);
  } finally {
    button.disabled = false;
  }
}

const scanButton = document.querySelector('#scan');
const cancelButton = document.querySelector('#cancel-scan');
const status = document.querySelector('#scan-status');
const results = document.querySelector('#results');
const storageTab = document.querySelector('#storage-tab');
const organizationTab = document.querySelector('#organization-tab');
const signalsTab = document.querySelector('#signals-tab');
const storagePanel = document.querySelector('#storage-panel');
const organizationPanel = document.querySelector('#organization-panel');
const signalsPanel = document.querySelector('#signals-panel');
let activeJob = null;
let scanning = false;

function addDetailChoice(list, detailHost, row, detailCard) {
  row.classList.add('detail-list-item');
  row.type = 'button';
  row.setAttribute('aria-pressed','false');
  row.addEventListener('click', () => {
    list.querySelectorAll('.detail-list-item').forEach(item => {
      item.classList.toggle('selected', item === row);
      item.setAttribute('aria-pressed', String(item === row));
    });
    detailHost.replaceChildren(detailCard);
  });
  list.append(row);
}

function selectTab(tab) {
  const tabs = [[storageTab, storagePanel], [organizationTab, organizationPanel], [signalsTab, signalsPanel]];
  for (const [button, panel] of tabs) {
    const selected = button === tab;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    button.classList.toggle('active', selected);
    panel.hidden = !selected;
  }
}

function showResults(result) {
  selectTab(storageTab);
  setOrganizationData(result.recommendations || [], result.folders || [], result.folder_choices_truncated);
  const groups = result.duplicates || [];
  const files = result.files || [];
  const totalBytes = files.reduce((total, file) => total + file.size, 0);
  const duplicateSavings = groups.reduce((total, group) => total + group.estimated_savings, 0);
  document.querySelector('#metric-files').textContent = files.length.toLocaleString();
  document.querySelector('#metric-duplicates').textContent = groups.length.toLocaleString();
  document.querySelector('#metric-savings').textContent = formatBytes(duplicateSavings);
  renderStorageChart(files);
  renderFolderChart(files);
  renderDuplicateChart(groups);
  const isOld = file => file.last_opened && Date.now() - Date.parse(file.last_opened) >= 50 * 24 * 60 * 60 * 1000;
  const largest = [...files].sort((left, right) => right.size - left.size).slice(0, 10);
  const largestHost = document.querySelector('#largest-list');
  largestHost.replaceChildren();
  document.querySelector('#scanned-size').textContent = formatBytes(totalBytes);
  document.querySelector('#largest-count').textContent = `${largest.length} largest of ${files.length} files`;
  for (const file of largest) {
    const row = document.createElement('article');
    row.className = 'largest-row';
    const info = document.createElement('div');
    info.className = 'largest-file-info';
    const path = document.createElement('div');
    path.className = 'file-path';
    path.textContent = file.path;
    const type = document.createElement('small');
    type.textContent = file.file_type || 'File';
    info.append(path,type);
    const size = document.createElement('strong');
    size.className = 'largest-size';
    size.textContent = formatBytes(file.size);
    const openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'reveal-file';
    openButton.textContent = 'Open file';
    openButton.addEventListener('click', () => openScannedFile(file.path, openButton));
    row.append(info, size, openButton);
    largestHost.append(row);
  }
  if (!largest.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No readable files found in the selected folders.';
    largestHost.append(empty);
  }

  const oldFiles = files.filter(isOld).sort((left, right) => Date.parse(left.last_opened) - Date.parse(right.last_opened));
  const oldHost = document.querySelector('#old-list');
  const ageDetails = document.querySelector('#age-details');
  oldHost.replaceChildren();
  ageDetails.replaceChildren();
  document.querySelector('#old-count').textContent = `${oldFiles.length} among the 10 largest files checked`;
  for (const file of oldFiles) {
    const detailCard = document.createElement('article');
    detailCard.className = 'age-file-detail';
    const path = document.createElement('div');
    path.className = 'file-path is-old';
    path.textContent = file.path;
    const detail = document.createElement('p');
    detail.className = 'stale-detail';
    detail.textContent = `Last opened ${new Date(file.last_opened).toLocaleDateString()} · ${formatBytes(file.size)}`;
    const openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'reveal-file';
    openButton.textContent = 'Open file';
    openButton.addEventListener('click', () => openScannedFile(file.path, openButton));
    detailCard.append(path, detail, openButton);
    const row = document.createElement('button');
    row.className = 'age-list-choice';
    const name = document.createElement('strong');
    name.textContent = file.name;
    const when = document.createElement('small');
    when.textContent = new Date(file.last_opened).toLocaleDateString();
    row.append(name,when);
    addDetailChoice(oldHost,ageDetails,row,detailCard);
  }
  if (!oldFiles.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No 50+ day last-opened dates found among the 10 largest files checked. macOS may not provide this data for every file.';
    oldHost.append(empty);
    ageDetails.innerHTML = '<p class="organizer-detail-empty">No older files to show.</p>';
  } else {
    oldHost.querySelector('.detail-list-item')?.click();
  }

  const host = document.querySelector('#duplicate-list');
  const duplicateDetails = document.querySelector('#duplicate-details');
  host.replaceChildren();
  duplicateDetails.replaceChildren();
  document.querySelector('#duplicate-count').textContent = groups.length;
  document.querySelector('#scan-summary').textContent = Object.entries(result.locations || {})
    .map(([name, info]) => `${name}: ${info.count} files · ${formatBytes(info.size)}${info.available ? '' : ' (unavailable)'}`)
    .join(' · ');

  for (const group of groups.sort((left, right) => right.estimated_savings - left.estimated_savings)) {
    const card = document.createElement('article');
    card.className = 'duplicate-card';
    const meta = document.createElement('div');
    meta.className = 'duplicate-meta';
    const count = document.createElement('strong');
    count.textContent = `${group.files.length} identical files · ${formatBytes(group.size)} each`;
    const saving = document.createElement('span');
    saving.className = 'saving';
    saving.textContent = `${formatBytes(group.estimated_savings)} possible savings`;
    meta.append(count, saving);
    card.append(meta);
    for (const file of group.files) {
      const fileRow = document.createElement('div');
      fileRow.className = 'duplicate-file-row';
      const path = document.createElement('div');
      path.className = `file-path is-duplicate${isOld(file) ? ' is-old' : ''}`;
      path.textContent = file.path;
      const tags = document.createElement('span');
      tags.className = 'file-signal-tags';
      const duplicateTag = document.createElement('span');
      duplicateTag.className = 'signal-tag duplicate-tag';
      duplicateTag.textContent = 'Duplicate';
      tags.append(duplicateTag);
      if (isOld(file)) {
        const oldTag = document.createElement('span');
        oldTag.className = 'signal-tag old-tag';
        oldTag.textContent = '50+ days';
        tags.append(oldTag);
      }
      const revealButton = document.createElement('button');
      revealButton.type = 'button';
      revealButton.className = 'reveal-file';
      revealButton.textContent = 'Open file';
      revealButton.addEventListener('click', async () => {
        revealButton.disabled = true;
        actionStatus.textContent = 'Opening file…';
        try {
          const response = await fetch('/api/actions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'open', job_id: window.lastCompletedJob, sources: [file.path]}),
          });
          const data = await response.json();
          const result = data.results?.[0];
          if (!response.ok || !result?.success) throw new Error(result?.message || data.detail || 'Could not show file in Finder.');
          actionStatus.textContent = `Opened ${file.path} with its default application.`;
        } catch (error) {
          actionStatus.textContent = error.message;
        } finally {
          revealButton.disabled = false;
        }
      });
      fileRow.append(path,tags,revealButton);
      card.append(fileRow);
    }
    const keepRow = document.createElement('div');
    keepRow.className = 'keep-row';
    const keepLabel = document.createElement('label');
    keepLabel.textContent = 'Keep this copy:';
    const keepChoice = document.createElement('select');
    keepChoice.id = `keep-copy-${Math.random().toString(36).slice(2)}`;
    keepLabel.htmlFor = keepChoice.id;
    keepChoice.className = 'keep-choice';
    keepChoice.setAttribute('aria-label', 'Choose which duplicate copy to keep');
    for (const file of group.files) keepChoice.add(new Option(file.path, file.path));
    keepLabel.append(keepChoice);

    const keepHere = document.createElement('button');
    keepHere.type = 'button';
    keepHere.className = 'keep-current';
    keepHere.textContent = 'Do nothing · keep all';
    keepHere.addEventListener('click', () => {
      card.classList.add('kept-here');
      actionStatus.textContent = 'Leaving every copy where it is. Nothing was changed.';
    });

    const keepOne = document.createElement('button');
    keepOne.type = 'button';
    keepOne.className = 'trash-duplicates';
    keepOne.textContent = 'Keep one · Trash the rest';
    const trashAll = document.createElement('button');
    trashAll.type = 'button';
    trashAll.className = 'trash-all';
    trashAll.textContent = 'Delete all · move to Trash';
    const actionStatus = document.createElement('span');
    actionStatus.className = 'group-action-status';

    async function moveToTrash(sources, confirmation, successMessage) {
      if (!window.confirm(confirmation)) return;
      keepOne.disabled = true;
      trashAll.disabled = true;
      actionStatus.textContent = 'Moving copies to Trash…';
      try {
        const response = await fetch('/api/actions', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'trash', job_id: window.lastCompletedJob, sources}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not move copies to Trash.');
        const failed = (data.results || []).filter(item => !item.success);
        const moved = (data.results || []).length - failed.length;
        actionStatus.textContent = failed.length
          ? `${moved} moved to Trash; ${failed.length} failed. ${failed.map(item => item.message).join(' ')}`
          : successMessage;
        if (!failed.length) card.classList.add('resolved');
      } catch (error) {
        actionStatus.textContent = error.message;
      } finally {
        if (!card.classList.contains('resolved')) {
          keepOne.disabled = false;
          trashAll.disabled = false;
        }
      }
    }

    keepOne.addEventListener('click', () => {
      const retained = keepChoice.value;
      const sources = group.files.map(file => file.path).filter(path => path !== retained);
      const list = sources.map(path => `• ${path}`).join('\n');
      moveToTrash(sources,
        `Keep this copy in place:\n${retained}\n\nMove the other copies to Trash?\n${list}\n\nYou can restore them from Trash.`,
        `${sources.length} other copy/copies moved to Trash. The selected copy stayed in its folder.`);
    });
    trashAll.addEventListener('click', () => {
      const sources = group.files.map(file => file.path);
      const list = sources.map(path => `• ${path}`).join('\n');
      moveToTrash(sources,
        `Move all ${sources.length} identical copies to the Mac Trash?\n${list}\n\nYou can restore them from Trash.`,
        `${sources.length} copies moved to Trash.`);
    });
    keepRow.append(keepLabel, keepHere, keepOne, trashAll);
    card.append(keepRow, actionStatus);
    const groupChoice = document.createElement('button');
    groupChoice.className = 'duplicate-list-choice';
    const groupName = document.createElement('strong');
    groupName.textContent = group.files[0]?.name || 'Identical files';
    const groupInfo = document.createElement('small');
    groupInfo.textContent = `${group.files.length} copies · ${formatBytes(group.estimated_savings)} possible savings`;
    groupChoice.append(groupName,groupInfo);
    addDetailChoice(host,duplicateDetails,groupChoice,card);
  }
  if (!groups.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No exact duplicates found in the selected folders.';
    host.append(empty);
    duplicateDetails.innerHTML = '<p class="organizer-detail-empty">No duplicate groups to show.</p>';
  } else {
    host.querySelector('.detail-list-item')?.click();
  }
  results.hidden = false;
}

async function loadDiskSpace() {
  try {
    const response = await fetch('/api/disk');
    if (!response.ok) throw new Error('Could not read disk space.');
    const disk = await response.json();
    document.querySelector('#disk-space-free').textContent = `${formatBytes(disk.available)} free`;
    document.querySelector('#disk-space-status').textContent = `${formatBytes(disk.used)} used of ${formatBytes(disk.total)}`;
    document.querySelector('#disk-space-fill').style.width = `${disk.total ? Math.min(100, disk.used / disk.total * 100) : 0}%`;
  } catch {
    document.querySelector('#disk-space-free').textContent = 'Unavailable';
    document.querySelector('#disk-space-status').textContent = 'Disk capacity could not be read.';
  }
}

async function scan() {
  const locations = [...document.querySelectorAll('input[name="location"]:checked')].map(input => input.value);
  if (!locations.length || scanning) {
    if (!locations.length) status.textContent = 'Select at least one folder first.';
    return;
  }

  scanning = true;
  const progressBar = document.querySelector('#scan-progress');
  progressBar.hidden = false;
  progressBar.classList.add('is-active');
  progressBar.setAttribute('aria-valuetext', 'Loading');
  scanButton.disabled = true;
  cancelButton.disabled = false;
  results.hidden = true;
  status.textContent = 'Loading…';
  try {
    const response = await fetch('/api/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({locations}),
    });
    const started = await response.json();
    if (!response.ok) throw new Error(started.detail || 'Could not start scan.');
    activeJob = started.job_id;

    let state;
    const deadline = Date.now() + 10 * 60 * 1000;
    do {
      if (Date.now() >= deadline) throw new Error('Scan timed out while waiting for results. You can retry safely.');
      await new Promise(resolve => setTimeout(resolve, 500));
      const poll = await fetch(`/api/scan/${encodeURIComponent(activeJob)}`);
      state = await poll.json();
      if (!poll.ok) throw new Error(state.detail || 'Could not read scan status.');
      status.textContent = state.status === 'running' ? 'Loading…' : state.status;
    } while (state.status === 'running');

    if (state.result) {
      window.lastCompletedJob = activeJob;
      showResults(state.result);
      status.textContent = state.result.problems?.length
        ? 'Scan finished. Some files could not be read; see folder availability above.'
        : 'Scan complete. No files were changed.';
    } else if (state.status === 'cancelled') {
      status.textContent = 'Scan cancelled. No files were changed.';
    } else {
      throw new Error(state.error || 'Scan did not complete.');
    }
  } catch (error) {
    status.textContent = error.message;
  } finally {
    scanning = false;
    activeJob = null;
    scanButton.disabled = false;
    cancelButton.disabled = true;
    progressBar.classList.remove('is-active');
    progressBar.hidden = true;
    progressBar.setAttribute('aria-valuetext', 'Not loading');
  }
}

storageTab.addEventListener('click', () => selectTab(storageTab));
organizationTab.addEventListener('click', () => selectTab(organizationTab));
signalsTab.addEventListener('click', () => selectTab(signalsTab));
const tabs = [storageTab, organizationTab, signalsTab];
for (const [index, tab] of tabs.entries()) {
  tab.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      const offset = event.key === 'ArrowRight' ? 1 : -1;
      const next = tabs[(index + offset + tabs.length) % tabs.length];
      selectTab(next);
      next.focus();
    }
  });
}

scanButton.addEventListener('click', scan);
loadDiskSpace();
cancelButton.addEventListener('click', async () => {
  if (!activeJob) return;
  cancelButton.disabled = true;
  try {
    const response = await fetch(`/api/scan/${encodeURIComponent(activeJob)}/cancel`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: '{}',
    });
    if (!response.ok) throw new Error('The server did not accept the cancellation request.');
    status.textContent = 'Cancelling scan…';
  } catch (error) {
    cancelButton.disabled = false;
    status.textContent = `${error.message} The scan may still be running.`;
  }
});
