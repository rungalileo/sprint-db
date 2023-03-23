from datetime import datetime, timedelta, timezone
from typing import Dict, List
from api_router import ApiRouter


class Utils:

    def __init__(self, r: ApiRouter):
        self.r = r
        self._priority_field_id = '62f6c112-35ed-4b29-9e07-dd16975ba823'

    def filter_all_but_unneeded_and_completed(self, story_list: List) -> List:
        return [e for e in story_list if e.get("unneeded", "") is not True and e.get("completed", "") is not True]

    def filter_all_but_unneeded(self, story_list: List):
        return [e for e in story_list if e.get("unneeded", "") is not True]

    def filter_completed(self, story_list: List) -> List:
        return [e for e in story_list if e.get("completed", "") is True]

    def filter_completed_and_in_review(self, story_list: List) -> List:
        return [e for e in story_list if
                e.get('completed', '') is True or self.r.get_workflow(e['workflow_state_id']) == 'In Review']

    def filter_bugs(self, stories: List) -> List:
        return [s for s in stories if s.get('story_type', '') == 'bug']

    def filter_features(self, stories: List) -> List:
        return [s for s in stories if s.get('story_type', '') == 'feature' or s.get('story_type', '') == 'chore']

    def filter_non_archived(self, stories: List) -> List:
        return [s for s in stories if s.get('archived', False) is not True]

    def filter_stories_by_member(
            self, stories: List, member_name: str
    ) -> Dict:
        story_list: List[str] = []
        story_type_list: List[str] = []
        milestone_name_list: List[str] = []
        priority_list: List[str] = []
        state_list: List[str] = []

        for story in stories:
            if member_name in [
                self.r.get_owner_name(owner).replace("\\", "")
                for owner in story["owner_ids"]
                if self.r.get_owner_name(owner) is not None
            ]:
                milestone_name = ""
                m = self.r.get_milestone_from_story(story)
                if m is not None:
                    milestone_name = m["name"]
                story_list.append(f"{story['name']}###{story['app_url']}")
                milestone_name_list.append(milestone_name)
                story_type_list.append(story["story_type"])

                priority_value = "-"
                custom_fields = story["custom_fields"]
                for cf in custom_fields:
                    if cf["field_id"] != self._priority_field_id:
                        continue
                    else:
                        priority_value = str(cf["value"]).upper()
                priority_list.append(priority_value)
                state_list.append(self.r.get_workflow(story["workflow_state_id"]))

        return {
            "Story": story_list,
            "Type": story_type_list,
            "Milestone": milestone_name_list,
            "Priority": priority_list,
            "State": state_list,
        }

    def filter_recent_sprints(self, iterations: List) -> List:
        iteration_names = []
        for it in iterations:
            end_date = datetime.strptime(it['end_date'], "%Y-%m-%d").date()
            if self.within_last_n_weeks(end_date):
                iteration_names.append((it['name'], end_date))
        return iteration_names

    def within_last_n_weeks(self, dt: datetime.date, n=8) -> bool:
        eight_weeks_ago = datetime.now() - timedelta(weeks=n)
        return dt >= eight_weeks_ago.date()

    def filter_stories_by_sprint(self, stories, sprint_name):
        iteration = self.r.get_iteration_from_name(iteration_name=sprint_name)
        sprint_start_date = datetime.fromisoformat(iteration.get('start_date', '').replace('Z', '+00:00'))
        sprint_end_date = datetime.fromisoformat(iteration.get('end_date', '').replace('Z', '+00:00'))
        x = []
        for s in stories:
            creation_date = datetime.fromisoformat(s.get('created_at', '').replace('Z', '+00:00'))
            creation_date = creation_date.replace(tzinfo=timezone.utc)
            sprint_start_date = sprint_start_date.replace(tzinfo=timezone.utc)
            sprint_end_date = sprint_end_date.replace(tzinfo=timezone.utc)
            if sprint_start_date <= creation_date <= sprint_end_date:
                x.append(s)
        return x

    @staticmethod
    def is_feature_or_chore(story):
        return True if story['story_type'] == 'feature' or story['story_type'] == 'chore' else False

    @staticmethod
    def is_bug(story):
        return True if story['story_type'] == 'bug' else False
