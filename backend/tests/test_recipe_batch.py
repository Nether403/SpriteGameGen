from app.recipe_batch import new_batch, run_batch
from app.recipes import RecipeV1


class Runner:
    def __init__(self):
        self.calls = 0

    def preflight(self, recipe):
        return None

    def run(self, recipe):
        self.calls += 1
        return f"project-{self.calls}"


class FailingRunner(Runner):
    def run(self, recipe):
        self.calls += 1
        raise RuntimeError("failed after provider work")


def test_batch_resume_skips_completed_provider_work(tmp_path):
    recipe = RecipeV1(prompt="knight", style="pixel")
    runner = Runner()
    path = tmp_path / "batch.json"

    first = run_batch(path, runner, new_batch([recipe]))
    second = run_batch(path, runner)

    assert first.items[0].status == "completed"
    assert second.items[0].status == "completed"
    assert runner.calls == 1


def test_batch_does_not_retry_indeterminate_running_work(tmp_path):
    recipe = RecipeV1(prompt="knight", style="pixel")
    state = new_batch([recipe])
    state.items[0].status = "running"
    path = tmp_path / "batch.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    runner = Runner()

    result = run_batch(path, runner)

    assert result.items[0].status == "indeterminate"
    assert runner.calls == 0


def test_batch_failure_becomes_indeterminate_and_is_not_retried(tmp_path):
    recipe = RecipeV1(prompt="knight", style="pixel")
    path = tmp_path / "batch.json"
    runner = FailingRunner()

    import pytest
    with pytest.raises(RuntimeError):
        run_batch(path, runner, new_batch([recipe]))
    result = run_batch(path, runner)

    assert result.items[0].status == "indeterminate"
    assert runner.calls == 1
