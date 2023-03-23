import os
import sys
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional, Any


# Distribution of stories per Milestone within the Sprint
# Distribution of stories per person

# Status distribution of Stories:
#   - % of completed stories - grouped by milestone within the Sprint
#   - % of triage stories - grouped by milestone within the Sprint
#   - % of in progress stories - grouped by milestone within the Sprint


class ApiRouter:
    def __init__(self):
        self._calls_made = 0
        _retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["GET"],
            backoff_factor=1
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=_retry_strategy))

        self._base_url = 'https://api.app.shortcut.com/api'
        _token = os.getenv('SHORTCUT_API_TOKEN')
        _token = '6417c35e-acd8-442f-9ec8-f02da50f8dac' if _token is None else _token
        self._shortcut_token = '?token=' + _token
        self._get_milestones_url = '/v3/milestones'
        self._get_epics_url = '/v3/epics'
        self._get_iteration_url = '/v3/iterations'
        self._get_members_url = '/v3/members'
        self._get_workflows_url = '/v3/workflows'
        self._get_iteration_with_id_url = '/v3/iterations/{}'

        self._special_milestone_ids = {3073, 3077}
        self._all_milestones = dict()
        self._special_milestones = dict()
        self._all_sprints = list()
        self._milestone_epic_mappings = dict()
        self._epic_story_mappings = dict()
        self._members_dict = self._create_members_map()
        self._workflows_dict = self._create_workflows_id_map()
        self._iteration_map = dict()

    def _create_workflows_id_map(self) -> Dict[int, str]:
        workflows_dict: Dict[int, str] = {}
        workflows = self.make_api_call(f"{self._base_url}{self._get_workflows_url}")
        for workflow in workflows:
            for state in workflow['states']:
                workflows_dict[state['id']] = state['name']
        return workflows_dict

    def _create_members_map(self):
        members_dict = dict()
        members = self.make_api_call(self._base_url + self._get_members_url)
        for member in members:
            member_id = member['profile']['id']
            member_name = member['profile']['name']
            members_dict[member_id] = member_name
        return members_dict

    def make_api_call(self, url):
        if url in st.session_state:
            return st.session_state[url]
        try:
            self._calls_made += 1
            response = self.session.get(url + self._shortcut_token)
            # Add this URL to session state
            st.session_state[url] = response.json()
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(e)
            sys.exit(1)
        return response.json()

    def get_workflow(self, workflow_id):
        return self._workflows_dict[workflow_id]

    def get_members(self, member_id):
        return self._members_dict[member_id]

    def get_all_sprints(self):
        if len(self._all_sprints) == 0:
            self._do_get_iterations_and_load_cache()
        return self._all_sprints

    def _do_get_iterations_and_load_cache(self):
        all_iterations = self.make_api_call(self._base_url + self._get_iteration_url)
        self._all_sprints = all_iterations
        for iteration in all_iterations:
            self._iteration_map[iteration['id']] = iteration
            self._iteration_map[iteration['name']] = iteration

    def get_epics_for_milestone(self, milestone_id: int) -> List[Dict[str, Any]]:
        if milestone_id not in self._milestone_epic_mappings:
            url = f"{self._base_url}{self._get_milestones_url}/{milestone_id}/epics"
            epic_list = self.make_api_call(url)
            self._milestone_epic_mappings[milestone_id] = epic_list
        return self._milestone_epic_mappings[milestone_id]

    def get_all_stories_for_milestone(self, milestone_id, sprint=None) -> List[Dict[str, Any]]:
        stories: List[Dict[str, Any]] = []
        epics: Optional[List[Dict[str, Any]]] = self.get_epics_for_milestone(milestone_id)

        if epics is not None:
            for epic in epics:
                stories.extend(self.get_stories_for_epic(epic['id']))

        if sprint is not None:
            stories = [s for s in stories if
                       s.get('iteration_id') and sprint == self.get_iteration_name_from_id(s['iteration_id'])]

        return stories

    def get_stories_for_epic(self, epic_id, sprint=None):
        if epic_id not in self._epic_story_mappings:
            stories_list = self.make_api_call(self._base_url + self._get_epics_url + "/{}/stories".format(epic_id))
            self._epic_story_mappings[epic_id] = stories_list
        stories_list = self._epic_story_mappings[epic_id]
        if sprint is not None:
            stories_list = [s for s in stories_list if
                            s['iteration_id'] is not None and sprint == self.get_iteration_name_from_id(
                                s['iteration_id'])]
        return stories_list

    def get_milestones(self, active=False):
        if len(self._all_milestones) == 0:
            # Lazy call
            milestones = self.make_api_call(self._base_url + self._get_milestones_url)
            self._all_milestones.update({m['id']: m for m in milestones if m['id'] not in self._special_milestone_ids})
            self._special_milestones.update({m['id']: m for m in milestones if m['id'] in self._special_milestone_ids})

        milestones = self._all_milestones.values()

        if not active:
            return milestones

        active_milestones = [m for m in milestones if m.get('started_at_override') and m.get('completed_at_override')
                             and datetime.strptime(m['started_at_override'],
                                                   '%Y-%m-%dT%H:%M:%SZ').date() <= datetime.now().date() <= datetime.strptime(
            m['completed_at_override'], '%Y-%m-%dT%H:%M:%SZ').date()]
        return active_milestones

    def get_special_milestones(self) -> List:
        return list(self._special_milestones.values())

    def get_milestone_from_id(self, milestone_id):
        return self._all_milestones[milestone_id]

    def get_milestone_from_epic_id(self, epic_id):
        return next((self._all_milestones.get(mid) or self._special_milestones.get(mid) for mid, epics in
                     self._milestone_epic_mappings.items() for epic in epics if epic['id'] == epic_id), None)

    def get_milestone_from_story(self, story):
        return self.get_milestone_from_epic_id(story['epic_id'])

    def get_all_members(self):
        return list(self._members_dict.values())

    def get_owner_name(self, primary_story_owner_id):
        owner_info = self.make_api_call(self._base_url + self._get_members_url + "/" + primary_story_owner_id)
        owner_name = owner_info['profile']['name']
        return owner_name

    def get_iteration_status_count(self, iteration_id):
        iteration_url = self._get_iteration_url.format(iteration_id)
        return self.make_api_call(self._base_url + iteration_url)

    def get_status_count(self, story_list: List[Dict]) -> Dict[str, int]:
        status_count: Dict[str, int] = {}
        for story in story_list:
            state: str = story['story_type']
            status_count[state] = status_count.get(state, 0) + 1
        return status_count

    def get_owner_count(self, story_list: List[Dict]) -> Dict[str, List[int]]:
        owner_count: Dict[str, int] = {}
        for story in story_list:
            story_owners = story['owner_ids']
            if story_owners:
                primary_story_owner_id = story_owners[0]
                owner_name = self.get_owner_name(primary_story_owner_id)
                owner_count[owner_name] = owner_count.get(owner_name, 0) + 1
        return {
            'Owner': list(owner_count.keys()),
            'Stories': list(owner_count.values())
        }

    def get_iteration_name_from_id(self, iteration_id):
        try:
            if iteration_id not in self._iteration_map:
                # Lazy load
                self._do_get_iterations_and_load_cache()
            return self._iteration_map[iteration_id]['name']
        except KeyError:
            print('Bad Iteration ID passed in: {}'.format(iteration_id))
            return None

    def get_iteration_from_name(self, iteration_name):
        return self._iteration_map[iteration_name]
