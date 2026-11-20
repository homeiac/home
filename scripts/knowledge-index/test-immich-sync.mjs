import {test} from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {ROOT,sourcePacket,digest,mapAsset,metadataDecision,faceCandidate} from './immich_sync/core.mjs';
const source={path:'Google Photos/Photos from 2025/a.jpg',size_bytes:123,summary:'first',faces:[],groups:[]};
const asset={id:'asset',ownerId:'owner',libraryId:'library',isExternal:true,originalPath:ROOT+source.path,exifInfo:{fileSizeInByte:123}};
asset.checksum=crypto.createHash('sha1').update('path:'+asset.originalPath).digest('base64');
test('matches only one correctly scoped external asset with compatible size and path checksum',()=>{
 assert.equal(mapAsset(source,[asset],'owner','library').asset.id,'asset');
 assert.equal(mapAsset(source,[{...asset,isExternal:undefined}],'owner','library').asset.id,'asset');
 assert.equal(mapAsset(source,[{...asset,libraryId:null}],'owner','library').reason,'missing_asset');
 assert.equal(mapAsset(source,[asset,asset],'owner','library').reason,'ambiguous_mapping');
 assert.equal(mapAsset(source,[{...asset,isExternal:false}],'owner','library').reason,'missing_asset');
 assert.equal(mapAsset(source,[{...asset,checksum:'wrong'}],'owner','library').reason,'path_checksum_mismatch');
 assert.equal(mapAsset({...source,size_bytes:999},[asset],'owner','library').reason,'size_mismatch');
 assert.equal(mapAsset({...source,path:'Google Photos/Locked Folder/a.jpg'},[asset],'owner','library').reason,'outside_import_scope');
});
test('fingerprints include revised captions, human labels and group context',()=>{
 const old=digest(sourcePacket(source));
 assert.notEqual(digest(sourcePacket({...source,summary:'revised'})),old);
 assert.notEqual(digest(sourcePacket({...source,faces:[{id:'f',person:'Known',label_source:'user'}]})),old);
 assert.notEqual(digest(sourcePacket({...source,groups:[{id:'g',location:'Atlanta'}]})),old);
});
test('updates owned machine metadata but protects edits and intentional removal',()=>{
 const a={summary:'first'},b={summary:'revised'},human={summary:'user edit'};
 assert.equal(metadataDecision(null,a,null,null),'write');
 assert.equal(metadataDecision(a,b,a,null),'write');
 assert.equal(metadataDecision(human,b,a,null),'conflict');
 assert.equal(metadataDecision(null,b,a,null),'conflict');
 assert.equal(metadataDecision(b,b,a,b),'unchanged');
 assert.equal(metadataDecision(a,b,null,a),'resume');
});
test('spatial transfer only uses unambiguous confirmed labels, never model suggestions',()=>{
 const f={id:'target',imageWidth:100,imageHeight:100,boundingBoxX1:10,boundingBoxY1:10,boundingBoxX2:40,boundingBoxY2:40};
 const old={id:'source',label_source:'user',box:[.1,.1,.4,.4]};
 assert.equal(faceCandidate(old,[f]).face.id,'target');
 assert.equal(faceCandidate({...old,label_source:'automatic'},[f]).reason,'not_human_confirmed');
 assert.equal(faceCandidate(old,[f,{...f,id:'other'}]).reason,'ambiguous_spatial_match');
 assert.equal(faceCandidate(old,[f],new Set(['target'])).reason,'no_spatial_match');
});
