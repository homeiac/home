"""Rank existing face embeddings against confirmed people, without relabeling."""
from collections import defaultdict

import numpy as np

THRESHOLD = 0.55
MARGIN = 0.08


def vectors(rows: list[dict]) -> dict:
    """Separate model/dimension spaces and ignore invalid or zero vectors."""
    groups = defaultdict(list)
    for row in rows:
        value = np.asarray(row['embedding'] or [], dtype=np.float32)
        if value.ndim != 1 or not value.size or not np.isfinite(value).all():
            continue
        norm = float(np.linalg.norm(value))
        if norm > 1e-12:
            groups[row['model'], len(value)].append((row, value/norm))
    return groups


def match_batch(candidates: list[dict], references: list[dict], rejected: set[tuple[str,str]],
                threshold: float = THRESHOLD, margin: float = MARGIN) -> dict:
    """Return unambiguous suggestions; similarity is not an identity probability.

    Compare distinct people, not the top two reference photos of the same person.
    Rejections of a reference suppress that person's suggestion for this face.
    Chunk reference comparisons so memory doesn't grow as candidates × references.
    """
    result = {}
    reference_groups = vectors(references)
    rejected_people = defaultdict(set)
    names = {r['id']: r['person'] for r in references}
    for face_id, reference_id in rejected:
        if reference_id in names:
            rejected_people[face_id].add(names[reference_id])
    for space, candidate_group in vectors(candidates).items():
        people = defaultdict(list)
        for row, vector in reference_groups.get(space, []):
            people[row['person']].append((row, vector))
        if not people:
            continue
        matrix = np.stack([v for _,v in candidate_group])
        best = np.full(len(candidate_group), -2., dtype=np.float32)
        second = best.copy()
        winning = [None] * len(candidate_group)
        for person, refs in sorted(people.items()):
            scores = np.full(len(candidate_group), -2., dtype=np.float32)
            ref_ids = [None] * len(candidate_group)
            for offset in range(0,len(refs),256):
                block = refs[offset:offset+256]
                similarities = matrix @ np.stack([v for _,v in block]).T
                indices = similarities.argmax(axis=1)
                values = similarities[np.arange(len(candidate_group)),indices]
                for i in np.flatnonzero(values>scores):
                    scores[i] = values[i]
                    ref_ids[i] = block[indices[i]][0]['id']
            for i,(candidate,_) in enumerate(candidate_group):
                if person in rejected_people[candidate['id']]:
                    continue
                score = scores[i]
                if score > best[i]:
                    second[i],best[i] = best[i],score
                    winning[i] = dict(person=person, reference_id=ref_ids[i], score=float(score))
                elif score > second[i]:
                    second[i] = score
        for i,(candidate,_) in enumerate(candidate_group):
            if winning[i] and best[i]>=threshold and best[i]-second[i]>=margin:
                result[candidate['id']] = winning[i]
    return result
