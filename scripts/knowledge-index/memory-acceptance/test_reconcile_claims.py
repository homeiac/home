"""Exercise the same caption/depiction path with synthetic people and a different medium."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from check_caption_reconciliation import check
from openlabel_album import DEPICTS, build_scene, card, link_depicted_faces, stable_id
from review_openlabel import select_together
from scan_caption_participants import reconcile_claims, review_with_sol


class ReconciliationTests(unittest.TestCase):
    def test_partial_revision_uses_original_and_only_accepted_actions(self):
        ref = dict(namespace="immich", face_id="other-face", person_id="other-person",
                   box=[.2,.2,.4,.4])
        audit = dict(ref, source_literal=" smiles while steering a car.", literal=" smiles in the portrait.",
                     spans=[dict(start=1, end=7, words="smiles", sense="smile")])
        regions = {("immich","other-face"):ref}
        parts = [[ref, audit["source_literal"]]]
        scene = build_scene("another-asset", parts, regions, 100, 100, audit)
        uid = stable_id("another-asset", "immich", "other-face")
        obj = scene["openlabel"]["objects"][uid]
        link = {"type": DEPICTS, "name":"depicts", "rdf_subjects":[{"uid":"1","type":"object"}],
                "rdf_objects":[{"uid":uid,"type":"object"}]}
        medium = {"openlabel":{"metadata":scene["openlabel"]["metadata"],
                  "objects":{uid:copy.deepcopy(obj),"1":{"name":"Portrait","type":"picture",
                  "object_data":{"bbox":[{"name":"frame","val":[40,40,70,70]}]}}},"relations":{"2":link}}}
        link_depicted_faces(scene, medium)
        result = card(scene, {"other-person":"Alex"})
        self.assertEqual([a["name"] for a in scene["openlabel"]["actions"].values()], ["smiles"])
        self.assertEqual(result["faces"][uid]["depicted_in"], ["1"])
        result.update(asset="another-asset",date="2001-02-03",media_type="Photo",date_status="confirmed")
        result["faces"]["physical"] = {"person_id":"other"}
        result["individual"].append({"subject":"physical"})
        self.assertFalse(select_together({"another-asset":result}, ["other","other-person"]))
        with self.assertRaisesRegex(ValueError, "caption changed"):
            build_scene("another-asset", [[ref," rides a bike."]], regions, 100, 100, audit)

    def test_local_reconciliation_receives_both_sources(self):
        review = {"phrase": "waves", "finding": "The raised hand belongs to a bystander."}
        job = {"regions": [{"face_id": "f", "namespace": "immich"}],
               "subject_face_id": "f", "subject_namespace": "immich",
               "captions": ["smiles and waves"], "corrections": [review]}
        corrected = dict(caption="The subject smiles.", kept=["smiles"], dropped=["waves"])
        incorrect = dict(caption="The subject smiles and waves.", kept=["smiles and waves"], dropped=[])
        rejection = {"errors": ["The hand belongs to a bystander."]}
        model = Mock(side_effect=[incorrect, rejection, corrected, {"errors": []}])
        self.assertEqual(reconcile_claims(job, model), dict(status="proposed", **corrected))
        for request in model.call_args_list:
            self.assertIn(job["captions"][0], request.args[1])
            self.assertIn(review["finding"], request.args[1])
        self.assertIn(rejection["errors"][0], model.call_args_list[2].args[1])
        model = Mock(side_effect=[incorrect, rejection, incorrect, rejection])
        unresolved = reconcile_claims(job, model)
        self.assertEqual(unresolved, {"status": "unresolved", "verification_errors": rejection["errors"]})
        self.assertEqual(model.call_count, 4)

    def test_independent_review_gets_only_the_disputed_text(self):
        job = {"regions": [{"face_id": "private-face", "namespace": "immich"}],
               "image": "/private/album/thumbnail.jpg", "subject_name": "Alex",
               "subject_face_id": "private-face", "subject_namespace": "immich",
               "captions": ["Alex smiles while waving."],
               "corrections": [{"phrase": "waving", "finding": "The hand beside Alex belongs to someone else."}]}
        local = dict(caption="The subject smiles while waving.", kept=["smiles", "waves"], dropped=[])
        accepted = dict(status="proposed", caption="The subject smiles.", kept=["smiles"], dropped=["waves"])
        def codex(command, **options):
            prompt = options["input"]
            for private in ("private-face", "thumbnail.jpg", "Alex"):
                self.assertNotIn(private, prompt)
            self.assertIn("The hand beside the subject belongs to someone else.", prompt)
            self.assertNotIn("--image", command)
            result_file = Path(command[command.index("--output-last-message") + 1])
            result_file.write_text(json.dumps(accepted))
        with patch("scan_caption_participants.subprocess.run", side_effect=codex):
            self.assertEqual(reconcile_claims(job, Mock(return_value=local), review_with_sol), accepted)

    def test_fact_check_compares_meaning_across_cold_runs(self):
        asset = "efbd02ee-d287-4348-81e1-557c9f7fe286"
        expected = {asset: {"required": ["smil"], "forbidden": ["waving"]}}
        with tempfile.TemporaryDirectory() as root:
            runs = [Path(root) / name for name in ("a", "b")]
            for path, caption in zip(runs, ("Alex smiles.", "Alex is smiling.")):
                path.mkdir()
                row = dict(status="proposed", input_hash="same-evidence", caption=caption)
                (path / (asset + ".json")).write_text(json.dumps(row))
            check(expected, runs)
            row["caption"] += " Alex is waving."
            (runs[1] / (asset + ".json")).write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError, "factual checks in run 2"):
                check(expected, runs)
