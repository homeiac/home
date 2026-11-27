#!/usr/bin/env python3
"""Compare frozen description queries with model output and a private visual audit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('quality_directory',type=Path);p.add_argument('query_directory',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
rows=json.loads((args.quality_directory/'descriptions.json').read_text());processed=[r for r in rows if r['status']=='complete']
pattern=re.compile(r'\b(dogs?|pupp(?:y|ies)|canines?|husk(?:y|ies)|shepherds?|retrievers?)\b',re.I)
variants={'broad_with_waffles':lambda r:r['dog_description'],'dog_terms':lambda r:bool(pattern.search(r['description'] or '')),
          'dog_terms_or_missing_description':lambda r:not r['has_description'] or bool(pattern.search(r['description'] or ''))}
result={'population':len(processed),'model_matched_assets':sum(r['matched'] for r in processed),'query_variants':{}}
for name,query in variants.items():
    selected=[r for r in processed if query(r)]
    result['query_variants'][name]={'candidates':len(selected),'model_matches_retained':sum(r['matched'] for r in selected),
      'model_matches_omitted':sum(r['matched'] and not query(r) for r in processed),'query_hits_without_model_match':sum(not r['matched'] for r in selected),
      'inference_reduction_percent':round(100*(1-len(selected)/len(processed)),2)}
manifest=args.query_directory/'sample.json';digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
assert digest=='8e6c89740554784f0909fc39234b788b78e264a47049f2afd1b886cade5b8543','Labels belong to the frozen reviewed sample'
# These labels reflect visual inspection of the frozen images, not descriptions.
labels=[]
for r in json.loads(manifest.read_text()):
    i=r['index'];labels.append({'index':i,'dog_visible':i<65 and i not in {0,5,6,7,11,19},
        'clear_waffles_model_miss':i in {9,12,14,17,20,24,25,29,30}})
(args.query_directory/'visual-labels.json').write_text(json.dumps({'reviewer':'assistant visual inspection','manifest_sha256':digest,'labels':labels},indent=2)+'\n')
result['visual_audit']={'query_positive_model_negative':{'sampled':32,'dog_visible':26,'no_visible_dog':6,'clear_waffles_misses':9},
  'query_negative_model_positive':{'sampled':33,'dog_visible':33,'obvious_wrong_dog_tags':0},
  'query_negative_model_negative':{'sampled':24,'dog_visible':0},
  'separate_accepted_sample':{'random_across_backends':32,'lowest_confidence':12,'obvious_wrong_dog_tags':0},
  'separate_low_confidence_rejected_sample':{'sampled':12,'clear_waffles_misses':5,'identity_uncertain':3,'other_dogs_or_no_waffles':4},
  'manifest_sha256':digest}
result['limits']=['Full-population agreement counts use model output, not independently verified truth.',
 'Visual labels are assistant judgments; obscured/rear/young-dog identity is not owner-confirmed.',
 'Stratified samples are not pooled into library-wide precision or recall; query hits can correctly show dogs other than Waffles.',
 'The stricter query removes the food-word ambiguity after inspecting this sample; it is not an untouched test set.']
args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
