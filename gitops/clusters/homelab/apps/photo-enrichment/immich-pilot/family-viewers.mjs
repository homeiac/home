import { readFile, realpath, rename, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export async function shareNewAlbums(api, owner, viewers, handled, save) {
  if (viewers.length !== 2 || new Set([owner, ...viewers]).size !== 3 || ![owner, ...viewers].every(id => /^[0-9a-f-]{36}$/i.test(id))) {
    throw Error('Invalid household account configuration');
  }
  let added = 0;
  for (const album of await api('/albums')) {
    if (handled.has(album.id)) continue;
    const members = album.albumUsers;
    if (!members.some(m => m.role === 'owner' && m.user.id === owner)) continue;
    const missing = viewers.filter(id => !members.some(m => m.user.id === id));
    if (missing.length) {
      const result = await api('/albums/' + album.id + '/users', {
        albumUsers: missing.map(userId => ({ userId, role: 'viewer' }))
      });
      if (!missing.every(id => result.albumUsers.some(m => m.user.id === id && m.role === 'viewer'))) {
        throw Error('Album viewer verification failed');
      }
      added += missing.length;
    }
    handled.add(album.id);
    await save(handled);
  }
  return added;
}

async function main() {
  const setting = async name => (await readFile('/policy/' + name, 'utf8')).trim();
  const key = await setting('api-key');
  const state = '/state/shared.json';
  let handled = new Set();
  try { handled = new Set(JSON.parse(await readFile(state, 'utf8'))); }
  catch (e) { if (e.code !== 'ENOENT') throw e; }
  async function api(path, body) {
    const response = await fetch('http://immich-server:2283/api' + path, {
      method: body ? 'PUT' : 'GET',
      headers: {'x-api-key': key, 'Content-Type': 'application/json'},
      body: body && JSON.stringify(body), signal: AbortSignal.timeout(20000)
    });
    if (!response.ok) throw Error('Immich album API returned ' + response.status);
    return response.json();
  }
  const count = await shareNewAlbums(api, await setting('owner'), (await setting('viewers')).split(','), handled, async ids => {
    await writeFile(state + '.tmp', JSON.stringify([...ids]), { mode: 0o600 });
    await rename(state + '.tmp', state);
  });
  console.log(JSON.stringify({albumsProcessedToDate: handled.size, viewerGrantsAdded: count}));
}
if (process.argv[1] && pathToFileURL(await realpath(process.argv[1])).href === import.meta.url) await main();
