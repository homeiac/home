#!/usr/bin/env python3
"""Synthetic matching explanations and bounded review-group regression tests."""
import unittest
import numpy as np
from photo_enrichment.matching import rank_batch, match_batch, ReviewGroups, review_page, vectors, review_group_count, review_group_counts


def face(key, vector, person=None, model='m'):
    return dict(id=key, embedding=vector, person=person, model=model)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.refs=[face('a',[1.,0.],'A'),face('b',[0.,1.],'B')]

    def test_every_face_has_details_without_fabricating_scores(self):
        rows=[face('low',[-1.,0.]),face('tie',[1.,1.]),face('clear',[1.,.01]),
              face('zero',[0.,0.]),face('other',[1.,0.],model='other'),face('nan',[float('nan'),0.])]
        ranked=rank_batch(rows,self.refs,set())
        self.assertEqual(set(ranked),{r['id'] for r in rows})
        self.assertEqual(ranked['low']['reason'],'below_threshold')
        self.assertEqual(ranked['tie']['reason'],'ambiguous')
        self.assertEqual(ranked['clear']['reason'],'qualified')
        self.assertEqual(ranked['zero']['reason'],'invalid_embedding')
        self.assertEqual(ranked['other']['reason'],'no_compatible_references')
        self.assertIsNone(ranked['nan']['score'])
        self.assertAlmostEqual(ranked['tie']['score'],2**-.5,places=6)
        self.assertEqual(set(match_batch(rows,self.refs,set())),{'clear'})

    def test_no_references_and_no_self_match(self):
        row=face('a',[1.,0.],'A')
        self.assertEqual(rank_batch([row],[],set())['a']['reason'],'no_references')
        self.assertEqual(rank_batch([row],[row],set())['a']['reason'],'no_other_references')
        ranked=rank_batch([row],self.refs,set())['a']
        self.assertEqual(ranked['person'],'B')
        self.assertEqual(ranked['score'],0)

    def test_rejected_candidate_remains_explained_not_eligible(self):
        ranked=rank_batch([face('c',[1.,0.])],self.refs,{('c','a')})['c']
        self.assertEqual(ranked['person'],'A')
        self.assertEqual(ranked['reason'],'rejected')
        self.assertFalse(ranked['qualified'])

    def test_multiple_references_of_one_person_do_not_make_ambiguity(self):
        refs=self.refs+[face('a2',[.99,.01],'A')]
        self.assertTrue(rank_batch([face('c',[1.,0.])],refs,set())['c']['qualified'])

    def test_prepared_references_match_uncached_results(self):
        rows=[face('a',[1.,0.],'A'),face('c',[.1,.9])]
        self.assertEqual(rank_batch(rows,self.refs,set()),
                         rank_batch(rows,self.refs,set(),reference_groups=vectors(self.refs)))

    def test_negative_cosine_is_not_clamped_to_zero(self):
        ranked=rank_batch([face('c',[-1.,0.])],[self.refs[0]],set())['c']
        self.assertEqual(ranked['score'],-1.)
        self.assertFalse(ranked['qualified'])


class GroupTests(unittest.TestCase):
    def group(self,rows,refs=()):
        groups=ReviewGroups()
        for start in range(0,len(rows),256):
            batch=rows[start:start+256]
            groups.add(batch,rank_batch(batch,list(refs),set()))
        return groups

    def test_repeated_appearances_group_without_identity_writes(self):
        rows=[face(str(i),[1.,0.]) for i in range(1000)]
        groups=self.group(rows)
        self.assertEqual(len(groups.groups),1)
        self.assertEqual(len(groups.groups['0']),1000)
        self.assertTrue(all(row['person'] is None for row in rows))
        self.assertEqual(len(groups.membership),1000)

    def test_incompatible_and_invalid_vectors_are_not_grouped_together(self):
        rows=[face('a',[1.,0.]),face('b',[1.,0.],model='other'),face('c',[0.,0.]),face('d',[0.,0.])]
        self.assertEqual(len(self.group(rows).groups),4)

    def test_groups_do_not_chain_across_an_anchor_threshold(self):
        # B can resemble A and C, but C must meet A's threshold to join A.
        rows=[face(str(i),[float(np.cos(a)),float(np.sin(a))]) for i,a in enumerate([0.,.5,1.])]
        groups=self.group(rows)
        self.assertNotEqual(groups.membership['0'],groups.membership['2'])

    def test_qualified_people_have_separate_review_collections(self):
        refs=[face('a',[1.,0.],'A'),face('b',[0.,1.],'B')]
        rows=[face('x',[1.,0.]),face('y',[1.,.02]),face('z',[0.,1.])]
        groups=self.group(rows,refs)
        self.assertEqual(groups.membership['x'],groups.membership['y'])
        self.assertNotEqual(groups.membership['x'],groups.membership['z'])

    def test_pagination_members_and_stale_confirmed_faces(self):
        review=dict(groups={'a':['a','b','c'],'d':['d']},generation='g')
        page=review_page({'b','c','d','new'},review,0,2)
        self.assertEqual(page['total'],3)
        self.assertEqual(review_group_count({'b','c','d','new'},review),3)
        self.assertEqual(page['ids'],['b','d'])
        self.assertEqual(page['group_cards']['b'],dict(id='a',count=2))
        inside=review_page({'b','c','d'},review,1,1,'a')
        self.assertEqual(inside['ids'],['c'])
        self.assertEqual(inside['total'],2)
        self.assertFalse(inside['grouped'])

    def test_default_scope_keeps_singletons_accessible_separately(self):
        review=dict(groups={'a':['a','b'],'c':['c']},generation='g')
        visible={'a','b','c','new'}
        self.assertEqual(review_page(visible,review,0,48,scope='repeated')['ids'],['a'])
        singles=review_page(visible,review,0,48,scope='ungrouped')
        self.assertEqual(singles['ids'],['c','new'])
        self.assertFalse(singles['grouped'])
        self.assertEqual(singles['group_cards'],{})
        self.assertEqual(review_group_counts(visible,review),dict(review_groups=1,ungrouped=2))

    def test_pending_group_pass_does_not_dump_whole_library(self):
        page=review_page({str(i) for i in range(78000)}, {},0,48)
        self.assertEqual(page['ids'],[])
        self.assertEqual(page['total'],0)


if __name__=='__main__': unittest.main()
