from typing import Optional
from syncgitlab2msproject.custom_types import WebURL

from .ms_project import Task

def is_gitlab_hyperlink(url: WebURL, gitlab_url: WebURL) -> bool:
    return url.startswith(gitlab_url)


def get_weburl_from_task(task: Optional[Task], gitlab_url: WebURL) -> Optional[WebURL]:
    """
    Get the weburl from MS Project Task (is saved as hyperlink)
    """

    def check_get_url(value: Optional[str]) -> Optional[WebURL]:
        if value is not None:
            check_url = WebURL(value)
            if is_gitlab_hyperlink(check_url, gitlab_url):
                return check_url
        return None

    if task is not None:
        if (url := check_get_url(task.hyperlink_address)) is not None:
            return url
        # If not as hyperlink we also look in task.text29 field
        if (url := check_get_url(task.text29)) is not None:
            return url
    return None