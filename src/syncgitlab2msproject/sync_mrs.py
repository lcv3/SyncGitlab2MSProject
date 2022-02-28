import win32com.universal
from logging import getLogger
from typing import Callable, Dict, List, Optional, Type, overload

from syncgitlab2msproject.custom_types import WebURL
from syncgitlab2msproject.helper_classes import TaskTyperSetter

from .custom_types import MergeRequestRef
from .exceptions import (
    MergeRequestReferenceDuplicated,
    MovedMergeRequestNotDefined,
    MSProjectValueSetError,
)
from .gitlab_merge_requests import MergeRequest
from .ms_project import MSProject, Task

from .sync_func import get_weburl_from_task

logger = getLogger(f"{__package__}.{__name__}")

MR_PREFIX = "!!DON'T CHANGE!! MR:"

DEFAULT_DURATION = 8 * 60


def get_merge_request_ref_id(merge_request: MergeRequest) -> MergeRequestRef:
    """
    Return the ID of a gitlab MR

    Note the
    """
    return MergeRequestRef(merge_request.id)


def get_merge_request_web_url(merge_request: MergeRequest) -> WebURL:
    """
    Get the web url from a gitlab MR
    """
    return WebURL(merge_request.web_url)


def set_merge_request_ref_to_task(task: Task, merge_request: MergeRequest) -> None:
    """set reference to gitlab merge request in MS Project task"""
    task.text30 = (
        f"{MR_PREFIX}{merge_request.id};{merge_request.group_id};{merge_request.project_id};{merge_request.iid}"
    )


def get_merge_request_ref_from_task(task: Optional[Task]) -> Optional[MergeRequestRef]:
    """get reference to gitlab MRs from MS Project task"""
    if task is not None and task.text30 and task.text30.startswith(MR_PREFIX):
        values = task.text30[len(MR_PREFIX) :].split(";")
        return MergeRequestRef(int(values[0]))
    return None


def update_task_with_merge_request_data(
    task: Task,
    merge_request: MergeRequest,
    task_type_setter: Type[TaskTyperSetter],
    *,
    parent_ids: Optional[List[MergeRequestRef]] = None,
    ignore_merge_request: bool = False,
    is_add: bool = False,
) -> List[MergeRequestRef]:
    """
    Update task with MR data

    if an MR is moved the date of the new MR is used as long it is available

    Args:
        task: The MS Project task that will be updated
        merge_request: the MR with the data to be considered
        task_type_setter: Helper class to set the task type correct
        parent_ids: the parent stuff
        ignore_merge_request: only return the related (and moved) ids but do not really sync
                      This is required so we can ignored also moved MRs correctly
        is_add:

    Returns:
        list of MergeRequestRefs that
    """
    if parent_ids is None:
        parent_ids = [get_merge_request_ref_id(merge_request)]
    else:
        parent_ids += [get_merge_request_ref_id(merge_request)]

    if (moved_ref := merge_request.moved_reference) is not None:
        assert moved_ref is not None
        try:
            return update_task_with_merge_request_data(
                task,
                moved_ref,
                task_type_setter,
                parent_ids=parent_ids,
                ignore_merge_request=ignore_merge_request,
            )
        except MovedMergeRequestNotDefined:
            logger.warning(
                f"MR {merge_request} was moved outside of context."
                f" Ignoring the MR. Please update the task {task} manually!"
            )
    elif not ignore_merge_request:
        set_merge_request_ref_to_task(task, merge_request)
        try:
            type_setter = task_type_setter(merge_request)
            type_setter.set_task_type_before_sync(task, is_add)
            task.name = merge_request.title
            #task.notes = merge_request.description
            if merge_request.due_date is not None:
                task.deadline = merge_request.due_date
            if not task.has_children:
                if (estimated := merge_request.time_estimated) is not None:
                    task.work = int(estimated)
            # Update duration in case it seems to be default
            if task.duration == DEFAULT_DURATION and task.estimated:
                if task.work > 0:
                    task.duration = task.work
            if (time_spend := merge_request.time_spent_total) is not None:
                task.actual_work = time_spend
            if merge_request.has_tasks or task.percent_complete == 0:
                task.percent_complete = merge_request.percentage_tasks_done
            task.hyperlink_name = merge_request.full_ref
            task.hyperlink_address = merge_request.web_url
            task.text29 = merge_request.web_url
            task.text28 = "; ".join([f'"{label}"' for label in merge_request.labels])
            task.actual_start = merge_request.created_at
            if len(merge_request.assignees):
                task.resource_names = merge_request.assignees[0]
            if merge_request.is_closed:
                task.actual_finish = merge_request.closed_at
            type_setter.set_task_type_after_sync(task)
        except (MSProjectValueSetError, win32com.universal.com_error) as e:
            logger.error(
                f"FATAL: Could not sync MR {merge_request} to task {task}.\nError: {e}"
            )
        else:
            logger.info(f"Synced MR {merge_request} to task {task}")
    return parent_ids


def add_merge_request_as_task_to_project(
    tasks: MSProject, merge_request: MergeRequest, task_type_setter: Type[TaskTyperSetter]
):
    task = tasks.add_task(merge_request.title)
    logger.info(f"Created {task} as it was missing for MR, now syncing it.")
    # Add a setting to allow forcing outline level on new tasks
    # task.outline_level = 1
    update_task_with_merge_request_data(task, merge_request, task_type_setter, is_add=True)


