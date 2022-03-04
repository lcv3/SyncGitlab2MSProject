import dateutil.parser
from datetime import datetime
from gitlab import Gitlab
from logging import getLogger
from typing import Dict, List, Optional

from .custom_types import GitlabMergeRequest
from .exceptions import MovedMergeRequestNotDefined
from .funcions import warn_once
from .gitlab_func import get_user_identifier,get_group_id_from_gitlab_project

logger = getLogger(f"{__package__}.{__name__}")

class MergeRequest:
    """
    Wrapper class around Group/Project MRs
    """

    # The MergeRequest object itself is not dynamic only the contained obj is!
    __slots__ = [
        "obj",
        "_fixed_group_id",
    ]

    def __init__(self, obj: GitlabMergeRequest, fixed_group_id: Optional[int] = None):
        """
        :param obj:
        :param fixed_group_id: Do not extract the group_id from the
                               Gitlab MR but assume it is fixed
        """
        self._fixed_group_id = fixed_group_id
        self.obj: GitlabMergeRequest = obj

    def __getattr__(self, item: str):
        """Default to get the values from the original objext"""
        return getattr(self.obj, item)

    def __str__(self):
        return f"'{self.title}' (ID: {self.id})"

    # **************************************************************
    # *** Define some default properties to allow static typing  ***
    # **************************************************************
    @property
    def id(self) -> int:
        """
        The id of a merge request - it seems to be unique within an installation
        """
        return self.obj.id

    @property
    def iid(self) -> int:
        return self.obj.iid

    @property
    def project_id(self) -> int:
        return self.obj.project_id

    @property
    def group_id(self) -> Optional[int]:
        """
        Return the group id, if negative a user id is given
        The group ID is either taken from the merge request itself or if a project is given
        the merge request is fixed (see #7)

        If group_id isn't fixed and can't be extracted, only give a warning and do
        not fail, as it isn't required to have the sync working. Only the
        merge request id or weblink is used to find the related merge request.
        See `sync.py`
          * `get_merge_request_ref_from_task`
          * `MergeRequestFinder`

        """
        if self._fixed_group_id is not None:
            return self._fixed_group_id
        try:
            return self.obj.group_id
        except AttributeError:
            warn_once(
                logger,
                "Could not extract group_id from MergeRequest. "
                "This is not required for syncing, so I will continue.",
            )
            return None

    @property
    def has_tasks(self) -> bool:
        return self.obj.task_completion_status['count'] > 0

    @property
    def is_closed(self) -> bool:
        return str(self.obj.state).lower().strip().startswith("closed")

    @property
    def is_merged(self) -> bool:
        return str(self.obj.state).lower().strip().startswith("merged")

    @property
    def is_open(self):
        return str(self.obj.state).lower().strip().startswith("open")

    @property
    def percentage_tasks_done(self) -> int:
        """
        Percentage of tasks done, 0 if no tasks are defined and not closed.
        By definition always 100 if MR is closed or merged

        :exceptions MovedMergeRequestNotDefined
        """
        if self.is_closed:
            return 100

        if self.is_merged:
            return 100

        if not self.has_tasks:
            return 0

        task = self.obj.task_completion_status
        
        return round(task["completed_count"] / task["count"] * 100)

    @property
    def title(self) -> str:
        return self.obj.title

    @property
    def description(self) -> str:
        return self.obj.description

    @property
    def closed_at(self) -> Optional[datetime]:
        if (val := self.obj.closed_at) is not None:
            return dateutil.parser.parse(val)
        return None

    @property
    def merged_at(self) -> Optional[datetime]:
        if (val := self.obj.merged_at) is not None:
            return dateutil.parser.parse(val)
        return None

    @property
    def created_at(self) -> Optional[datetime]:
        if (val := self.obj.created_at) is not None:
            return dateutil.parser.parse(val)
        return None

    @property
    def due_date(self) -> Optional[datetime]:
        if (self.obj.milestone) is None:
            return None
        if (val := self.obj.milestone['due_date']) is not None:
            return dateutil.parser.parse(val)
        return None

    @property
    def closed_by(self) -> Optional[str]:
        if (val := self.obj.closed_by) is not None:
            return get_user_identifier(val)
        return None

    def _get_from_time_stats(self, key) -> Optional[float]:
        """
        Somehow the python-gitlab API seems to be not 100% fixed,
        see issue #9

        :param key: key to query from time stats
        :return: the value if existing or none
        """
        query_dict: Dict[str, float]
        if callable(self.obj.time_stats):
            query_dict = self.obj.time_stats()
        else:
            query_dict = self.obj.time_stats
        return query_dict.get(key, None)

    @property
    def time_estimated(self) -> Optional[float]:
        """
        Time estimated in minutes
        """
        if (time_estimate := self._get_from_time_stats("time_estimate")) is not None:
            return time_estimate / 60
        else:
            logger.warning("Time Estimate is None")
            return None

    @property
    def time_spent_total(self) -> Optional[float]:
        """
        Total time spent in minutes
        """
        if (time_spend := self._get_from_time_stats("total_time_spent")) is not None:
            return time_spend / 60
        else:
            logger.warning("Time spend is None")
            return None

    @property
    def assignees(self) -> List[str]:
        """
        list of Gitlab Assignees.

        Note in the community edition only one assignee is possible
        """
        return [get_user_identifier(user) for user in self.obj.assignees]

    @property
    def author(self) -> str:
        """
        Gitlab MR Author.
        """
        return get_user_identifier(self.obj.author)


    @property
    def labels(self) -> List[str]:
        """
        list of labels
        """
        return self.obj.labels

    @property
    def full_ref(self) -> str:
        """
        give the full reference through which the MR can be accessed
        """
        return self.obj.attributes['references']['full']

    @property
    def web_url(self) -> str:
        """
        give the url from which the MR can be accessed
        """
        return self.obj.web_url


def get_group_merge_requests(gitlab: Gitlab, group_id: int) -> List[MergeRequest]:
    group = gitlab.groups.get(group_id, lazy=True)
    return [MergeRequest(merge_request) for merge_request in group.mergerequests.list(all=True,sort='desc')]


def get_project_merge_requests(gitlab: Gitlab, project_id: int) -> List[MergeRequest]:
    project = gitlab.projects.get(project_id)
    return [
        MergeRequest(merge_request, fixed_group_id=get_group_id_from_gitlab_project(project))
        for merge_request in project.mergerequests.list(all=True)
    ]
