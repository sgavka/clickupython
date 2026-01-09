import json
import os
import unittest
from datetime import datetime
from time import sleep
from typing import Optional
from unittest.mock import MagicMock, Mock, patch, call

from clickup_sdk import exceptions
from clickup_sdk.client import ClickUpClient


def load_asset(filename):
    """Load a JSON asset file from the assets directory."""
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    file_path = os.path.join(assets_dir, f'{filename}.json')
    with open(file_path, 'r') as f:
        return json.load(f)


def mock_response_with_json(json_data: dict, status_code: int = 200, headers: Optional[dict[str, str]] = None):
    """Create a mock response object with JSON data."""
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
    mock_response.text = json.dumps(json_data)
    return mock_response


class TestClientInitialization(unittest.TestCase):
    """Tests for ClickUpClient initialization."""

    def test_init_with_defaults(self):
        """Test client initialization with default parameters."""
        client = ClickUpClient(token="test_token")
        self.assertEqual(client.token, "test_token")
        self.assertEqual(client.api_url, "https://api.clickup.com/api/v2/")
        self.assertEqual(client.request_count, 0)
        self.assertEqual(client.rate_limit_remaining, 100)
        self.assertFalse(client.retry_rate_limited_requests)

    def test_init_with_custom_params(self):
        """Test client initialization with custom parameters."""
        custom_url = "https://custom.api.com/"
        client = ClickUpClient(
            token="test_token",
            api_url=custom_url,
            retry_rate_limited_requests=True,
            rate_limit_buffer_wait_time=10,
            start_rate_limit_remaining=50
        )
        self.assertEqual(client.api_url, custom_url)
        self.assertTrue(client.retry_rate_limited_requests)
        self.assertEqual(client.rate_limit_buffer_wait_time, 10)
        self.assertEqual(client.rate_limit_remaining, 50)


