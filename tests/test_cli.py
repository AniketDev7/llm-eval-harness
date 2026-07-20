from typer.testing import CliRunner

from llm_eval.cli import app


def test_list_command_uses_documented_name():
    result = CliRunner().invoke(app, ["list", "--help"])

    assert result.exit_code == 0
    assert "List recent runs" in result.output


def test_accidental_list_dash_command_is_not_exposed():
    result = CliRunner().invoke(app, ["list-", "--help"])

    assert result.exit_code != 0
