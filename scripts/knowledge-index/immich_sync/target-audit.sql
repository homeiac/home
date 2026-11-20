SELECT a.id::text,a."originalPath" AS original_path,a."ownerId"::text AS owner_id,
       a."libraryId"::text AS library_id,a."isExternal" AS is_external,
       a."isOffline" AS is_offline,a."deletedAt" IS NOT NULL AS is_deleted,
       encode(a.checksum,'hex') AS checksum,a."checksumAlgorithm" AS checksum_algorithm,
       e."fileSizeInByte" AS size_bytes,e.description,e.latitude,e.longitude,e."dateTimeOriginal" AS taken_at,
       e."lockedProperties" AS locked_properties,
       (SELECT value FROM asset_metadata WHERE "assetId"=a.id AND key='home.photo-enrichment.v1') AS pilot_provenance
FROM asset a LEFT JOIN asset_exif e ON e."assetId"=a.id
