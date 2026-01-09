import io
import json
import ntpath
import os
import urllib
import urllib.parse
from datetime import datetime
from time import sleep
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Union

import requests
from requests import JSONDecodeError

from clickup_sdk import exceptions
from clickup_sdk import models
from clickup_sdk.helpers import formatting
from clickup_sdk.helpers.timefuncs import fuzzy_time_to_unix
from clickup_sdk.models import CustomFieldFilter, CustomFieldFilterOperator

API_URL = "https://api.clickup.com/api/v2/"


class ClickUpClient:
    def __init__(
            self,
            token: str,
            api_url: str = API_URL,
            retry_rate_limited_requests: bool = False,
            rate_limit_buffer_wait_time: int = 5,
            start_rate_limit_remaining: int = 100,
            start_rate_limit_reset: float = datetime.now().timestamp(),
            request_exception_handler: Optional[Callable[[Exception, requests.Response, Any], None]] = None,
            sleep_on_rate_limit_handler: Optional[Callable[[float, Any], None]] = None,
    ) -> None:
        self.api_url = api_url
        self.token = token
        self.request_count = 0
        self.rate_limit_remaining = start_rate_limit_remaining
        self.rate_limit_reset = start_rate_limit_reset
        self.rate_limit_buffer_wait_time = rate_limit_buffer_wait_time
        self.retry_rate_limited_requests = retry_rate_limited_requests
        self.request_exception_handler = request_exception_handler
        self.sleep_on_rate_limit_handler = sleep_on_rate_limit_handler

    def __parse_response_rate_limit_headers(self, response: requests.Response) -> None:
        """Parses rate limit headers from the response and updates instance variables.

        Args:
            response (requests.Response): The response from the API

        Returns:
            None
        """
        self.rate_limit_remaining = int(response.headers.get("x-ratelimit-remaining", 0))
        self.rate_limit_reset = float(response.headers.get("x-ratelimit-reset", 0))

    def __check_rate_limit(self) -> None:
        """Checks if the rate limit has been reached and sleeps if necessary.

        Returns:
            None
        """
        if self.rate_limit_remaining <= 1:
            resume_time = datetime.fromtimestamp(
                self.rate_limit_reset + self.rate_limit_buffer_wait_time
            )
            seconds = (resume_time - datetime.now()).total_seconds()
            if self.sleep_on_rate_limit_handler is not None:
                self.sleep_on_rate_limit_handler(seconds, self)
            sleep(seconds)

    # Generates headers for use in GET, POST, DELETE, PUT requests

    def __headers(self, file_upload: bool = False) -> Dict[str, str]:
        """Internal method to generate headers for HTTP requests. Generates headers for use in GET, POST, DELETE and PUT requests.

        Args:
            file_upload (bool, optional): Whether this is a file upload request. Defaults to False.

        Returns:
            Dict[str, str]: Returns headers for HTTP requests
        """

        return (
            {
                "Authorization": self.token
            }
            if file_upload
            else {
                "Authorization": self.token,
                "Content-Type": "application/json",
            }
        )

    def __request(
            self, method: str, uri: str, data: Optional[dict] = None, upload_files: Optional[Dict[str, Any]] = None,
            file_upload: bool = False) -> Union[Dict[str, Any], int, None]:
        """Performs an HTTP request to the ClickUp API

        Args:
            method (str): HTTP method (GET, POST, PUT, DELETE)
            uri (str): API endpoint URI (relative to api_url)
            data (str, optional): JSON string for POST/PUT requests
            upload_files (dict, optional): Files to upload for POST requests
            file_upload (bool, optional): Whether this is a file upload request

        Returns:
            Union[Dict[str, Any], int, None]: Response data from the API, status code for DELETE requests, or None if the request fails
        """
        path = formatting.url_join(self.api_url, uri)
        max_json_decode_retries = 3
        max_rate_limit_retries = 10

        for attempt in range(max(max_json_decode_retries, max_rate_limit_retries) + 1):
            self.__check_rate_limit()

            # Prepare request arguments
            request_kwargs = {
                "headers": self.__headers(file_upload if upload_files else False)
            }
            if method in ["POST", "PUT"] and data:
                request_kwargs["json"] = data
            if method == "POST" and upload_files:
                request_kwargs["files"] = upload_files

            # Make the request
            response = getattr(requests, method.lower())(path, **request_kwargs)
            self.request_count += 1

            # Parse response
            try:
                response_json = response.json()
            except JSONDecodeError as e:
                if self.request_exception_handler is not None:
                    self.request_exception_handler(e, response, self)
                if attempt >= max_json_decode_retries:
                    raise exceptions.ClickupClientError(
                        f"Failed to decode JSON response after {max_json_decode_retries} retries", response.status_code
                    )
                continue  # Retry

            self.__parse_response_rate_limit_headers(response)

            # Handle rate limiting
            if response.status_code == 429:
                if self.retry_rate_limited_requests:
                    if attempt >= max_rate_limit_retries:
                        raise exceptions.ClickupClientError(
                            f"Rate limit retry exceeded after {max_rate_limit_retries} attempts", response.status_code
                        )
                    continue  # Retry

                error_data = {
                    'response': response.text,
                    'headers': dict(response.headers),
                    'uri': uri
                }
                if data:
                    error_data['data'] = data

                raise exceptions.ClickupClientError(
                    "Rate limit exceeded", response.status_code, data=error_data
                )

            # Handle errors
            if response.status_code >= 400:
                error_data = {
                    'response': response.text,
                    'headers': dict(response.headers),
                    'uri': uri
                }
                if data:
                    error_data['data'] = data

                error = response_json.get("err", json.dumps(response_json))
                raise exceptions.ClickupClientError(
                    error, response.status_code, data=error_data
                )

            # Return appropriate response
            if response.ok:
                # DELETE requests return status code instead of JSON
                if method == "DELETE":
                    return response.status_code
                return response_json

        return None

    def __get_request(self, uri: str) -> Union[Dict[str, Any], None]:
        return self.__request("GET", uri)

    def __post_request(
            self,
            uri: str,
            data: Optional[dict] = None,
            upload_files: Optional[Dict[str, Any]] = None,
            file_upload: bool = False
    ) -> Union[Dict[str, Any], None]:
        return self.__request("POST", uri, data, upload_files, file_upload)

    def __put_request(self, uri: str, data: Optional[dict]) -> Union[Dict[str, Any], None]:
        return self.__request("PUT", uri, data)

    def __delete_request(self, uri: str) -> Union[Dict[str, Any], int, None]:
        return self.__request("DELETE", uri)

    # Lists
    def get_list(self, list_id: str) -> models.SingleList:
        uri = f"list/{list_id}"
        fetched_list = self.__get_request(uri)
        return models.SingleList.build_list(fetched_list)

    def get_folderless_lists(self, space_id: str) -> models.AllLists:
        uri = f"space/{space_id}/list"
        fetched_lists = self.__get_request(uri)
        return models.AllLists.build_lists(fetched_lists)

    def get_lists(self, folder_id: str) -> models.AllLists:
        uri = f"folder/{folder_id}"
        fetched_lists = self.__get_request(uri)
        return models.AllLists.build_lists(fetched_lists)

    def create_list(
            self,
            folder_id: str,
            name: str,
            content: str,
            due_date: str,
            priority: int,
            status: str,
    ) -> Optional[models.SingleList]:
        data = {
            "name": name,
            "content": content,
            "due_date": due_date,
            "status": status,
        }
        uri = f"folder/{folder_id}/list"
        created_list = self.__post_request(uri, data)
        if created_list:
            return models.SingleList.build_list(created_list)

    def create_folderless_list(
            self,
            space_id: str,
            name: str,
            content: str = None,
            due_date: str = None,
            priority: int = None,
            assignee: str = None,
            status: str = None,
    ) -> Optional[models.SingleList]:
        arguments = {
            "name": name,
            "content": content,
            "due_date": due_date,
            "priority": priority,
            "assignee": assignee,
            "status": status
        }
        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"space/{space_id}/list"
        created_list = self.__post_request(uri, final_dict)
        if created_list:
            return models.SingleList.build_list(created_list)

    # //TODO Add unit tests
    def update_list(
            self,
            list_id: str,
            name: str = None,
            content: str = None,
            due_date: str = None,
            due_date_time: bool = None,
            priority: int = None,
            assignee: str = None,
            unset_status: bool = None,
    ) -> Optional[models.SingleList]:

        if priority and priority not in range(1, 5):
            raise exceptions.ClickupClientError(
                "Priority must be in range of 1-4.", "Priority out of range"
            )

        if due_date:
            due_date = fuzzy_time_to_unix(due_date)

        arguments = {
            "name": name,
            "content": content,
            "due_date": due_date,
            "due_date_time": due_date_time,
            "priority": priority,
            "assignee": assignee,
            "unset_status": unset_status
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"list/{list_id}"
        updated_list = self.__put_request(uri, final_dict)
        if updated_list:
            return models.SingleList.build_list(updated_list)

    def delete_list(self, list_id: str) -> bool:

        """Deletes a list via a given list id.

        Returns:
            bool: Returns True if the list was successfully deleted.
        """
        uri = f"list/{list_id}"
        self.__delete_request(uri)
        return True

    def add_task_to_list(self, task_id: str, list_id: str) -> bool:
        uri = f"list/{list_id}/task/{task_id}"
        self.__post_request(uri, None)
        return True

    def remove_task_from_list(self, task_id: str, list_id: str) -> bool:
        uri = f"list/{list_id}/task/{task_id}"
        self.__delete_request(uri)
        return True

    # Folders

    def get_folder(self, folder_id: str) -> Optional[models.Folder]:
        uri = f"folder/{folder_id}"
        fetched_folder = self.__get_request(uri)
        if fetched_folder:
            return models.Folder.build_folder(fetched_folder)

    def get_folders(self, space_id: str) -> Optional[models.Folders]:
        uri = f"space/{space_id}/folder"
        fetched_folders = self.__get_request(uri)
        if fetched_folders:
            return models.Folders.build_folders(fetched_folders)

    def create_folder(self, space_id: str, name: str) -> Optional[models.Folder]:
        data = {
            "name": name
        }
        uri = f"space/{space_id}/folder"
        created_folder = self.__post_request(uri, data)
        if created_folder:
            return models.Folder.build_folder(created_folder)

    def update_folder(self, folder_id: str, name: str) -> Optional[models.Folder]:
        data = {
            "name": name
        }
        uri = f"folder/{folder_id}"
        updated_folder = self.__put_request(uri, data)
        if updated_folder:
            return models.Folder.build_folder(updated_folder)

    def delete_folder(self, folder_id: str) -> bool:
        uri = f"folder/{folder_id}"
        self.__delete_request(uri)
        return True

    def upload_attachment(
            self,
            task_id: str,
            file: io.BytesIO | BinaryIO,
            file_type: Optional[str] = None,
    ) -> Optional[models.Attachment]:
        """Uploads an attachment to a ClickUp task.

        Args:
            :task_id (str): The ID of the task to upload to.
            :file_path (str): The filepath of the file to upload.

        Returns:
            :Attachment: Returns an attachment object.
        """
        files = [("attachment", (file.name, file.read(), file_type))]
        data = {
            "filename": ntpath.basename(file.name),
        }
        uri = f"task/{task_id}/attachment"
        uploaded_attachment = self.__post_request(uri, data, files, True)

        if uploaded_attachment:
            final_attachment = models.Attachment.build_attachment(uploaded_attachment)
            return final_attachment

    def get_task(
            self,
            task_id: str,
            include_subtasks: bool = False,
    ) -> models.Task:
        """Fetches a single ClickUp task item and returns a Task object.

        Args:
            :task_id (str): The ID of the task to return.

        Returns:
            :Task: Returns an object of type Task.
        """
        get_params = {}
        if include_subtasks:
            get_params["include_subtasks"] = 'true'

        get_part = ''
        if len(get_params) > 0:
            get_part = urllib.parse.urlencode(get_params)
            get_part = f"?{get_part}"

        uri = f"task/{task_id}{get_part}"
        fetched_task = self.__get_request(uri)
        return models.Task(**fetched_task)

    def get_team_tasks(
            self,
            team_Id: str,
            page: int = 0,
            order_by: str = "created",
            reverse: bool = False,
            subtasks: bool = False,
            space_ids: List[str] = None,
            project_ids: List[str] = None,
            list_ids: List[str] = None,
            statuses: List[str] = None,
            include_closed: bool = False,
            assignees: List[str] = None,
            tags: List[str] = None,
            due_date_gt: str = None,
            due_date_lt: str = None,
            date_created_gt: str = None,
            date_created_lt: str = None,
            date_updated_gt: str = None,
            date_updated_lt: str = None,
    ) -> Optional[models.Tasks]:
        """Gets filtered tasks for a team.

        Args:
            :team_Id (str): The id of the team to get tasks for.
            :page (int, optional): The starting page number. Defaults to 0.
            :order_by (str, optional):  Order by field, defaults to "created". Options: id, created, updated, due_date.
            :reverse (bool, optional): [description]. Defaults to False.
            :subtasks (bool, optional): [description]. Defaults to False.
            :space_ids (List[str], optional): [description]. Defaults to None.
            :project_ids (List[str], optional): [description]. Defaults to None.
            :list_ids (List[str], optional): [description]. Defaults to None.
            :statuses (List[str], optional): [description]. Defaults to None.
            :include_closed (bool, optional): [description]. Defaults to False.
            :assignees (List[str], optional): [description]. Defaults to None.
            :tags (List[str], optional): [description]. Defaults to None.
            :due_date_gt (str, optional): [description]. Defaults to None.
            :due_date_lt (str, optional): [description]. Defaults to None.
            :date_created_gt (str, optional): [description]. Defaults to None.
            :date_created_lt (str, optional): [description]. Defaults to None.
            :date_updated_gt (str, optional): [description]. Defaults to None.
            :date_updated_lt (str, optional): [description]. Defaults to None.

        Raises:
            exceptions.ClickupClientError: [description]

        Returns:
            models.Tasks: [description]
        """
        if order_by not in ["id", "created", "updated", "due_date"]:
            raise exceptions.ClickupClientError(
                "Options are: id, created, updated, due_date", "Invalid order_by value"
            )

        supplied_values = [
            f"page={page}",
            f"order_by={order_by}",
            f"reverse={str(reverse).lower()}",
        ]

        if statuses:
            supplied_values.append(
                f"{urllib.parse.quote_plus('statuses[]')}={','.join(statuses)}"
            )
        if assignees:
            supplied_values.append(
                f"{urllib.parse.quote_plus('assignees[]')}={','.join(assignees)}"
            )
        if due_date_gt:
            supplied_values.append(f"due_date_gt={fuzzy_time_to_unix(due_date_gt)}")
        if due_date_lt:
            supplied_values.append(f"due_date_lt={fuzzy_time_to_unix(due_date_lt)}")
        if space_ids:
            supplied_values.append(
                f"{urllib.parse.quote_plus('space_ids[]')}={','.join(space_ids)}"
            )
        if project_ids:
            supplied_values.append(
                f"{urllib.parse.quote_plus('project_ids[]')}={','.join(project_ids)}"
            )
        if list_ids:
            supplied_values.append(
                f"{urllib.parse.quote_plus('list_ids[]')}={','.join(list_ids)}"
            )
        if date_created_gt:
            supplied_values.append(f"date_created_gt={date_created_gt}")
        if date_created_lt:
            supplied_values.append(f"date_created_lt={date_created_lt}")
        if date_updated_gt:
            supplied_values.append(f"date_updated_gt={date_updated_gt}")
        if date_updated_lt:
            supplied_values.append(f"date_updated_lt={date_updated_lt}")
        if subtasks:
            supplied_values.append(f"subtasks=true")

        joined_url = f"task?{'&'.join(supplied_values)}"
        uri = f"team/{team_Id}/{joined_url}"
        fetched_tasks = self.__get_request(uri)
        if fetched_tasks:
            return models.Tasks.build_tasks(fetched_tasks)

    def get_tasks(
            self,
            list_id: str,
            archived: bool = False,
            page: int = 0,
            order_by: str = "created",
            reverse: bool = False,
            subtasks: bool = False,
            statuses: List[str] = None,
            include_closed: bool = False,
            assignees: List[str] = None,
            due_date_gt: str = None,
            due_date_lt: str = None,
            date_created_gt: str = None,
            date_created_lt: str = None,
            date_updated_gt: str = None,
            date_updated_lt: str = None,
            custom_fields: List[models.CustomFieldFilter] = None,
            custom_field: models.CustomFieldFilter = None,
    ) -> Optional[models.Tasks]:

        """The maximum number of tasks returned in this response is 100. When you are paging this request, you should check list limit
        against the length of each response to determine if you are on the last page.

        Args:
            :list_id (str):
                The ID of the list to retrieve tasks from.
            :archived (bool, optional):
                Include archived tasks in the retrieved tasks. Defaults to False.
            :page (int, optional):
                Page to fetch (starts at 0). Defaults to 0.
            :order_by (str, optional):
                Order by field, defaults to "created". Options: id, created, updated, due_date.
            :reverse (bool, optional):
                Reverse the order of the returned tasks. Defaults to False.
            :subtasks (bool, optional):
                Include archived tasks in the retrieved tasks. Defaults to False.
            :statuses (List[str], optional):
                Only retrieve tasks with the supplied status. Defaults to None.
            :include_closed (bool, optional):
                Include closed tasks in the query. Defaults to False.
            :assignees (List[str], optional):
                Retrieve tasks for specific assignees only. Defaults to None.
            :due_date_gt (str, optional):
                Retrieve tasks with a due date greater than the supplied date. Defaults to None.
            :due_date_lt (str, optional): Retrieve tasks with a due date less than the supplied date. Defaults to None.
            :date_created_gt (str, optional):
                Retrieve tasks with a creation date greater than the supplied date. Defaults to None.
            :date_created_lt (str, optional):
                Retrieve tasks with a creation date less than the supplied date. Defaults to None.
            :date_updated_gt (str, optional):
                Retrieve tasks where the last update date is greater than the supplied date. Defaults to None.
            :date_updated_lt (str, optional): Retrieve tasks where the last update date is greater than the supplied date. Defaults to None.

        Raises:
            :exceptions.ClickupClientError: [description]

        Returns:
            :models.Tasks: Returns a list of item Task.
        """

        if order_by not in ["id", "created", "updated", "due_date"]:
            raise exceptions.ClickupClientError(
                "Options are: id, created, updated, due_date", "Invalid order_by value"
            )

        supplied_values = [
            f"archived={str(archived).lower()}",
            f"page={page}",
            f"order_by={order_by}",
            f"reverse={str(reverse).lower()}",
            f"include_closed={str(include_closed).lower()}",
        ]

        if statuses:
            supplied_values.append(
                f"{urllib.parse.quote_plus('statuses[]')}={','.join(statuses)}"
            )
        if assignees:
            supplied_values.append(
                f"{urllib.parse.quote_plus('assignees[]')}={','.join(assignees)}"
            )
        if due_date_gt:
            supplied_values.append(f"due_date_gt={fuzzy_time_to_unix(due_date_gt)}")
        if due_date_lt:
            supplied_values.append(f"due_date_lt={fuzzy_time_to_unix(due_date_lt)}")
        if date_created_gt:
            supplied_values.append(f"date_created_gt={date_created_gt}")
        if date_created_lt:
            supplied_values.append(f"date_created_lt={date_created_lt}")
        if date_updated_gt:
            supplied_values.append(f"date_updated_gt={date_updated_gt}")
        if date_updated_lt:
            supplied_values.append(f"date_updated_lt={date_updated_lt}")
        if subtasks:
            supplied_values.append(f"subtasks=true")
        if custom_field:
            supplied_values.append(f"custom_field={custom_field.model_dump_json()}")
        if custom_fields:
            custom_fields_json = json.dumps([cf.model_dump(mode='json') for cf in custom_fields])
            supplied_values.append(f"custom_fields={custom_fields_json}")

        joined_url = f"task?{'&'.join(supplied_values)}"
        uri = f"list/{list_id}/{joined_url}"
        fetched_tasks = self.__get_request(uri)
        if fetched_tasks:
            return models.Tasks.build_tasks(fetched_tasks)

    def create_task(
            self,
            list_id: str,
            name: str,
            description: Optional[str] = None,
            priority: Optional[int] = None,
            assignees: Optional[List[str]] = None,
            tags: Optional[List[str]] = None,
            status: Optional[str] = None,
            due_date: Optional[str] = None,
            start_date: Optional[str] = None,
            parent: Optional[str] = None,
            notify_all: bool = True,
            custom_fields: Optional[List[models.CreateTaskCustomField]] = None,
    ) -> Optional[models.Task]:

        """[summary]

        Args:
            :list_id (str): [description]
            :name (str): [description]
            :description (str, optional): [description]. Defaults to None.
            :priority (int, optional): [description]. Defaults to None.
            :assignees ([type], optional): [description]. Defaults to None.
            :tags ([type], optional): [description]. Defaults to None.
            :status (str, optional): [description]. Defaults to None.
            :due_date (str, optional): [description]. Defaults to None.
            :start_date (str, optional): [description]. Defaults to None.
            :notify_all (bool, optional): [description]. Defaults to True.

        Raises:
            :exceptions.ClickupClientError: [description]

        Returns:
            :models.Task: [description]
        """
        if priority and priority not in range(1, 5):
            raise exceptions.ClickupClientError(
                "Priority must be in range of 1-4.", "Priority out of range"
            )
        if due_date:
            due_date = fuzzy_time_to_unix(due_date)
        if notify_all:
            notify_all = str(notify_all).lower()
        if custom_fields:
            custom_fields = [cf.model_dump(mode='json') for cf in custom_fields]

        arguments = {
            "name": name,
            "description": description,
            "priority": priority,
            "assignees": assignees,
            "tags": tags,
            "status": status,
            "due_date": due_date,
            "start_date": start_date,
            "parent": parent,
            "notify_all": notify_all,
            "custom_fields": custom_fields
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"list/{list_id}/task"
        created_task = self.__post_request(uri, final_dict)

        if created_task:
            return models.Task(**created_task)

    def update_task(
            self,
            task_id: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            status: Optional[str] = None,
            priority: Optional[int] = None,
            time_estimate: Optional[int] = None,
            archived: Optional[bool] = None,
            add_assignees: Optional[List[str]] = None,
            remove_assignees: Optional[List[int]] = None,
            add_watchers: Optional[List[str]] = None,
            remove_watchers: Optional[List[int]] = None,
    ) -> Optional[models.Task]:

        """[summary]

        Args:
            :task_id ([type]): The ID of the ClickUp task to update.
            :name (str, optional): Sting value to update the task name to. Defaults to None.
            :description (str, optional): Sting value to update the task description to. Defaults to None.
            :status (str, optional): String value of the tasks status. Defaults to None.
            :priority (int, optional): Priority of the task. Range 1-4. Defaults to None.
            :time_estimate (int, optional): Time estimate of the task. Defaults to None.
            :archived (bool, optional): Whether the task should be archived or not. Defaults to None.
            :add_assignees (List[str], optional): List of assignee IDs to add to the task. Defaults to None.
            :remove_assignees (List[int], optional): List of assignee IDs to remove from the task. Defaults to None.
            :add_watchers (List[str], optional): List of watcher IDs to add to the task. Defaults to None.
            :remove_watchers (List[int], optional): List of watcher IDs to remove from the task. Defaults to None.

        Raises:
            :exceptions.ClickupClientError: Raises "Priority out of range" exception for invalid priority range.

        Returns:
            :models.Task: Returns an object of type Task.
        """
        if priority and priority not in range(1, 5):
            raise exceptions.ClickupClientError(
                "Priority must be in range of 1-4.", "Priority out of range"
            )

        arguments = {
            "name": name,
            "description": description,
            "status": status,
            "priority": priority,
            "time_estimate": time_estimate,
            "archived": archived
        }

        if add_assignees and remove_assignees:
            arguments.update(
                {
                    "assignees": {
                        "add": add_assignees,
                        "rem": remove_assignees
                    }
                }
            )
        elif add_assignees:
            arguments.update(
                {
                    "assignees": {
                        "add": add_assignees
                    }
                }
            )
        elif remove_assignees:
            arguments.update(
                {
                    "assignees": {
                        "rem": remove_assignees
                    }
                }
            )

        if add_watchers and remove_watchers:
            arguments.update(
                {
                    "watchers": {
                        "add": add_watchers,
                        "rem": remove_watchers
                    }
                }
            )
        elif add_watchers:
            arguments.update(
                {
                    "watchers": {
                        "add": add_watchers
                    }
                }
            )
        elif remove_watchers:
            arguments.update(
                {
                    "watchers": {
                        "rem": remove_watchers
                    }
                }
            )

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"task/{task_id}"
        updated_task = self.__put_request(uri, final_dict)
        if updated_task:
            return models.Task(**updated_task)

    def delete_task(self, task_id: str) -> bool:
        uri = f"task/{task_id}"
        self.__delete_request(uri)
        return True

    def add_task_link(self, task_id: str, links_to: str) -> bool:
        uri = f"task/{task_id}/link/{links_to}"

        # it return {"task": { #task object here# }}
        self.__post_request(uri, None)

        return True

    # Comments
    def get_task_comments(self, task_id: str) -> Optional[models.Comments]:
        uri = f"task/{task_id}/comment"
        fetched_comments = self.__get_request(uri)
        final_comments = models.Comments.build_comments(fetched_comments)
        if final_comments:
            return final_comments

    def get_list_comments(self, list_id: str) -> Optional[models.Comments]:
        uri = f"list/{list_id}/comment"
        fetched_comments = self.__get_request(uri)
        final_comments = models.Comments.build_comments(fetched_comments)
        if final_comments:
            return final_comments

    def get_chat_comments(
            self,
            view_id: str,
            start_from: Optional[datetime] = None,
            start_from_id: Optional[int] = None,
    ) -> Optional[models.Comments]:
        query = {}
        if start_from:
            query["start"] = start_from.timestamp()
        if start_from_id:
            query["start_id"] = start_from_id

        query_string = ""
        if len(query) > 0:
            query_string = "?" + urllib.parse.urlencode(query)

        uri = f"view/{view_id}/comment{query_string}"
        fetched_comments = self.__get_request(uri)
        final_comments = models.Comments.build_comments(fetched_comments)
        if final_comments:
            return final_comments

    def get_threaded_comments(self, comment_id: str) -> Optional[models.Comments]:
        uri = f"comment/{comment_id}/reply"
        fetched_comments = self.__get_request(uri)
        final_comments = models.Comments.build_comments(fetched_comments)
        if final_comments:
            return final_comments

    def create_threaded_comment(
            self,
            comment_id: int,
            comment_text: Optional[str] = None,
            comment: Optional[list[dict]] = None,
            assignee: Optional[int] = None,
            group_assignee: Optional[int] = None,
            notify_all: Optional[bool] = True,
    ) -> Optional[models.Comment]:
        if comment_text is None and comment is None:
            raise exceptions.ClickupClientError(
                "Either comment_text or comment must be supplied.", "No comment supplied"
            )

        data = {
            "notify_all": notify_all
        }
        if comment_text:
            data["comment_text"] = comment_text
        if comment:
            data["comment"] = comment
        if assignee:
            data["assignee"] = assignee
        if group_assignee:
            data["group_assignee"] = group_assignee

        uri = f"comment/{comment_id}/reply"
        created_comment = self.__post_request(uri, data)

        final_comment = models.Comment.build_comment(created_comment)
        if final_comment:
            return final_comment

    def update_comment(
            self,
            comment_id: str,
            comment_text: Optional[str] = None,
            comment: Optional[list[dict]] = None,
            assignee: Optional[str] = None,
            resolved: Optional[bool] = None,
    ) -> bool:
        arguments = {
            "comment_text": comment_text,
            "comment": comment,
            "assignee": assignee,
            "resolved": resolved
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"comment/{comment_id}"
        self.__put_request(uri, final_dict)
        return True

    def delete_comment(self, comment_id: str) -> bool:
        uri = f"comment/{comment_id}"
        self.__delete_request(uri)
        return True

    def create_task_comment(
            self,
            task_id: str,
            comment_text: Optional[str] = None,
            comment: Optional[list[dict]] = None,
            assignee: str = None,
            notify_all: bool = True,
    ) -> Optional[models.Comment]:
        if comment_text is None and comment is None:
            raise exceptions.ClickupClientError(
                "Either comment_text or comment must be supplied.", "No comment supplied"
            )

        data = {
            "notify_all": notify_all
        }
        if comment_text:
            data["comment_text"] = comment_text
        if comment:
            data["comment"] = comment

        uri = f"task/{task_id}/comment"
        created_comment = self.__post_request(uri, data)

        final_comment = models.Comment.build_comment(created_comment)
        if final_comment:
            return final_comment

    def create_chat_comment(
            self,
            view_id: str,
            comment_text: str,
            notify_all: bool = True,
    ) -> Optional[models.Comment]:
        arguments = {
            "comment_text": comment_text,
            "notify_all": notify_all
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"view/{view_id}/comment"
        created_comment = self.__post_request(uri, final_dict)

        final_comment = models.Comment.build_comment(created_comment)
        if final_comment:
            return final_comment

    # Teams
    def get_teams(self) -> Optional[models.Teams]:
        uri = "team"
        fetched_teams = self.__get_request(uri)
        final_teams = models.Teams.build_teams(fetched_teams)
        if final_teams:
            return final_teams

    # Checklists
    def create_checklist(self, task_id: str, name: str) -> Optional[models.Checklist]:
        data = {
            "name": name
        }
        uri = f"task/{task_id}/checklist"
        created_checklist = self.__post_request(uri, data)
        return models.Checklists.build_checklist(created_checklist)

    def create_checklist_item(
            self, checklist_id: str, name: str, assignee: str = None
    ) -> Optional[models.Checklist]:
        data = {
            "name": name,
            "assignee": assignee
        } if assignee else {
            "name": name
        }
        uri = f"checklist/{checklist_id}/checklist_item"
        created_checklist = self.__post_request(uri, data)
        return models.Checklists.build_checklist(created_checklist)

    def update_checklist(
            self, checklist_id: str, name: str = None, position: int = None
    ) -> Optional[models.Checklist]:
        if not name and not position:
            return

        data = {}
        if name:
            data["name"] = name
        if position:
            data["position"] = position

        uri = f"checklist/{checklist_id}"
        updated_checklist = self.__put_request(uri, data)
        if updated_checklist:
            return models.Checklists.build_checklist(updated_checklist)

    def delete_checklist(self, checklist_id: str) -> bool:
        uri = f"checklist/{checklist_id}"
        self.__delete_request(uri)
        return True

    def delete_checklist_item(self, checklist_id: str, checklist_item_id: str) -> bool:
        uri = f"checklist/{checklist_id}/checklist_item/{checklist_item_id}"
        self.__delete_request(uri)
        return True

    def update_checklist_item(
            self,
            checklist_id: str,
            checklist_item_id: str,
            name: str = None,
            resolved: bool = None,
            parent: str = None,
    ) -> Optional[models.Checklist]:
        arguments = {
            "name": name,
            "resolved": resolved,
            "parent": parent
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"checklist/{checklist_id}/checklist_item/{checklist_item_id}"
        item_update = self.__put_request(uri, final_dict)

        final_update = models.Checklists.build_checklist(item_update)
        if final_update:
            return final_update

    # Members
    def get_task_members(self, task_id: str) -> Optional[models.Members]:
        uri = f"task/{task_id}/member"
        task_members = self.__get_request(uri)
        return models.Members.build_members(task_members)

    def get_list_members(self, list_id: str) -> Optional[models.Members]:
        uri = f"list/{list_id}/member"
        task_members = self.__get_request(uri)
        return models.Members.build_members(task_members)

    # Goals
    def create_goal(
            self,
            team_id,
            name: str,
            due_date: str = None,
            description: str = None,
            multiple_owners: bool = True,
            owners: List[int] = None,
            color: str = None,
    ) -> Optional[models.Goal]:
        arguments = {
            "name": name,
            "due_date": due_date,
            "description": description,
            "multiple_owners": multiple_owners,
            "color": color
        }

        if multiple_owners and owners:
            arguments.update(
                {
                    "owners": owners
                }
            )

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"team/{team_id}/goal"
        created_goal = self.__post_request(uri, final_dict)
        if created_goal:
            return models.Goals.build_goals(created_goal)

    def update_goal(
            self,
            goal_id: str,
            name: str = None,
            due_date: str = None,
            description: str = None,
            rem_owners: List[str] = None,
            add_owners: List[str] = None,
            color: str = None,
    ) -> Optional[models.Goal]:
        arguments = {
            "name": name,
            "due_date": due_date,
            "description": description,
            "rem_owners": rem_owners,
            "add_owners": add_owners,
            "color": color
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        uri = f"goal/{goal_id}"
        updated_goal = self.__put_request(uri, final_dict)
        if updated_goal:
            return models.Goals.build_goals(updated_goal)

    def delete_goal(self, goal_id: str) -> bool:
        uri = f"goal/{goal_id}"
        self.__delete_request(uri)
        return True

    def get_goal(self, goal_id: str) -> Optional[models.Goal]:
        uri = f"goal/{goal_id}"
        fetched_goal = self.__get_request(uri)
        final_goal = models.Goals.build_goals(fetched_goal)
        if final_goal:
            return final_goal

    def get_goals(self, team_id: str, include_completed: bool = False) -> Optional[models.Goals]:
        query_param = "?include_completed=true" if include_completed else "?include_completed=false"
        uri = f"team/{team_id}/goal{query_param}"
        fetched_goals = self.__get_request(uri)
        final_goals = models.GoalsList.build_goals(fetched_goals)
        if final_goals:
            return final_goals

    # Tags
    def get_space_tags(self, space_id: str) -> Optional[models.Tags]:
        uri = f"space/{space_id}/tag"
        fetched_tags = self.__get_request(uri)
        final_tags = models.Tags.build_tags(fetched_tags)
        if final_tags:
            return final_tags

    def create_space_tag(self, space_id, name: str) -> Optional[models.Tag]:
        arguments = {
            "name": name
        }

        final_dict = {k: v for k, v in arguments.items() if v is not None}
        final_tag = {
            "tag": final_dict
        }

        uri = f"space/{space_id}/tag"
        created_tag = self.__post_request(uri, final_tag)
        if created_tag:
            return models.Tag.build_tag(created_tag)
        return None

    def tag_task(self, task_id: str, tag_name: str) -> bool:
        uri = f"task/{task_id}/tag/{tag_name}"
        self.__post_request(uri, None)
        return True

    def untag_task(self, task_id: str, tag_name: str) -> bool:
        uri = f"task/{task_id}/tag/{tag_name}"
        self.__delete_request(uri)
        return True

    # Spaces
    def create_space(
            self, team_id: str, name: str, features: models.Features
    ) -> Optional[models.Space]:
        final_dict = {
            "name": name,
            "multiple_assignees": features.multiple_assignees,
            "features": features.all_features,
        }

        uri = f"team/{team_id}/space"
        created_space = self.__post_request(uri, final_dict)
        if created_space:
            return models.Space.build_space(created_space)

    def delete_space(self, space_id: str) -> bool:
        uri = f"space/{space_id}"
        self.__delete_request(uri)
        return True

    def get_space(self, space_id: str) -> Optional[models.Space]:
        uri = f"space/{space_id}"
        fetched_space = self.__get_request(uri)
        if fetched_space:
            return models.Space.build_space(fetched_space)

    def get_spaces(self, team_id: str, archived: bool = False) -> Optional[models.Spaces]:
        query_param = "?archived=true" if archived else "?archived=false"
        uri = f"team/{team_id}/space{query_param}"
        fetched_spaces = self.__get_request(uri)
        if fetched_spaces:
            return models.Spaces.build_spaces(fetched_spaces)

    # Shared Hierarchy
    def get_shared_hierarchy(self, team_id: str) -> Optional[models.SharedHierarchy]:
        uri = f"team/{team_id}/shared"
        fetched_hierarchy = self.__get_request(uri)
        if fetched_hierarchy:
            return models.SharedHierarchy.build_shared(fetched_hierarchy)

    # Time Tracking
    def get_time_entries_in_range(
            self,
            team_id: str,
            start_date: str = None,
            end_date: str = None,
            assignees: List[str] = None,
    ) -> Optional[models.TimeTrackingData]:
        startdate = "start_date="
        enddate = "end_date="
        assignees_temp = "assignee="

        if start_date:
            startdate = f"start_date={fuzzy_time_to_unix(start_date)}"
        if end_date:
            enddate = f"end_date={fuzzy_time_to_unix(end_date)}"
        if assignees:
            if len(assignees) > 1:
                assignees_temp = f'assignee={",".join(assignees)}'
            if len(assignees) == 1:
                assignees_temp = f"assignee={assignees[0]}"

        joined_url = f"time_entries?{startdate}&{enddate}&{assignees_temp}"
        uri = f"team/{team_id}/{joined_url}"
        fetched_time_data = self.__get_request(uri)

        if fetched_time_data:
            return models.TimeTrackingDataList.build_data(fetched_time_data)

    def get_single_time_entry(
            self, team_id: str, timer_id: str
    ) -> Optional[models.TimeTrackingData]:
        uri = f"team/{team_id}/time_entries/{timer_id}"
        fetched_time_data = self.__get_request(uri)
        if fetched_time_data:
            return models.TimeTrackingDataSingle.build_data(fetched_time_data)

    def start_timer(self, team_id: str, timer_id: str) -> Optional[models.TimeTrackingData]:
        uri = f"team/{team_id}/time_entries/start/{timer_id}"
        fetched_time_data = self.__post_request(uri, None)
        if fetched_time_data:
            return models.TimeTrackingDataSingle.build_data(fetched_time_data)

    def stop_timer(self, team_id: str) -> Optional[models.TimeTrackingData]:
        uri = f"team/{team_id}/time_entries/stop"
        fetched_time_data = self.__post_request(uri, None)
        if fetched_time_data:
            return models.TimeTrackingDataSingle.build_data(fetched_time_data)

    def get_list_views(self, list_id: str) -> Optional[models.Views]:
        uri = f"list/{list_id}/view"
        fetched_views = self.__get_request(uri)
        if fetched_views:
            return models.Views.build_views(fetched_views)

    def get_webhooks(self, team_id: int) -> Optional[models.Webhooks]:
        uri = f"team/{str(team_id)}/webhook"
        fetched_webhooks = self.__get_request(uri)
        if fetched_webhooks:
            return models.Webhooks.build_webhooks(fetched_webhooks)

    def create_webhook(self, team_id: int, create_webhook: models.CreateWebhook) -> Optional[models.Webhook]:
        uri = f"team/{str(team_id)}/webhook"
        created_webhook = self.__post_request(uri, create_webhook.model_dump_json())
        if created_webhook:
            return models.CreatedWebhook.build_webhook(created_webhook).webhook

    def delete_webhook(self, webhook_id: str) -> bool:
        uri = f"webhook/{webhook_id}"
        self.__delete_request(uri)
        return True

    def update_webhook(
            self,
            webhook_id: str,
            endpoint: str,
            events: str = '*',
            status: models.WebhookHealthStatus = models.WebhookHealthStatus.active,
    ) -> models.UpdatedWebhook:
        uri = f"webhook/{webhook_id}"
        updated_webhook = self.__put_request(uri, {"endpoint": endpoint, "events": events, "status": status.value})
        return models.UpdatedWebhook(**updated_webhook)

    # Custom Fields
    def set_custom_field_value(
            self,
            task_id: str,
            field_id: str,
            value: Any,
    ) -> bool:
        """Sets the value of a custom field on a task.

        Args:
            task_id (str): The ID of the task to update.
            field_id (str): The UUID of the custom field to set.
            value (Any): The value to set. Type depends on the custom field type:
                - Text: str
                - Number: int or float
                - Dropdown: str (option id) or int (option order index)
                - Date: int (Unix timestamp in milliseconds)
                - Checkbox: bool
                - Labels: list of label UUIDs
                - Currency: int or float
                - etc.

        Returns:
            bool: True if the custom field was successfully set.
        """
        data = {"value": value}
        uri = f"task/{task_id}/field/{field_id}"
        self.__post_request(uri, data)
        return True
