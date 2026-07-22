import json

from app.actions import load_action_catalog


def test_bundled_actions_have_distinct_choreography():
    catalog = load_action_catalog()

    assert set(catalog.actions) >= {"idle", "walk", "run", "attack", "jump"}
    assert all(len(catalog.actions[name].phases) > 1 for name in ("idle", "run", "attack", "jump"))


def test_external_pack_is_data_only_bounded_and_collision_isolated(tmp_path):
    valid = {
        "format": "sprite-action-pack",
        "format_version": 1,
        "id": "community",
        "version": "1",
        "actions": [
            {
                "id": "dance",
                "motion": "dance",
                "min_frames": 2,
                "max_frames": 4,
                "default_frames": 4,
            }
        ],
    }
    (tmp_path / "valid.json").write_text(json.dumps(valid), encoding="utf-8")
    collision = {**valid, "id": "collision"}
    collision["actions"] = [{**valid["actions"][0], "id": "walk"}]
    (tmp_path / "collision.json").write_text(json.dumps(collision), encoding="utf-8")
    (tmp_path / "duplicate.json").write_text(
        '{"format":"sprite-action-pack","format":"bad"}', encoding="utf-8"
    )

    catalog = load_action_catalog(tmp_path)

    assert "dance" in catalog.actions
    assert catalog.actions["walk"].motion
    assert len(catalog.errors) == 2


def test_external_loader_does_not_recurse_or_follow_symlinks(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "ignored.json").write_text("{}", encoding="utf-8")

    catalog = load_action_catalog(tmp_path)

    assert not catalog.errors