class TestClientLists(unittest.TestCase):
    """Tests for List-related methods."""

    @patch('requests.get')
    def test_get_list(self, mock_get: MagicMock):
        """Test getting a single list."""
        mock_response = load_asset('get_list_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_list(list_id="123456789")

        self.assertEqual(result.id, "123456789")
        self.assertEqual(result.name, "Test List")
        self.assertEqual(result.content, "Test list description")
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertIn("list/123456789", args[0])

    @patch('requests.get')
    def test_get_lists(self, mock_get: MagicMock):
        """Test getting lists from a folder."""
        mock_response = load_asset('get_lists_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_lists(folder_id="456789123")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.lists), 2)
        self.assertEqual(result.lists[0].name, "Test List 1")
        self.assertEqual(result.lists[1].name, "Test List 2")
        mock_get.assert_called_once()

    @patch('requests.post')
    def test_create_list(self, mock_post: MagicMock):
        """Test creating a list in a folder."""
        mock_response = load_asset('create_list_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_list(
            folder_id="456789123",
            name="New Test List",
            content="Newly created list",
            due_date="1650000000000",
            priority=2,
            status="active"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "New Test List")
        self.assertEqual(result.content, "Newly created list")
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_create_folderless_list(self, mock_post: MagicMock):
        """Test creating a folderless list in a space."""
        mock_response = load_asset('create_list_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_folderless_list(
            space_id="789123456",
            name="New Test List",
            content="Newly created list"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "New Test List")
        mock_post.assert_called_once()

    @patch('requests.delete')
    def test_delete_list(self, mock_delete: MagicMock):
        """Test deleting a list."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_list(list_id="123456789")

        self.assertTrue(result)
        mock_delete.assert_called_once()

    @patch('requests.post')
    def test_add_task_to_list(self, mock_post: MagicMock):
        """Test adding a task to a list."""
        mock_post.return_value = mock_response_with_json({})

        client = ClickUpClient(token="test_token")
        result = client.add_task_to_list(task_id="999888777", list_id="123456789")

        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch('requests.delete')
    def test_remove_task_from_list(self, mock_delete: MagicMock):
        """Test removing a task from a list."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.remove_task_from_list(task_id="999888777", list_id="123456789")

        self.assertTrue(result)
        mock_delete.assert_called_once()


class TestClientFolders(unittest.TestCase):
    """Tests for Folder-related methods."""

    @patch('requests.get')
    def test_get_folder(self, mock_get: MagicMock):
        """Test getting a single folder."""
        mock_response = load_asset('get_folder_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_folder(folder_id="456789123")

        self.assertIsNotNone(result)
        self.assertEqual(result.id, "456789123")
        self.assertEqual(result.name, "Test Folder")
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_folders(self, mock_get: MagicMock):
        """Test getting folders from a space."""
        mock_response = load_asset('get_folders_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_folders(space_id="789123456")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.folders), 2)
        self.assertEqual(result.folders[0].name, "Test Folder 1")
        mock_get.assert_called_once()

    @patch('requests.post')
    def test_create_folder(self, mock_post: MagicMock):
        """Test creating a folder."""
        mock_response = load_asset('get_folder_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_folder(space_id="789123456", name="Test Folder")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Test Folder")
        mock_post.assert_called_once()

    @patch('requests.put')
    def test_update_folder(self, mock_put: MagicMock):
        """Test updating a folder."""
        mock_response = load_asset('get_folder_response')
        mock_response['name'] = "Updated Folder"
        mock_put.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.update_folder(folder_id="456789123", name="Updated Folder")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Updated Folder")
        mock_put.assert_called_once()

    @patch('requests.delete')
    def test_delete_folder(self, mock_delete: MagicMock):
        """Test deleting a folder."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_folder(folder_id="456789123")

        self.assertTrue(result)
        mock_delete.assert_called_once()


class TestClientTasks(unittest.TestCase):
    """Tests for Task-related methods."""

    @patch('requests.get')
    def test_get_task(self, mock_get: MagicMock):
        """Test getting a single task."""
        mock_response = load_asset('get_task_000000000_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_task(task_id="000000000")

        self.assertEqual(result.id, "000000000")
        self.assertEqual(result.name, "TEST")
        self.assertEqual(result.status.status, "TODO")
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_task_with_subtasks(self, mock_get: MagicMock):
        """Test getting a task with subtasks."""
        mock_response = load_asset('get_task_000000000_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_task(task_id="000000000", include_subtasks=True)

        self.assertEqual(result.id, "000000000")
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertIn("include_subtasks=true", args[0])

    @patch('requests.get')
    def test_get_tasks(self, mock_get: MagicMock):
        """Test getting tasks from a list."""
        mock_response = load_asset('get_tasks_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_tasks(list_id="123456789")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.tasks), 2)
        self.assertEqual(result.tasks[0].name, "Task 1")
        self.assertEqual(result.tasks[1].name, "Task 2")
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_tasks_with_filters(self, mock_get: MagicMock):
        """Test getting tasks with filters."""
        mock_response = load_asset('get_tasks_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_tasks(
            list_id="123456789",
            archived=False,
            page=0,
            order_by="created",
            statuses=["TODO", "IN PROGRESS"]
        )

        self.assertIsNotNone(result)
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertIn("archived=false", args[0])
        self.assertIn("statuses", args[0])

    @patch('requests.post')
    def test_create_task(self, mock_post: MagicMock):
        """Test creating a task."""
        mock_response = load_asset('create_task_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_task(
            list_id="123456789",
            name="New Task",
            description="Task description",
            priority=1
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "New Task")
        self.assertEqual(result.description, "Task description")
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_create_task_with_invalid_priority(self, mock_post: MagicMock):
        """Test creating a task with invalid priority raises error."""
        client = ClickUpClient(token="test_token")

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.create_task(
                list_id="123456789",
                name="New Task",
                priority=5  # Invalid: must be 1-4
            )

        self.assertIn("Priority must be in range of 1-4", str(context.exception))

    @patch('requests.put')
    def test_update_task(self, mock_put: MagicMock):
        """Test updating a task."""
        mock_response = load_asset('get_task_000000000_response')
        mock_response['name'] = "Updated Task Name"
        mock_put.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.update_task(
            task_id="000000000",
            name="Updated Task Name",
            status="IN PROGRESS"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Updated Task Name")
        mock_put.assert_called_once()

    @patch('requests.delete')
    def test_delete_task(self, mock_delete: MagicMock):
        """Test deleting a task."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_task(task_id="000000000")

        self.assertTrue(result)
        mock_delete.assert_called_once()

    @patch('requests.post')
    def test_add_task_link(self, mock_post: MagicMock):
        """Test adding a task link."""
        mock_response_data = {
            "task": load_asset('get_task_000000000_response')
        }
        mock_post.return_value = mock_response_with_json(mock_response_data)

        client = ClickUpClient(token="test_token")
        result = client.add_task_link(task_id="task123", links_to="task456")

        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("task/task123/link/task456", args[0])


class TestClientComments(unittest.TestCase):
    """Tests for Comment-related methods."""

    @patch('requests.get')
    def test_get_task_comments(self, mock_get: MagicMock):
        """Test getting task comments."""
        mock_response = load_asset('get_comments_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_task_comments(task_id="000000000")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.comments), 2)
        self.assertEqual(result.comments[0].comment_text, "This is a test comment")
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_get_list_comments(self, mock_get: MagicMock):
        """Test getting list comments."""
        mock_response = load_asset('get_comments_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_list_comments(list_id="123456789")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.comments), 2)
        mock_get.assert_called_once()

    @patch('requests.post')
    def test_create_task_comment(self, mock_post: MagicMock):
        """Test creating a task comment."""
        mock_response = load_asset('create_comment_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_task_comment(
            task_id="000000000",
            comment_text="New comment created"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.comment_text, "New comment created")
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_create_task_comment_without_text(self, mock_post: MagicMock):
        """Test creating a task comment without text raises error."""
        client = ClickUpClient(token="test_token")

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.create_task_comment(task_id="000000000")

        self.assertIn("Either comment_text or comment must be supplied", str(context.exception))

    @patch('requests.put')
    def test_update_comment(self, mock_put: MagicMock):
        """Test updating a comment."""
        mock_put.return_value = mock_response_with_json({})

        client = ClickUpClient(token="test_token")
        result = client.update_comment(
            comment_id="11111111",
            comment_text="Updated comment"
        )

        self.assertTrue(result)
        mock_put.assert_called_once()

    @patch('requests.delete')
    def test_delete_comment(self, mock_delete: MagicMock):
        """Test deleting a comment."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_comment(comment_id="11111111")

        self.assertTrue(result)
        mock_delete.assert_called_once()


class TestClientTeams(unittest.TestCase):
    """Tests for Team-related methods."""

    @patch('requests.get')
    def test_get_teams(self, mock_get: MagicMock):
        """Test getting teams."""
        mock_response = load_asset('get_teams_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_teams()

        self.assertIsNotNone(result)
        self.assertEqual(len(result.teams), 1)
        self.assertEqual(result.teams[0].name, "Test Team")
        mock_get.assert_called_once()


class TestClientChecklists(unittest.TestCase):
    """Tests for Checklist-related methods."""

    @patch('requests.post')
    def test_create_checklist(self, mock_post: MagicMock):
        """Test creating a checklist."""
        mock_response = load_asset('create_checklist_response')
        mock_post.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.create_checklist(task_id="000000000", name="Test Checklist")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Test Checklist")
        mock_post.assert_called_once()

    @patch('requests.delete')
    def test_delete_checklist(self, mock_delete: MagicMock):
        """Test deleting a checklist."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_checklist(checklist_id="checklist123")

        self.assertTrue(result)
        mock_delete.assert_called_once()


class TestClientSpaces(unittest.TestCase):
    """Tests for Space-related methods."""

    @patch('requests.get')
    def test_get_space(self, mock_get: MagicMock):
        """Test getting a space."""
        mock_response = load_asset('get_space_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        result = client.get_space(space_id="789123456")

        self.assertIsNotNone(result)
        self.assertEqual(result.id, "789123456")
        self.assertEqual(result.name, "Test Space")
        mock_get.assert_called_once()

    @patch('requests.delete')
    def test_delete_space(self, mock_delete: MagicMock):
        """Test deleting a space."""
        mock_delete.return_value = mock_response_with_json({}, status_code=200)

        client = ClickUpClient(token="test_token")
        result = client.delete_space(space_id="789123456")

        self.assertTrue(result)
        mock_delete.assert_called_once()


class TestClientErrorHandling(unittest.TestCase):
    """Tests for error handling."""

    @patch('requests.get')
    def test_rate_limit_error_without_retry(self, mock_get: MagicMock):
        """Test rate limit error without retry enabled."""
        mock_get.return_value = mock_response_with_json(
            {"err": "Rate limit exceeded"},
            status_code=429
        )

        client = ClickUpClient(token="test_token", retry_rate_limited_requests=False)

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.get_task(task_id="000000000")

        self.assertEqual(context.exception.code, 429)
        self.assertIn("Rate limit exceeded", str(context.exception))

    @patch('requests.get')
    def test_client_error_400(self, mock_get: MagicMock):
        """Test handling of 400 error."""
        error_response = {"err": "Bad request"}
        mock_get.return_value = mock_response_with_json(
            error_response,
            status_code=400
        )

        client = ClickUpClient(token="test_token")

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.get_task(task_id="000000000")

        self.assertEqual(context.exception.code, 400)
        self.assertIn("Bad request", str(context.exception))

    @patch('requests.get')
    def test_client_error_404(self, mock_get: MagicMock):
        """Test handling of 404 error."""
        error_response = {"err": "Task not found"}
        mock_get.return_value = mock_response_with_json(
            error_response,
            status_code=404
        )

        client = ClickUpClient(token="test_token")

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.get_task(task_id="nonexistent")

        self.assertEqual(context.exception.code, 404)
        self.assertIn("Task not found", str(context.exception))

    @patch('requests.get')
    def test_invalid_order_by_parameter(self, mock_get: MagicMock):
        """Test invalid order_by parameter raises error."""
        client = ClickUpClient(token="test_token")

        with self.assertRaises(exceptions.ClickupClientError) as context:
            client.get_tasks(list_id="123456789", order_by="invalid")

        self.assertIn("Invalid order_by value", str(context.exception))


class TestClientRateLimiting(unittest.TestCase):
    """Tests for rate limiting functionality."""

    @patch('requests.get')
    def test_rate_limit_headers_parsing(self, mock_get: MagicMock):
        """Test that rate limit headers are parsed correctly."""
        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-reset": "1640000000"
        }
        mock_response = load_asset('get_task_000000000_response')
        mock_get.return_value = mock_response_with_json(mock_response, headers=headers)

        client = ClickUpClient(token="test_token")
        client.get_task(task_id="000000000")

        self.assertEqual(client.rate_limit_remaining, 50)
        self.assertEqual(client.rate_limit_reset, 1640000000.0)

    @patch('requests.get')
    def test_request_count_increments(self, mock_get: MagicMock):
        """Test that request count increments."""
        mock_response = load_asset('get_task_000000000_response')
        mock_get.return_value = mock_response_with_json(mock_response)

        client = ClickUpClient(token="test_token")
        self.assertEqual(client.request_count, 0)

        client.get_task(task_id="000000000")
        self.assertEqual(client.request_count, 1)

        client.get_task(task_id="000000000")
        self.assertEqual(client.request_count, 2)


class TestClientCustomHandlers(unittest.TestCase):
    """Tests for custom handler callbacks."""

    @patch('requests.get')
    def test_request_exception_handler_callback(self, mock_get: MagicMock):
        """Test that request exception handler is called."""
        # Create a mock response that will cause a JSON decode error
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.side_effect = Exception("JSON decode error")
        mock_response.headers = {
            "x-ratelimit-remaining": "100",
            "x-ratelimit-reset": "1609459200"
        }
        mock_get.return_value = mock_response

        exception_handler_called = []

        def exception_handler(e, response, client):
            exception_handler_called.append(True)

        client = ClickUpClient(
            token="test_token",
            request_exception_handler=exception_handler
        )

        with self.assertRaises(exceptions.ClickupClientError):
            client.get_task(task_id="000000000")

        # Handler should be called multiple times (once per retry)
        self.assertGreater(len(exception_handler_called), 0)


if __name__ == '__main__':
    unittest.main()
