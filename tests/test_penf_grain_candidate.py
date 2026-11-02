import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import penf_grain_candidate_probe as grain
import penf_grain_diagnostic_probe as diagnostic
import penf_grain_order_probe as order
from penf_tone_graph_candidate import build_graph


class FilmGrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='penf-grain-')
        cls.graph = build_graph(Path(cls.temp.name)/'candidate')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_invalid_and_native_defaults_are_off(self):
        grain.decode_cases(self.graph)

    def test_native_banked_storage_and_reset_preserve_mono(self):
        grain.storage_cases()

    def test_acquired_snapshot_survives_later_edits(self):
        grain.snapshot_cases(self.graph)

    def test_capture_to_job_and_native_requests_keep_acquired_grain(self):
        grain.joined_capture_case(self.graph)

    def test_native_capture_order_preserves_strength(self):
        order.native_order_case(self.graph)

    def test_native_order_negative_controls(self):
        order.negative_controls(self.graph)

    def test_native_order_strength_profile_matrix(self):
        order.order_matrix(self.graph)

    def test_native_order_all_capture_slots(self):
        order.slot_cases(self.graph)

    def test_native_order_all_metadata_records(self):
        order.metadata_cases(self.graph)

    def test_native_order_invalid_contexts(self):
        order.invalid_cases(self.graph)

    def test_compact_and_invalid_owner_copy_after_capture_tag(self):
        order.copy_guard_cases(self.graph)

    def test_constructor_snapshots_survive_owner_reuse(self):
        order.owner_reuse_case(self.graph)

    def test_constructor_prepare_neutral_abi(self):
        order.neutral_abi_cases(self.graph)

    def test_unmapped_late_code_and_reuse_are_neutral(self):
        grain.unavailable_cases(self.graph)

    def test_explicit_async_profile_strength_request(self):
        grain.manager_cases(self.graph)

    def test_shared_grain_page_bounded_input(self):
        grain.editor_cases(self.graph)

    def test_native_viewer_grain_footer_and_delete(self):
        grain.viewer_cases(self.graph)

    def test_all_diagnostic_footer_patterns_and_levels(self):
        diagnostic.footers(self.graph)

    def test_custom_color_edits_skip_mask_and_reach_both_image_stages(self):
        grain.color_processing_cases(self.graph)

    def test_grain_page_does_not_draw_a_tone_curve(self):
        grain.grain_graph_case(self.graph)

    def test_native_color_mask_image_and_strength_matrix(self):
        grain.pipeline_cases(self.graph)


if __name__ == '__main__':
    unittest.main()
