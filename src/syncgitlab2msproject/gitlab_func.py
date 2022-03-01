from functools import lru_cache
from gitlab import Gitlab
from gitlab.v4.objects import Project
from logging import getLogger
from typing import Dict, Optional, Union

from .custom_types import GitlabUserDict

logger = getLogger(f"{__package__}.{__name__}")


def get_user_identifier(user_dict: GitlabUserDict) -> str:
    """
    Return the user identifier

    keep as separate function to allow easier changes later if required
    """
    return str(user_dict["name"])



@lru_cache(10)
def get_group_id_from_gitlab_project(project: Project) -> Optional[int]:
    """
    Get user id form gitlab project.
    If the namespace of the project is a user, a negativ
    value is returned
    :param project:
    """
    try:
        namespace: Dict[str, Union[int, str]] = project.namespace
    except AttributeError:
        logger.warning(
            f"Could not extract name space for project '{project.get_id()}' - "
            "This error will be ignored."
        )
        return None
    if str(namespace["kind"]).lower() == "user":
        return -int(namespace["id"])
    else:
        return int(namespace["id"])


def get_gitlab_class(server: str, personal_token: Optional[str] = None) -> Gitlab:
    if personal_token is None:
        return Gitlab(server, ssl_verify=False)
    else:
        return Gitlab(server, private_token=personal_token, ssl_verify=False)

