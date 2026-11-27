"""Evaluate explicitly held-out examples with the upstream models; never write faces.

Run inside the tagger container with the private test JSON on stdin. Only derived
model caches are modified. The normal poller must remain disabled during testing.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, '/app')
import classifier
import data
import embedder
from inference import inference_session
from poller import THRESHOLD, THRESHOLD_FALLBACK

examples = json.load(sys.stdin)
directory = Path('/data')
embedder.load_embed_cache(directory)
config = data.load_config(directory)
references = {name: data.load_pet_refs(cfg.get('person_id') or name, directory)
              for name, cfg in config.items()}
training = {r['asset_id'] for refs in references.values() for r in refs}
negatives = data.load_negatives(directory)
training.update(n['asset_id'] for n in negatives)
assert not training.intersection(examples['positive']+examples['negative']), 'Test/training overlap'
results = []
with inference_session():
    fitted = classifier.build_classifier(list(config), references, negatives)
    if fitted is None:
        raise RuntimeError('No reference embeddings')
    names, model, scaler = fitted
    for expected, ids in examples.items():
        if expected not in ('positive', 'negative'):
            continue
        for asset in ids:
            image = embedder.fetch_thumbnail(asset)
            if image is None:
                raise RuntimeError('Test thumbnail unavailable')
            detections = embedder.crop_animals(image)
            crops = detections or [(None, image)]
            predictions = []
            for box, crop in crops:
                vector = embedder.embed_image(crop)
                if vector is None:
                    raise RuntimeError('Test embedding unavailable')
                name, probability = classifier.classify(vector, names, model, scaler)
                threshold = THRESHOLD if box is not None else THRESHOLD_FALLBACK
                predictions.append(dict(name=name, probability=round(probability, 4),
                                        detected=box is not None,
                                        accepted=name == 'Waffles' and probability >= threshold))
            results.append(dict(asset=asset, expected=expected, predictions=predictions,
                                matched=any(p['accepted'] for p in predictions)))
            print(json.dumps({'progress': len(results), 'total':len(examples['positive'])+len(examples['negative'])}), flush=True)
counts = dict(true_positive=0, false_negative=0, false_positive=0, true_negative=0)
for result in results:
    metric = ('true_positive' if result['matched'] else 'false_negative') if result['expected'] == 'positive' else ('false_positive' if result['matched'] else 'true_negative')
    counts[metric] += 1
embedder.save_embed_cache()
print(json.dumps({'counts': counts, 'results': results}), flush=True)
