import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from helmupdater import (
    app,
    build_chart,
    current_system,
    get_charts,
    get_hash,
    update_one_chart,
)

runner = CliRunner()


class TestCurrentSystem:
    def test_current_system_returns_string(self):
        with patch("helmupdater.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="aarch64-darwin\n")
            result = current_system()
            assert result == "aarch64-darwin"
            mock_run.assert_called_once()

    def test_current_system_caches_result(self):
        # Clear cache before test
        current_system.cache_clear()
        with patch("helmupdater.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="x86_64-linux\n")
            result1 = current_system()
            result2 = current_system()
            assert result1 == result2
            # Called only once due to cache
            assert mock_run.call_count == 1


class TestBuildChart:
    def test_build_chart_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stderr="", stdout="")
            result = build_chart("myrepo", "mychart")
            assert result.returncode == 0

    def test_build_chart_failure_without_check(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="error")
            result = build_chart("myrepo", "mychart", check=False)
            assert result.returncode == 1


class TestGetHash:
    def test_get_hash_extracts_from_stderr(self):
        with patch("helmupdater.build_chart") as mock_build:
            mock_build.return_value = Mock(
                stderr="some output\ngot: sha256-abc123=\nmore output"
            )
            result = get_hash("repo", "chart")
            assert result == "sha256-abc123="

    def test_get_hash_raises_on_missing_hash(self):
        with patch("helmupdater.build_chart") as mock_build:
            mock_build.return_value = Mock(stderr="no hash here\n")
            with pytest.raises(RuntimeError):
                get_hash("repo", "chart")


class TestGetCharts:
    def test_get_charts_returns_dict(self):
        with patch("subprocess.check_output") as mock_output:
            test_data = {"repo1": {"chart1": {"version": "1.0.0"}}}
            mock_output.return_value = json.dumps(test_data).encode()
            result = get_charts()
            assert result == test_data


class TestUpdateOneChart:
    @patch("helmupdater.get_hash")
    @patch("helmupdater.build_chart")
    @patch("builtins.open", create=True)
    @patch("helmupdater.requests.get")
    def test_update_one_chart_no_update_needed(
        self, mock_get, mock_open, mock_build, mock_get_hash
    ):
        mock_response = Mock()
        mock_response.text = """
entries:
  chart:
    - version: "0.1.0"
"""
        mock_get.return_value = mock_response

        local_chart = {"repo": "http://example.com/", "version": "1.0.0"}
        update_one_chart(
            "repo", "chart", local_chart, commit=False, fail_on_fetch=True
        )
        # Should return early without writing files
        mock_open.assert_not_called()

    @patch("helmupdater.get_hash")
    @patch("helmupdater.build_chart")
    @patch("builtins.open", create=True)
    @patch("helmupdater.requests.get")
    def test_update_one_chart_new_version_available(
        self, mock_get, mock_open, mock_build, mock_get_hash
    ):
        mock_response = Mock()
        mock_response.text = """
entries:
  chart:
    - version: "2.0.0"
"""
        mock_get.return_value = mock_response
        mock_get_hash.return_value = "sha256-newHash="
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        local_chart = {"repo": "http://example.com/", "version": "1.0.0"}
        update_one_chart(
            "repo", "chart", local_chart, commit=False, fail_on_fetch=True
        )
        # Should write to file
        mock_open.assert_called()

    @patch("helmupdater.subprocess.run")
    @patch("helmupdater.get_hash")
    @patch("helmupdater.build_chart")
    @patch("builtins.open", create=True)
    @patch("helmupdater.requests.get")
    def test_update_one_chart_with_commit(
        self, mock_get, mock_open, mock_build, mock_get_hash, mock_run
    ):
        mock_response = Mock()
        mock_response.text = """
entries:
  chart:
    - version: "2.0.0"
"""
        mock_get.return_value = mock_response
        mock_get_hash.return_value = "sha256-newHash="
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        local_chart = {"repo": "http://example.com/", "version": "1.0.0"}
        update_one_chart(
            "repo", "chart", local_chart, commit=True, fail_on_fetch=True
        )
        # Should call git add and git commit
        assert any("git" in str(call) for call in mock_run.call_args_list)


class TestUpdateCommand:
    def test_update_command_help(self):
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.stdout


class TestUpdateAllCommand:
    def test_update_all_command_help(self):
        result = runner.invoke(app, ["update-all", "--help"])
        assert result.exit_code == 0


class TestInitCommand:
    def test_init_command_help(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
