'use strict';
const $ = id => document.getElementById(id);
async function read(path) {
  const response = await fetch(path, {signal: AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error('Status unavailable');
  return response.json();
}
function count(value) { return value.toLocaleString(); }
async function refreshDashboard() {
  $('refresh').disabled = true;
  $('status').textContent = 'Checking the latest status…';
  // Independent cards can succeed even when another service is unavailable.
  const results = await Promise.allSettled([
    (async () => {
      const data = await read('/api/status');
      if (!Number.isFinite(data.captured_at) || data.captured_at <= 0) {
        $('index-status').textContent = 'Not published yet';
        $('index-detail').textContent = 'Waiting for the first enrichment update';
        return;
      }
      const age = Math.max(0, Date.now() / 1000 - data.captured_at);
      $('index-status').textContent = age < 900 ? 'Up to date' : 'Update overdue';
      $('index-detail').textContent = 'Updated ' + new Date(data.captured_at * 1000).toLocaleString();
    })(),
    (async () => {
      const groups = await read('/api/groups');
      if (!Array.isArray(groups)) throw new Error('Invalid notes status');
      $('group-count').textContent = count(groups.length);
      $('group-detail').textContent = groups.length ? 'Shared stories saved with your photos' : 'Ready for your first story';
    })(),
    (async () => {
      const config = await read('/api/config');
      $('cricket-app').hidden = !config.cricket;
      if (!config.cricket) {
        $('cricket-count').textContent = 'Not enabled';
        $('cricket-detail').textContent = 'Cricket highlights are not configured';
        return;
      }
      const data = await read('/api/cricket/albums');
      if (!Array.isArray(data.albums)) throw new Error('Invalid cricket status');
      $('cricket-count').textContent = count(data.albums.length);
      $('cricket-detail').textContent = data.albums.length ? 'Ready to explore in Cricket highlights' : 'Waiting for the first cricket album';
    })()
  ]);
  const cards = [['index-status', 'index-detail'], ['group-count', 'group-detail'], ['cricket-count', 'cricket-detail']];
  results.forEach((result, i) => {
    if (result.status === 'rejected') {
      $(cards[i][0]).textContent = 'Unavailable';
      $(cards[i][1]).textContent = 'Could not check right now. Try refreshing.';
    }
  });
  $('status').textContent = results.some(result => result.status === 'rejected')
    ? 'Some status checks are unavailable. Your library and app links are still here.'
    : 'Status checked ' + new Date().toLocaleTimeString();
  $('refresh').disabled = false;
}
$('refresh').onclick = refreshDashboard;
refreshDashboard();