class MergeRequestFinder:
    def __init__(self, merge_requests: List[MergeRequest]):
        # Create Dictionary of all IDs to find moved ones and relate existing
        self.ref_id_to_merge_request: Dict[MergeRequestRef, MergeRequest] = {}
        # We also try to sync according to the weburl but only in a second step
        self.web_url_to_merge_request: Dict[WebURL, MergeRequest] = {}
        for merge_request in merge_requests:
            """ Set up all references to locate later on"""
            ref_id = get_merge_request_ref_id(merge_request)
            if ref_id in self.ref_id_to_merge_request:
                raise MergeRequestReferenceDuplicated(
                    f"Reference ID {ref_id} was already defined! "
                    f"{self.ref_id_to_merge_request[ref_id]} and {merge_request} "
                    f"share the same Reference ID"
                )
            self.ref_id_to_merge_request[ref_id] = merge_request

            web_url = get_merge_request_web_url(merge_request)
            if web_url in self.web_url_to_merge_request:
                raise MergeRequestReferenceDuplicated(
                    f"Web URL {web_url} was already defined! "
                    f"{self.web_url_to_merge_request[web_url]} and {merge_request} "
                    f"share the same Web URL"
                )
            self.web_url_to_merge_request[web_url] = merge_request

    # Overload to make mypy aware of the fact that only None is given
    # once the id is none
    @overload
    def by_ref_id(self, ref_id: MergeRequestRef) -> MergeRequest:
        ...

    @overload
    def by_ref_id(self, ref_id: None) -> None:
        ...

    def by_ref_id(self, ref_id: Optional[MergeRequestRef]) -> Optional[MergeRequest]:
        """
        Give related MR if ref_id is set and the MR is found
        If an invalid reference is given throw
        :exceptions KeyError
        """
        if ref_id is None:
            return None
        return self.ref_id_to_merge_request[ref_id]

    def by_web_url(self, web_url: Optional[WebURL]) -> Optional[MergeRequest]:
        """
        Give related MR if weburl is set and the MR is found,
        If an invalid web_url is given throw
        :exceptions KeyError
        """
        if web_url is None:
            return None
        return self.web_url_to_merge_request[web_url]


def find_related_merge_request(
    task: Task, find_merge_request: MergeRequestFinder, gitlab_url: WebURL
) -> Optional[MergeRequest]:
    try:
        if (merge_request := find_merge_request.by_ref_id(get_merge_request_ref_from_task(task))) is not None:
            return merge_request
    except KeyError as key:
        logger.warning(
            f"Task {task} refers to MergeRequest with ID {key} which was not found in ."
            f"the MRs loaded from gitlab --> Ignored this reference"
        )
    try:
        if (
            merge_request := find_merge_request.by_web_url(get_weburl_from_task(task, gitlab_url))
        ) is not None:
            return merge_request
    except KeyError as key:
        logger.warning(
            f"Task {task} refers to Web url {key} which was not found in ."
            f"the MRs loaded from gitlab --> Ignored this reference"
        )
    return None


def sync_gitlab_merge_requests_to_ms_project(
    tasks: MSProject,
    merge_requests: List[MergeRequest],
    gitlab_url: WebURL,
    task_type_setter: Type[TaskTyperSetter],
    include_merge_request: Optional[Callable[[MergeRequest], bool]] = None,
) -> None:
    """

    Args:
        tasks: MS Project Tasks that will be synchronized
        merge_requests:  List of Gitlab MergeRequests
        gitlab_url: the gitlab istance url to check url found in MS project against
        include_merge_request: Include MR in sync, if None include everything
    """
    if include_merge_request is None:

        def always_true(x: MergeRequest):
            return True

        include_merge_request = always_true

    ref_merge_request: Optional[MergeRequest]
    # Keep track of already synced MRs
    synced: List[MergeRequestRef] = []

    # create finder
    find_merge_request = MergeRequestFinder(merge_requests)

    # Find moved MRs and reference them
    non_moved: List[MergeRequestRef] = []
    for merge_request in merge_requests:
        if (ref_int_id := merge_request.moved_to_id) is not None:
            if (ref_merge_request := find_merge_request.by_ref_id(MergeRequestRef(ref_int_id))) is not None:
                merge_request.moved_reference = ref_merge_request
        else:
            non_moved.append(get_merge_request_ref_id(merge_request))

    # get existing references and update them
    for task in tasks:
        if task is None:
            continue
        ref_merge_request = find_related_merge_request(task, find_merge_request, gitlab_url)

        if ref_merge_request is None:
            logger.info(
                f"Not Syncing {task} as a not reference "
                f"to a gitlab MR could be found"
            )
        else:
            ignore_merge_request = False
            if not include_merge_request(ref_merge_request):
                logger.info(
                    f"Ignoring task {task} as MR {ref_merge_request} "
                    f"has been marked to be ignored"
                )
                ignore_merge_request = True
            else:
                logger.info(f"Syncing {ref_merge_request} into {task}")
            # We want to not have the ignored task popping up in MRs that need to be
            # added and we also want make sure that moved ignored MRs are handled
            # correctly
            synced += update_task_with_merge_request_data(
                task, ref_merge_request, task_type_setter, ignore_merge_request=ignore_merge_request
            )

    # adding everything that was not synced and is not duplicate
    for ref_id in non_moved:
        if ref_id not in synced:
            if (ref_merge_request := find_merge_request.by_ref_id(ref_id)) is not None:
                if not include_merge_request(ref_merge_request):
                    logger.info(
                        f"Do not add MR {ref_merge_request} "
                        f"as it has been marked to be ignored."
                    )
                else:
                    add_merge_request_as_task_to_project(tasks, ref_merge_request, task_type_setter)
