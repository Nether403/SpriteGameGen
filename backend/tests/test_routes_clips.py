from httpx import ASGITransport, AsyncClient

from tests.test_routes_animate import _generate, _make


async def test_clips_are_isolated_selectable_and_delete_only_owned_assets(tmp_path):
    app, store, _ = _make(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_id = await _generate(client)
        first = await client.post(
            "/animate",
            json={"project_id": project_id, "action": "idle", "frames": 2, "clip_id": "idle-a"},
        )
        assert first.status_code == 200
        first_project = store.read_manifest(project_id)
        first_asset = first_project.clips["idle-a"].frames[0].rendered_filename
        first_bytes = store.asset_path(project_id, first_asset).read_bytes()

        second = await client.post(
            "/animate",
            json={"project_id": project_id, "action": "walk", "frames": 4, "clip_id": "walk-a"},
        )
        assert second.status_code == 200
        project = store.read_manifest(project_id)
        assert set(project.clips) == {"idle-a", "walk-a"}
        assert store.asset_path(project_id, first_asset).read_bytes() == first_bytes
        detail = await client.get(f"/projects/{project_id}")
        assert detail.json()["clips"]["walk-a"]["frames"][0]["url"]

        selected = await client.post(f"/projects/{project_id}/clips/idle-a/select")
        assert selected.status_code == 200
        assert store.read_manifest(project_id).active_clip_id == "idle-a"

        adjusted = await client.patch(
            f"/projects/{project_id}/clips/idle-a/frames/0",
            json={"enabled": False, "nudge_x": 2},
        )
        assert adjusted.status_code == 200
        repaired = store.read_manifest(project_id)
        assert repaired.clips["idle-a"].frames[0].enabled is False
        assert repaired.clips["walk-a"].frames[0].nudge_x == 0

        deleted = await client.delete(f"/projects/{project_id}/clips/walk-a")
        assert deleted.status_code == 200
        assert set(store.read_manifest(project_id).clips) == {"idle-a"}
        assert store.asset_path(project_id, first_asset).is_file()


async def test_quality_repair_and_frame_zip_make_no_provider_calls(tmp_path):
    app, store, provider = _make(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_id = await _generate(client)
        await client.post(
            "/animate",
            json={"project_id": project_id, "action": "idle", "frames": 2, "clip_id": "idle-a"},
        )
        calls = len(provider.edit_prompts)

        quality = await client.put(
            f"/projects/{project_id}/render-settings",
            json={"target_width": 16, "target_height": 16, "output_scale": 2, "color_limit": 8, "palette_mode": "shared_auto", "preset_palette": None, "custom_palette": []},
        )
        assert quality.status_code == 200
        repair = await client.patch(
            f"/projects/{project_id}/clips/idle-a/frames/0",
            json={"nudge_y": -1},
        )
        assert repair.status_code == 200
        exported = await client.post(
            "/export", json={"project_id": project_id, "clip_id": "idle-a"}
        )
        assert exported.status_code == 200
        assert exported.json()["frames_url"].split("?", 1)[0].endswith(".zip")
        assert len(provider.edit_prompts) == calls


async def test_canonical_create_route_allocates_a_new_clip_each_time(tmp_path):
    app, store, _ = _make(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project_id = await _generate(client)
        first = await client.post(
            f"/projects/{project_id}/clips",
            json={"action": "idle", "frames": 2, "direction": "left"},
        )
        second = await client.post(
            f"/projects/{project_id}/clips",
            json={"action": "walk", "frames": 4, "direction": "left"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(store.read_manifest(project_id).clips) == 2
