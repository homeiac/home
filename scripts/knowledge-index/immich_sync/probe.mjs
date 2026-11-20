// Read-only API shape check. No credentials, file paths or names in output.
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const api=async(path,body)=>{const r=await fetch('http://immich-server:2283/api'+path,{method:body?'POST':'GET',headers:{'x-api-key':key,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!r.ok)throw Error('HTTP '+r.status);return r.json();};
const me=await api('/users/me'), libraries=await api('/libraries');
const lib=libraries.find(l=>l.name==='Existing Google Photos');
const result=await api('/search/metadata',{libraryId:lib.id,withExif:true,size:1000,page:1});
const a=result.assets.items[0];
console.log(JSON.stringify({libraryOwnerMatches:lib.ownerId===me.id,items:result.assets.items.length,assetKeys:Object.keys(a),external:a.isExternal,libraryMatches:a.libraryId===lib.id,ownerMatches:a.ownerId===me.id,pathPrefix:a.originalPath?.startsWith('/external/gphotos/Google Photos/Photos from '),sizePresent:a.exifInfo?.fileSizeInByte!==undefined,paginationKeys:Object.keys(result.assets).filter(k=>k!=='items'),nextPage:result.assets.nextPage,nextCursorPresent:!!result.assets.nextCursor}));
const detail=await api('/assets/'+a.id);console.log(JSON.stringify({detailKeys:Object.keys(detail),detailExternal:detail.isExternal,detailLibraryMatches:detail.libraryId===lib.id,detailOwnerMatches:detail.ownerId===me.id}));
