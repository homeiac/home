"""Rank saved face embeddings; retain explanations without applying identities."""
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


def rank_batch(candidates: list[dict], references: list[dict], rejected: set[tuple[str,str]],
               threshold: float = THRESHOLD, margin: float = MARGIN, reference_groups: dict | None = None) -> dict:
    """Explain the closest distinct-person candidate, even when it cannot qualify.

    A reference cannot match itself. Rejected people remain visible as rejected;
    they cannot be suggested or silently replaced by a weaker identity. Scores
    remain cosine similarities, including negative values, never probabilities.
    """
    result = {r['id']: dict(person=None, reference_id=None, score=None, qualified=False,
                           reason='invalid_embedding', threshold=threshold, required_margin=margin)
              for r in candidates}
    reference_groups = vectors(references) if reference_groups is None else reference_groups
    names = {r['id']: r['person'] for r in references}
    rejected_people = defaultdict(set)
    for face_id, reference_id in rejected:
        if reference_id in names:
            rejected_people[face_id].add(names[reference_id])
    for space, candidate_group in vectors(candidates).items():
        people = defaultdict(list)
        for row, vector in reference_groups.get(space, []):
            people[row['person']].append((row, vector))
        for row, _ in candidate_group:
            result[row['id']]['reason'] = 'no_references' if not references else 'no_compatible_references'
        if not people:
            continue
        matrix = np.stack([v for _, v in candidate_group])
        best = np.full(len(candidate_group), -2., dtype=np.float32)
        second = best.copy()
        winning = [None] * len(candidate_group)
        candidate_ids = np.asarray([r['id'] for r, _ in candidate_group])
        for person, refs in sorted(people.items()):
            scores = np.full(len(candidate_group), -2., dtype=np.float32)
            ref_ids = [None] * len(candidate_group)
            for offset in range(0, len(refs), 256):
                block = refs[offset:offset+256]
                similarities = matrix @ np.stack([v for _, v in block]).T
                similarities[candidate_ids[:, None] == np.asarray([r['id'] for r, _ in block])[None, :]] = -2.
                indices = similarities.argmax(axis=1)
                values = similarities[np.arange(len(candidate_group)), indices]
                for i in np.flatnonzero(values > scores):
                    scores[i] = values[i]
                    ref_ids[i] = block[indices[i]][0]['id']
            for i, (candidate, _) in enumerate(candidate_group):
                score = scores[i]
                if score > best[i]:
                    second[i], best[i] = best[i], score
                    winning[i] = dict(person=person, reference_id=ref_ids[i], score=float(np.clip(score, -1, 1)))
                elif score > second[i]:
                    second[i] = score
        for i, (candidate, _) in enumerate(candidate_group):
            if winning[i] is None:
                result[candidate['id']]['reason'] = 'no_other_references'
                continue
            gap = float(best[i]-second[i]) if second[i] >= -1.00001 else None
            reason = ('rejected' if winning[i]['person'] in rejected_people[candidate['id']] else
                      'below_threshold' if best[i] < threshold else
                      'ambiguous' if gap is not None and gap < margin else 'qualified')
            result[candidate['id']].update(winning[i], reason=reason, qualified=reason == 'qualified',
                                           margin=gap, runner_up_score=float(np.clip(second[i], -1, 1)) if gap is not None else None)
    return result


def match_batch(candidates: list[dict], references: list[dict], rejected: set[tuple[str,str]],
                threshold: float = THRESHOLD, margin: float = MARGIN) -> dict:
    """Return only qualifying suggestions for existing callers and acceptance rules."""
    return {key: {k: value[k] for k in ('person', 'reference_id', 'score')}
            for key, value in rank_batch(candidates, references, rejected, threshold, margin).items()
            if value['qualified']}


