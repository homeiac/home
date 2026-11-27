// Select the native search gallery when the user opens an opted-in album from Albums.
function albumLink(album) {
  const standard = '/albums/' + album.id;
  if (location.pathname.replace(/\/$/, '') !== '/albums' ||
      !album.description?.split('\n').some(line => line.trim() === 'Layout: photo grid')) {
    return standard;
  }
  return '/search?' + new URLSearchParams({
    query: JSON.stringify({albumIds: [album.id], order: album.order || 'asc'})
  });
}

// Keep the upstream content-addressed modules intact. An import map selects
// the versioned route helper on a fresh page load, including SPA navigation.
function prepare(www, output) {
  const fs = require('node:fs');
  const crypto = require('node:crypto');
  const zlib = require('node:zlib');
  const path = require('node:path');
  const upstream = '/_app/immutable/chunks/DEHf2nXs.js';
  const overlay = '/_app/immutable/chunks/DEHf2nXs.album-grid-v1.js';
  const original = 'viewAlbum:({id:e})=>`/albums/${e}`';
  const shell = fs.readFileSync(path.join(www, 'index.html'), 'utf8');
  let index = shell;
  let module = '';
  const sourcePath = path.join(www, upstream);
  const source = fs.existsSync(sourcePath) ? fs.readFileSync(sourcePath, 'utf8') : '';
  if (crypto.createHash('sha256').update(source).digest('hex') ===
      '9729ef90af52c72b9064eaa45788e0cea15c20284e6b6c0cb28792ea26ba66ea' &&
      source.split(original).length === 2 && shell.includes('<head>') && !shell.includes('type="importmap"')) {
    module = source.replace(original, () => 'viewAlbum:' + albumLink.toString());
    const map = JSON.stringify({imports: {[upstream]: overlay}});
    index = shell.replace('<head>', '<head><script type="importmap">' + map + '</script>');
    console.log('Album grid links enabled');
  } else {
    console.warn('Unrecognized Immich web build. Keeping upstream album navigation.');
  }
  fs.writeFileSync(path.join(output, 'grid.js'), module);
  fs.writeFileSync(path.join(output, 'index.html'), index);
  fs.writeFileSync(path.join(output, 'index.html.br'), zlib.brotliCompressSync(index));
  fs.writeFileSync(path.join(output, 'index.html.gz'), zlib.gzipSync(index));
}

module.exports = {albumLink, prepare};
if (require.main === module) prepare('/build/www', '/output');
