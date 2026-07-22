from app.character_bundle import BUNDLE_FORMAT, BUNDLE_VERSION


def test_bundle_and_engine_profile_versions_are_independent():
    assert BUNDLE_FORMAT == "sprite-character-bundle"
    assert BUNDLE_VERSION == 1