class ReviewGroups:
    """Bounded approximate candidate search, followed by exact anchor comparison.

    Qualifying named suggestions share a review collection. Other valid vectors
    form conservative groups at cosine >= .80 to a fixed anchor (no transitive
    chaining). LSH may split a person across groups; it never bypasses the exact
    threshold. No all-pairs matrix, dependency, identity write or detection loss.
    """
    def __init__(self, threshold: float = .80):
        self.threshold = threshold
        self.groups = {}
        self.spaces = {}
        self.named = {}
        self.membership = {}

    def add(self, rows: list[dict], details: dict) -> None:
        valid = {r['id']: (space, vector) for space, values in vectors(rows).items() for r, vector in values}
        for row in rows:
            if row.get('person') is not None:
                continue
            face_id = row['id']
            detail = details[face_id]
            group_id = None
            if detail['qualified']:
                group_id = self.named.get(detail['person'])
                if group_id is None:
                    group_id = face_id
                    self.named[detail['person']] = group_id
            elif face_id in valid:
                space, vector = valid[face_id]
                if space not in self.spaces:
                    # Bounded buckets keep candidate lookup subquadratic even
                    # for a large homogeneous library. Exact duplicate vectors
                    # always share their anchor's buckets.
                    self.spaces[space] = dict(planes=np.random.default_rng(217).normal(size=(12, 10, space[1])).astype(np.float32),
                                               buckets=defaultdict(list), anchors={})
                index = self.spaces[space]
                bits = np.einsum('tbd,d->tb', index['planes'], vector) >= 0
                keys = [(i, int(np.dot(values, 1 << np.arange(10)))) for i, values in enumerate(bits)]
                candidates = sorted({anchor for key in keys for anchor in index['buckets'][key]})
                if candidates:
                    scores = np.stack([index['anchors'][key] for key in candidates]) @ vector
                    winner = int(scores.argmax())
                    if scores[winner] >= self.threshold:
                        group_id = candidates[winner]
                if group_id is None:
                    group_id = face_id
                    index['anchors'][group_id] = vector
                    for key in keys:
                        if len(index['buckets'][key]) < 256:
                            index['buckets'][key].append(group_id)
            if group_id is None:
                group_id = face_id
            self.groups.setdefault(group_id, []).append(face_id)
            self.membership[face_id] = group_id


def review_page(visible: set[str], review: dict, offset: int, limit: int, group: str = '', scope: str = 'all') -> dict:
    """Paginate representatives or one group's members, excluding obsolete faces."""
    groups = {key: [member for member in members if member in visible]
              for key, members in review.get('groups', {}).items()}
    groups = {key: members for key, members in groups.items() if members}
    generation = review.get('generation')
    if group:
        ids = groups.get(group, [])
        return dict(ids=ids[offset:offset+limit], total=len(ids), grouped=False,
                    group=group, generation=generation, group_cards={})
    # Unmatched records arriving after the last completed pass remain individual
    # review groups until the next pass. During startup return a loading state.
    if 'groups' in review:
        covered = {member for members in groups.values() for member in members}
        groups.update({key: [key] for key in sorted(visible-covered)})
    if scope == 'repeated':groups = {key:members for key,members in groups.items() if len(members)>1}
    elif scope == 'ungrouped':groups = {key:members for key,members in groups.items() if len(members)==1}
    elif scope != 'all':raise ValueError('Invalid review scope')
    ordered = sorted(groups, key=lambda key: (-len(groups[key]), key))
    page = ordered[offset:offset+limit]
    cards = {groups[key][0]: dict(id=key, count=len(groups[key])) for key in page}
    return dict(ids=list(cards), total=len(groups), grouped=scope != 'ungrouped', group='',
                generation=generation, group_cards=cards if scope != 'ungrouped' else {})


def review_group_count(visible: set[str], review: dict) -> int:
    """Count active groups plus new detections awaiting the next background pass."""
    if 'groups' not in review:
        return 0
    covered = set()
    count = 0
    for members in review['groups'].values():
        active = visible.intersection(members)
        if active:
            count += 1
            covered.update(active)
    return count + len(visible-covered)


def review_group_counts(visible: set[str], review: dict) -> dict:
    """Separate repeated review groups from individual ungrouped detections."""
    if 'groups' not in review:return dict(review_groups=0,ungrouped=0)
    covered=set();repeated=singles=0
    for members in review['groups'].values():
        active=visible.intersection(members)
        covered.update(active)
        if len(active)>1:repeated+=1
        elif active:singles+=1
    return dict(review_groups=repeated,ungrouped=singles+len(visible-covered))
