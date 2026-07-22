import json

from app.cli import main


def test_actions_cli_writes_machine_json_to_stdout(capsys):
    assert main(["actions", "list"]) == 0

    output = capsys.readouterr()
    assert set(json.loads(output.out)) == {"actions", "errors"}
    assert output.err == ""


def test_recipe_validate_reports_safe_error_to_stderr(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    assert main(["recipe", "validate", str(path)]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "ValidationError" in output.err
    assert str(path) not in output.err
