// Pure reconciliation rules. No biometric inference: existing confirmations are provenance.
import crypto from 'node:crypto';
import path from 'node:path';
export const META_KEY = 'home.knowledge-index.v1';
export const ROOT = '/external/gphotos/';
export const stable = value => JSON.stringify(value, (_,v) => v && typeof v==='object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))) : v);
export const digest = value => crypto.createHash('sha256').update(stable(value)).digest('hex');
export function sourcePacket(source) {
  const faces=(source.faces??[]).map(f=>({id:f.id,person:f.person,box:f.box,model:f.model,revision:f.revision,label_source:f.label_source}));
  return {schemaVersion:1,sourcePath:source.path,sizeBytes:Number(source.size_bytes),sourceMtime:source.mtime,
    summary:source.context_summary || source.summary || null,
    summaryModel:source.context_summary ? source.context_model : source.summary_model,
    summaryCreatedAt:source.summary_created_at,
    tags:[...new Set([...(source.summary_tags??[]),...(source.context_tags??[])])].sort(),
    locationContext:source.location_context??null,
    capture:{timestamp:source.capture_ts??source.taken_ts,source:source.capture_source??'takeout.photoTakenTime'},
    gps:{latitude:source.latitude,longitude:source.longitude,source:source.gps_source},
    faces,groups:source.groups??[]};
}
// When only faces/groups come from the catalog, retain the independent saved caption.
export function retainRecoveryCaption(packet, asset, saved) {
  if (!saved || !asset || saved.asset_id !== asset.id || packet.summary ||
      Number(saved.payload.sizeBytes) !== packet.sizeBytes ||
      Math.abs(Date.parse(saved.payload.sourceMtime) - Date.parse(packet.sourceMtime)) > 1500 ||
      !Number.isFinite(Date.parse(saved.payload.sourceMtime)) || !Number.isFinite(Date.parse(packet.sourceMtime))) return packet;
  const previous=saved.payload;
  return {...packet, summary:previous.summary, summaryModel:previous.summaryModel,
    summaryCreatedAt:previous.summaryCreatedAt, recovery:previous.recovery,
    tags:[...new Set([...packet.tags,...previous.tags])].sort()};
}
// A second caption can finish before the first queued write becomes visible.
export function sameRecoveryOriginal(job, assetId, proposed) {
  const saved=job?.payload;
  return Boolean(job?.asset_id===assetId && saved?.recovery?.run && saved.recovery.run===proposed.recovery.run &&
    saved.sourcePath===proposed.sourcePath && saved.sizeBytes===proposed.sizeBytes &&
    saved.sourceMtime===proposed.sourceMtime && saved.recovery.frames===proposed.recovery.frames &&
    saved.summary?.trim() && digest(saved)===job.source_hash && ['pending','applied','error'].includes(job.state));
}
export function eligible(source) {
  return Boolean(source.summary || source.context_summary || source.faces?.length || source.groups?.length);
}
export function scope(source) {
  return /^Google Photos\/Photos from [0-9]{4}\//.test(source.path) && !source.path.split('/').includes('..') && !path.isAbsolute(source.path);
}
export function mapAsset(source, candidates, ownerId, libraryId) {
  if(!scope(source))return {reason:'outside_import_scope'};
  const exact=candidates.filter(a=>a.originalPath===ROOT+source.path && a.isExternal!==false && a.libraryId!=null && a.ownerId===ownerId && a.libraryId===libraryId);
  if(exact.length!==1)return {reason:exact.length?'ambiguous_mapping':'missing_asset'};
  const a=exact[0];
  if(a.isTrashed)return {reason:'trashed_asset'};
  if(a.isOffline)return {reason:'offline_asset'};
  if(Number(a.exifInfo?.fileSizeInByte)!==Number(source.size_bytes))return {reason:'size_mismatch'};
  // Immich external checksums hash "path:" + absolute pathname, not image bytes.
  const expected=crypto.createHash('sha1').update('path:'+a.originalPath).digest('base64');
  if(a.checksum && a.checksum!==expected)return {reason:'path_checksum_mismatch'};
  return {asset:a};
}
export function metadataDecision(current, desired, previous, intent) {
  if(current && stable(current)===stable(desired))return 'unchanged';
  if(current && intent && stable(current)===stable(intent))return 'resume';
  // Never reclaim a key cleared/edited by someone after our previous successful write.
  if(previous && stable(current??null)!==stable(previous))return 'conflict';
  if(!previous && current)return 'conflict';
  return 'write';
}
export function normalizedBox(face) {
  if(!(face.imageWidth>0 && face.imageHeight>0))return null;
  return [face.boundingBoxX1/face.imageWidth,face.boundingBoxY1/face.imageHeight,face.boundingBoxX2/face.imageWidth,face.boundingBoxY2/face.imageHeight];
}
export function overlap(a,b) {
  if(!a || !b || [...a,...b].some(x=>!Number.isFinite(x)||x<0||x>1))return 0;
  const intersection=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
  const union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection;
  return union>0?intersection/union:0;
}
export function faceCandidate(sourceFace, faces, used=new Set()) {
  if(sourceFace.label_source!=='user')return {reason:'not_human_confirmed'};
  const matches=faces.filter(f=>!used.has(f.id)).map(f=>({face:f,score:overlap(sourceFace.box,normalizedBox(f))})).sort((a,b)=>b.score-a.score);
  if(!matches.length || matches[0].score<0.5)return {reason:'no_spatial_match'};
  if(matches[1] && matches[0].score-matches[1].score<0.2)return {reason:'ambiguous_spatial_match'};
  return matches[0];
}
