from typing import Callable, List, Optional, Type

from syncgitlab2msproject.custom_types import WebURL
from syncgitlab2msproject.helper_classes import TaskTyperSetter

from .gitlab_issues import Issue
#from .gitlab_merge_requests import MergeRequest
from .ms_project import MSProject

from .sync_gis import sync_gitlab_issues_to_ms_project

def sync_gitlab_to_ms_project(
    tasks: MSProject,
    issues: List[Issue],
    gitlab_url: WebURL,
    task_type_setter: Type[TaskTyperSetter],
    include_issue: Optional[Callable[[Issue], bool]] = None,
) -> None:
    """

    Args:
        tasks: MS Project Tasks that will be synchronized
        issues:  List of Gitlab Issues
        gitlab_url: the gitlab istance url to check url found in MS project against
        include_issue: Include issue in sync, if None include everything
    """
    sync_gitlab_issues_to_ms_project(tasks, issues, gitlab_url,
        task_type_setter, include_issue)
    