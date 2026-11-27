"""Run inside the pinned tagger, exporting only fitted parameters to private stdin/out."""
import json
from pathlib import Path
import sys
sys.path.insert(0, '/app')
import classifier
import data
import embedder

directory = Path('/data')
embedder.load_embed_cache(directory)
config = data.load_config(directory)
assert list(config) == ['Waffles']
refs = data.load_pet_refs(config['Waffles']['person_id'], directory)
fitted = classifier.build_classifier(['Waffles'], {'Waffles': refs}, data.load_negatives(directory))
assert fitted is not None
names, model, scaler = fitted
def attributes(obj, keys):
    return {key: getattr(obj, key).tolist() if hasattr(getattr(obj, key), 'tolist') else getattr(obj, key) for key in keys}
print(json.dumps({'names': names, 'person_id': config['Waffles']['person_id'],
                 'references': len(refs), 'negatives': len(data.load_negatives(directory)),
                 'scaler': attributes(scaler, ['mean_', 'scale_', 'var_', 'n_features_in_']),
                 'model': attributes(model, ['coef_', 'intercept_', 'classes_', 'n_features_in_'])}))
