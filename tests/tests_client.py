import json
import os
import unittest
from typing import Optional
from unittest.mock import MagicMock, Mock, patch

from clickupython.client import ClickUpClient


def load_asset(filename):
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    file_path = os.path.join(assets_dir, f'{filename}.json')
    with open(file_path, 'r') as f:
        return json.load(f)


def mock_response_with_json(json_data: dict, status_code: int = 200, headers: Optional[dict[str, str]] = None):
    if headers is None:
        headers = {
            "x-ratelimit-remaining": "100",
            "x-ratelimit-reset": "1609459200"
        }
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.headers = headers
    return mock_response


class TestClientGetTask(unittest.TestCase):
    @patch('requests.get')
    def test_get_task(self, mock_get: MagicMock):
        # Arrange
        mock_response = load_asset('get_task_000000000_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="fake_api_key")

        # Act
        result = client.get_task(task_id="000000000")

        # Assert
        self.assertEqual(result.id, "000000000")
        self.assertEqual(result.name, "TEST")
        self.assertEqual(result.status.status, "TODO")

        mock_get.assert_called_once()
