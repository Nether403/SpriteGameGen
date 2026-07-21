"""Deterministic structural pose-guide tests."""
import pytest
from PIL import Image, ImageChops

from app.models import Direction
from app.services.pose_reference import walk_pose_reference


def test_walk_pose_guides_are_distinct_and_select_eight_cycle_phases():
    guides = [walk_pose_reference(index, 8, Direction.RIGHT) for index in range(8)]

    assert all(image.mode == "RGB" and image.size == (256, 256) for image in guides)
    assert len({image.tobytes() for image in guides}) == 8


def test_four_frame_walk_uses_mirrored_contact_and_passing_guides():
    guides = [walk_pose_reference(index, 4, Direction.RIGHT) for index in range(4)]

    assert len({image.tobytes() for image in guides}) == 4
    assert ImageChops.difference(guides[0], guides[2]).getbbox() is not None
    assert ImageChops.difference(guides[1], guides[3]).getbbox() is not None


def test_left_pose_is_horizontal_mirror_of_right_pose():
    right = walk_pose_reference(1, 4, Direction.RIGHT)
    left = walk_pose_reference(1, 4, Direction.LEFT)

    assert left.tobytes() == right.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()


@pytest.mark.parametrize(
    ("index", "total"),
    [(-1, 4), (4, 4), (0, 0)],
)
def test_walk_pose_guide_rejects_invalid_bounds(index, total):
    with pytest.raises(ValueError):
        walk_pose_reference(index, total, Direction.RIGHT)


def test_walk_pose_guide_rejects_non_side_direction():
    with pytest.raises(ValueError, match="left/right"):
        walk_pose_reference(0, 4, Direction.UP)
