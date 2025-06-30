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
    mock_response.ok = status_code < 400
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


class TestClientAddTaskLink(unittest.TestCase):
    @patch('requests.post')
    def test_add_task_link(self, mock_post: MagicMock):
        # Arrange
        task_id = "task123"
        links_to = "task456"

        # Mock response with a task object
        mock_response_data = {
            "task": load_asset('get_task_000000000_response')
        }
        mock_post.return_value = mock_response_with_json(mock_response_data)

        client = ClickUpClient(token="fake_api_key")

        # Act
        result = client.add_task_link(task_id=task_id, links_to=links_to)

        # Assert
        self.assertTrue(result)
        mock_post.assert_called_once()

        # Verify the correct URL was called
        args, kwargs = mock_post.call_args
        self.assertIn(f"task/{task_id}/link/{links_to}", args[0])
