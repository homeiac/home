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

// Each invited recipient must first accept from their own Immich account.
export async function sharePeopleOnce(api, group, owner, viewers, granted, save) {
  const pending = viewers.filter(id => !granted.has(id));
  if (!pending.length) return 0;
  const members = new Set((await api('/cluster-groups/' + group + '/users')).map(u => u.id));
  if (!members.has(owner)) throw Error('Unexpected People group');
  for (const id of pending.filter(id => members.has(id))) {
    await api('/people/users', {type: 'everyone', sharedWithIds: [id], role: 'read'});
    granted.add(id);
    await save(granted);
  }
  return viewers.filter(id => !granted.has(id)).length;
}

async function checkpoint(path) {
  let ids = [];
  try { ids = JSON.parse(await readFile(path, 'utf8')); }
  catch (e) { if (e.code !== 'ENOENT') throw e; }
  return {
    ids: new Set(ids),
    async save(current) {
      await writeFile(path + '.tmp', JSON.stringify([...current]), {mode: 0o600});
      await rename(path + '.tmp', path);
    }
  };
}

async function main() {
  const setting = async name => (await readFile('/policy/' + name, 'utf8')).trim();
  const key = await setting('api-key');
  const owner = await setting('owner');
  const viewers = (await setting('viewers')).split(',');
  async function api(path, body) {
    const response = await fetch('http://immich-server:2283/api' + path, {
      method: body ? 'PUT' : 'GET',
      headers: {'x-api-key': key, 'Content-Type': 'application/json'},
      body: body && JSON.stringify(body), signal: AbortSignal.timeout(20000)
    });
    if (!response.ok) throw Error('Immich ' + path.split('/')[1] + ' API returned ' + response.status);
    const text = await response.text();
    return text ? JSON.parse(text) : undefined;
  }
  const albums = await checkpoint('/state/shared.json');
  const count = await shareNewAlbums(api, owner, viewers, albums.ids, albums.save);
  const people = await checkpoint('/state/people-read.json');
  const pending = await sharePeopleOnce(api, await setting('people-group'), owner, viewers, people.ids, people.save);
  console.log(JSON.stringify({albumsProcessedToDate: albums.ids.size, viewerGrantsAdded: count,
    peopleRecipientsGranted: people.ids.size, peopleRecipientsPending: pending}));
}
if (process.argv[1] && pathToFileURL(await realpath(process.argv[1])).href === import.meta.url) await main();
