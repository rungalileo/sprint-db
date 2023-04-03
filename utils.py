from datetime import datetime, timedelta, timezone
from typing import Dict, List
from api_router import ApiRouter


class Utils:

    def __init__(self, r: ApiRouter):
        self.r = r
        self._priority_field_id = '62f6c112-35ed-4b29-9e07-dd16975ba823'

    def filter_all_but_unneeded_and_completed(self, story_list: List) -> List:
        return [e for e in story_list if e.get("unneeded", "") is not True and e.get("completed", "") is not True]

    def filter_all_but_unneeded_and_completed_and_in_review(self, story_list: List) -> List:
        """
        Get all stories except the unneeded, completed, and in-review ones
        :param story_list:
        :return:
        """
        return [e for e in story_list if
                e.get("unneeded", "") is not True and e.get("completed", "") is not True and self.r.get_workflow(
                    e['workflow_state_id']) != 'In Review']

    def filter_all_but_unneeded(self, story_list: List):
        return [e for e in story_list if e.get("unneeded", "") is not True]

    def filter_completed(self, story_list: List) -> List:
        """
        Return all completed stories
        :param story_list:
        :return: list of completed stories
        """
        return [e for e in story_list if e.get("completed", "") is True]

    def filter_in_review_and_ready_for_development(self, story_list: List) -> List:
        return [
            e for e in story_list if
            self.r.get_workflow(e['workflow_state_id']) == 'Ready for Development' or
            self.r.get_workflow(e['workflow_state_id']) == 'In Review' or
            self.r.get_workflow(e['workflow_state_id']) == 'Triage'
        ]

    def filter_triage(self, story_list: List) -> List:
        return [e for e in story_list if self.r.get_workflow(e['workflow_state_id']) == 'Triage']

    def filter_completed_and_in_review(self, story_list: List) -> List:
        return [e for e in story_list if
                e.get('completed', '') is True or self.r.get_workflow(e['workflow_state_id']) == 'In Review']

    def filter_bugs(self, stories: List) -> List:
        return [s for s in stories if s.get('story_type', '') == 'bug']

    def filter_features(self, stories: List) -> List:
        return [s for s in stories if s.get('story_type', '') == 'feature' or s.get('story_type', '') == 'chore']

    def filter_non_archived(self, stories: List) -> List:
        return [s for s in stories if s.get('archived', False) is not True]

    def filter_stories_by_epic(self, stories: List, epic_name: str) -> Dict:
        fields = ["Story", "Type", "Milestone", "Priority", "State", "Created", "Requested By", "Owner"]
        fields_lists = [[] for _ in fields]

        for story in stories:
            if epic_name == self.r.get_epic_name(story["epic_id"]).strip():
                self._populate_lists_for_story_dataframe(
                    creation_date_list=fields_lists[fields.index("Created")],
                    milestone_name_list=fields_lists[fields.index("Milestone")],
                    priority_list=fields_lists[fields.index("Priority")],
                    state_list=fields_lists[fields.index("State")],
                    story=story,
                    story_list=fields_lists[fields.index("Story")],
                    story_type_list=fields_lists[fields.index("Type")],
                    requester_names=fields_lists[fields.index("Requested By")],
                    assignee_names=fields_lists[fields.index("Owner")],
                )

        return dict(zip(fields, fields_lists))

    def filter_stories_by_member(self, stories: List, member_name: str) -> Dict:
        filtered_stories = [story for story in stories if
                            member_name in [self.r.get_owner_name(owner).replace("\\", "") for owner in
                                            story["owner_ids"] if self.r.get_owner_name(owner) is not None]]
        data = {key: [] for key in ["Story", "Type", "Milestone", "Priority", "State", "Created", "Requested By"]}
        for story in filtered_stories:
            self._populate_lists_for_story_dataframe(data["Created"], data["Milestone"], data["Priority"],
                                                     data["State"], story, data["Story"], data["Type"],
                                                     data["Requested By"])
        return data

    def _populate_lists_for_story_dataframe(self, creation_date_list, milestone_name_list, priority_list, state_list,
                                            story, story_list, story_type_list, requester_names, assignee_names=None):
        if assignee_names is None:
            assignee_names = list()
        milestone_name = ""
        m = self.r.get_milestone_from_story(story)
        if m is not None:
            milestone_name = m["name"]
        story_list.append(f"{story['name']}###{story['app_url']}")
        milestone_name_list.append(milestone_name)
        story_type_list.append(story["story_type"])
        creation_date = None
        creation_day = story.get('created_at', '')
        if creation_day != '':
            date_object = datetime.strptime(creation_day, '%Y-%m-%dT%H:%M:%SZ')
            creation_date = date_object.strftime('%B %d, %Y')
        creation_date_list.append(creation_date)
        priority_value = "-"
        requester_id = story['requested_by_id']
        requester_name = self.r.get_members(member_id=str(requester_id))
        if requester_name is None:
            requester_names.append(None)
        else:
            requester_names.append(requester_name)

        assignee_id = story['owner_ids'][0] if story['owner_ids'] else ""
        assignee_name = self.r.get_members(member_id=str(assignee_id))
        if assignee_name is None:
            assignee_names.append(None)
        else:
            assignee_names.append(assignee_name)

        custom_fields = story["custom_fields"]
        for cf in custom_fields:
            if cf["field_id"] != self._priority_field_id:
                continue
            else:
                priority_value = str(cf["value"]).upper()
        priority_list.append(priority_value)
        state_list.append(self.r.get_workflow(story["workflow_state_id"]))

    def filter_recent_sprints(self, iterations: List) -> List:
        # Not to include future sprints
        iteration_names = []
        for it in iterations:
            end_date = datetime.strptime(it['end_date'], "%Y-%m-%d").date()
            start_date = datetime.strptime(it['start_date'], "%Y-%m-%d").date()
            if self.within_last_n_weeks(end_date) and start_date <= datetime.now().date():
                iteration_names.append((it['name'], end_date))
        return iteration_names

    def within_last_n_weeks(self, dt: datetime.date, n=8) -> bool:
        eight_weeks_ago = datetime.now() - timedelta(weeks=n)
        return dt >= eight_weeks_ago.date()

    def filter_stories_by_sprint(self, stories, sprint_name):
        iteration = self.r.get_iteration_from_name(iteration_name=sprint_name)
        sprint_start_date = datetime.fromisoformat(iteration.get('start_date', '').replace('Z', '+00:00'))
        sprint_end_date = datetime.fromisoformat(iteration.get('end_date', '').replace('Z', '+00:00'))
        sprint_stories = []
        for s in stories:
            creation_date = datetime.fromisoformat(s.get('created_at', '').replace('Z', '+00:00'))
            creation_date = creation_date.replace(tzinfo=timezone.utc)
            sprint_start_date = sprint_start_date.replace(tzinfo=timezone.utc)
            sprint_end_date = sprint_end_date.replace(tzinfo=timezone.utc)
            if sprint_start_date <= creation_date <= sprint_end_date:
                sprint_stories.append(s)
        return sprint_stories

    @staticmethod
    def is_feature_or_chore(story):
        return True if story['story_type'] == 'feature' or story['story_type'] == 'chore' else False

    @staticmethod
    def is_bug(story):
        return True if story['story_type'] == 'bug' else False

    @staticmethod
    def filter_all_but_done_epics(epics):
        return [e for e in epics if e['state'] != 'done']

    @staticmethod
    def get_completion_rate(addressed_stories, total_stories):
        total = len(total_stories)
        if total == 0:
            return 0
        total_addressed = len(addressed_stories)
        return round((total_addressed / total) * 100, 2)

    def filter_active_epics(self, epics_list):
        active_epics_list = []
        # this returns all active milestones + GBAI
        all_active_milestones = self.r.get_milestones(active=True)
        for e in epics_list:
            milestone_for_epic = self.r.get_milestone_from_epic_id(e['id'])
            if milestone_for_epic in all_active_milestones:
                active_epics_list.append(e)
        return active_epics_list

    @staticmethod
    def get_post_deployment_date(end_date):
        return end_date + timedelta(days=14)

    @staticmethod
    def get_dev_complete_date(end_date):
        return end_date - timedelta(days=6)
