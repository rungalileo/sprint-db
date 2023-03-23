import plost
import streamlit as st
import pandas as pd
from api_router import ApiRouter
from datetime import datetime, timezone
from typing import Dict, List
from utils import Utils

r = ApiRouter()
utils = Utils(r)


class SprintDashboard:
    def __init__(self):
        self._current_iteration = 'FFT'
        self.general_one_off_improvements_epic = 3079
        self.general_bugs_epic = 3078

        st.set_page_config(layout='wide', initial_sidebar_state='expanded')
        with open('style.css') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

    def has_recently_ended(self, m: Dict) -> bool:
        if m['completed_at_override'] is None:
            return False
        end_date = datetime.fromisoformat(m['completed_at_override'].replace('Z', '+00:00')).date()
        return utils.within_last_n_weeks(end_date, n=10)

    def get_story_completion_percentage(self, m: Dict) -> float:
        epics = r.get_epics_for_milestone(m['id'])
        completed_stories = sum(
            [s['completed'] for e in epics for s in r.get_stories_for_epic(e['id']) if not s['archived']])
        total_stories = sum([not s['archived'] for e in epics for s in r.get_stories_for_epic(e['id'])])
        if total_stories == 0:
            return 0.0
        return completed_stories / total_stories * 100

    def show_only_recently_finished(self, all_milestones: List) -> List:
        recently_finished_milestones = []
        for m in all_milestones:
            d = m.get('completed_at_override', None)
            if d is not None:
                dt = datetime.fromisoformat(m.get('completed_at_override', '').replace('Z', '+00:00')).date()
                if m.get('completed', '') is True and utils.within_last_n_weeks(dt, n=10):
                    recently_finished_milestones.append(m)
        return recently_finished_milestones

    def show_sprint_stars(self, completed_stories_in_sprint: List[Dict]) -> List[str]:
        user_count_map: Dict[str, int] = {}
        for s in completed_stories_in_sprint:
            for owner in s['owner_ids']:
                owner_name = r.get_owner_name(owner)
                user_count_map[owner_name] = user_count_map.get(owner_name, 0) + 1
        # sort the map by value
        user_count_map = dict(sorted(user_count_map.items(), key=lambda x: -x[1]))
        stars = [f'<b>{key}</b>, for crushing {value} stories!' for key, value in user_count_map.items()]
        return stars[:5]

    def get_epic_story_counts(self, all_active_epics: List) -> Dict:
        bugs = {}
        features = {}

        # Loop through all epics
        for epic in all_active_epics:
            epic_name = epic.get('name', '')
            for s in utils.filter_all_but_unneeded_and_completed(r.get_stories_for_epic(epic['id'], sprint=self._current_iteration)):
                if s.get('story_type', '') in ['feature', 'chore']:
                    features[epic_name] = features.setdefault(epic_name, 0) + 1
                elif s.get('story_type', '') == 'bug':
                    bugs[epic_name] = bugs.setdefault(epic_name, 0) + 1
        merged_dict = {"name": [], "features": [], "bugs": []}
        for key in set(features.keys()) | set(bugs.keys()):
            merged_dict["name"].append(key)
            features_count = features.get(key, 0)
            merged_dict["features"].append(features_count)
            bugs_count = bugs.get(key, 0)
            merged_dict["bugs"].append(bugs_count)

        return merged_dict

    def get_state_distribution(self, total_stories_in_sprint: List) -> Dict:
        workflow_names = {}
        for story in total_stories_in_sprint:
            workflow_id = story['workflow_state_id']
            if workflow_id is not None and workflow_id not in workflow_names:
                workflow_names[workflow_id] = r.get_workflow(workflow_id)

        state_distributions = {}
        for workflow_id, workflow_name in workflow_names.items():
            state_distributions[workflow_name] = 0

        for story in total_stories_in_sprint:
            workflow_id = story['workflow_state_id']
            if workflow_id is not None:
                workflow_name = workflow_names[workflow_id]
                state_distributions[workflow_name] += 1

        return state_distributions

    def create_dashboard(self):
        if 'iteration_name' in st.session_state:
            self._current_iteration = st.session_state['iteration_name']

        active_milestones = list(r.get_milestones(active=True))
        all_milestones_in_sprint = active_milestones + r.get_special_milestones()
        general_bugs_and_improvement_stories = r.get_all_stories_for_milestone(milestone_id=3077,
                                                                               sprint=self._current_iteration)
        all_gen_bugs_in_sprint = utils.filter_bugs(general_bugs_and_improvement_stories)
        all_gen_features_in_sprint = utils.filter_features(general_bugs_and_improvement_stories)

        # all stories in this sprint
        key_stories_in_sprint = []
        for milestone in active_milestones:
            key_stories_in_sprint.extend(
                r.get_all_stories_for_milestone(milestone['id'], sprint=self._current_iteration)
            )
        all_bugs_in_sprint = utils.filter_bugs(key_stories_in_sprint)
        all_features_in_sprint = utils.filter_features(key_stories_in_sprint)

        all_bugs_in_sprint.extend(all_gen_bugs_in_sprint)
        all_features_in_sprint.extend(all_gen_features_in_sprint)

        self.populate_top_sprint_metrics(active_milestones, all_bugs_in_sprint, all_features_in_sprint,
                                         all_gen_bugs_in_sprint, all_gen_features_in_sprint, key_stories_in_sprint)

        st.markdown("""---""")

        ####
        tab1, tab2, tab3, tab4 = st.tabs(
            ['Key Milestones', 'Milestone Timelines', 'Engineer Stories', 'Feature/Bugs Distributions']
        )

        self.populate_tab_1(active_milestones, tab1)
        self.populate_tab_2(active_milestones, tab2)

        total_stories_in_sprint = all_features_in_sprint + all_bugs_in_sprint
        self.populate_tab_3(active_milestones, all_gen_bugs_in_sprint, all_gen_features_in_sprint,
                            all_milestones_in_sprint, total_stories_in_sprint, tab3)
        self.populate_tab_4(all_bugs_in_sprint, all_features_in_sprint, all_gen_bugs_in_sprint,
                            all_gen_features_in_sprint, total_stories_in_sprint, tab4)

        # Create a container for the footer
        footer_container = st.container()

        # Add your footer content to the container
        with footer_container:
            st.write("---")
            st.write("<center>Built with ❤️ by Atin</center>", unsafe_allow_html=True)

    def populate_tab_4(self, all_bugs_in_sprint, all_features_in_sprint, all_gen_bugs_in_sprint,
                       all_gen_features_in_sprint, total_stories_in_sprint, tab4):
        with tab4:
            st.markdown('## Feature / Bugs Distributions')

            c1, c2, c3, c4, c5 = st.columns(5)

            num_total_in_sprint = len(total_stories_in_sprint)
            num_features_in_sprint = len(all_features_in_sprint)
            num_bugs_in_sprint = len(all_bugs_in_sprint)

            c1.metric("Total Stories", num_total_in_sprint)
            c2.metric("Features %", round(num_features_in_sprint / num_total_in_sprint * 100), 1)
            c3.metric("Bugs %", round(num_bugs_in_sprint / num_total_in_sprint * 100), 1)
            c4.metric("Features Closed", len(utils.filter_completed(all_features_in_sprint)))
            c5.metric("Bugs Squashed", len(utils.filter_completed(all_bugs_in_sprint)))
            st.markdown("""---""")

            # Row D
            st.markdown('### Stories by State')
            # Row E
            col1, col2, col3 = st.columns((4.5, 1, 4.5))
            with col1:
                story_state_distribution = self.get_state_distribution(total_stories_in_sprint)
                status_map = {
                    'State': story_state_distribution.keys(),
                    'Stories': story_state_distribution.values()
                }
                status_map_df = pd.DataFrame(status_map)
                plost.donut_chart(
                    data=status_map_df,
                    theta='Stories',
                    color='State'
                )
            with col3:
                st.markdown('### New Bugs/Features By Day')
                date_tickets_map = self.show_new_bugs_features_filed_per_day(total_stories_in_sprint)
                plost.bar_chart(
                    data=pd.DataFrame(date_tickets_map),
                    bar='Dates',
                    value=['Features', 'Bugs'],
                    use_container_width=True,
                )
            st.markdown("""---""")
            self.draw_feature_bug_distributions(
                all_gen_bugs_in_sprint,
                all_gen_features_in_sprint,
                total_stories_in_sprint,
            )

    def populate_tab_3(self, active_milestones, all_gen_bugs_in_sprint, all_gen_features_in_sprint,
                       all_milestones_in_sprint, total_stories_in_sprint, tab3):
        with tab3:
            # Row C
            current_iteration_stories = []
            for milestone in active_milestones:
                epics = utils.filter_all_but_unneeded(r.get_epics_for_milestone(milestone['id']))
                for epic in epics:
                    stories = utils.filter_all_but_unneeded(r.get_stories_for_epic(epic['id']))
                    for story in stories:
                        if story['iteration_id'] is not None and r.get_iteration_name_from_id(
                                story['iteration_id']) == self._current_iteration:
                            current_iteration_stories.append(story)

            self.draw_ownership_count_charts(all_gen_bugs_in_sprint,
                                             all_gen_features_in_sprint,
                                             current_iteration_stories,
                                             all_milestones_in_sprint)

            st.markdown("""---""")
            all_devs = r.get_all_members()
            col1, col2, col3 = st.columns((4.5, 1, 4.5))
            with col1:
                st.markdown("### Member Stories")
                all_devs = [s.strip() for s in all_devs]
                team_member_name = st.selectbox('Team Member:', all_devs)
                stories_df = pd.DataFrame(
                    utils.filter_stories_by_member(utils.filter_non_archived(total_stories_in_sprint), team_member_name)
                )
                stories_df = stories_df.style.format({'Story': self.make_clickable})
                stories_df.index += 1
                story_table = stories_df.to_html()
                st.write(story_table, unsafe_allow_html=True)
            with col3:
                stars = self.show_sprint_stars(utils.filter_completed_and_in_review(total_stories_in_sprint))
                st.markdown('### 🌮🌮 Sprint Tacos 🌮🌮')
                for star in stars:
                    st.write(star, unsafe_allow_html=True)

    def populate_tab_2(self, active_milestones, tab2):
        with tab2:
            # Row B
            c1, c2, c3 = st.columns((1, 8, 1))
            with c2:
                st.markdown("### Key Milestone")
                df = pd.DataFrame(self.get_milestone_data_view(active_milestones))
                df = df.style.format({'Milestone': self.make_clickable})
                df.index += 1
                table = df.to_html()
                st.write(table, unsafe_allow_html=True)

                st.markdown("""---""")
                self.milestones_needing_attention(active_milestones)

    def populate_tab_1(self, active_milestones: List, tab1):
        with tab1:
            st.markdown('### Key Milestone Timelines')
            c1, c2 = st.columns((7, 3))
            with c1:
                self.draw_eta_visualization(active_milestones)

    def populate_top_sprint_metrics(self, active_milestones, all_bugs_in_sprint, all_features_in_sprint,
                                    all_gen_bugs_in_sprint, all_gen_features_in_sprint, key_stories_in_sprint):
        # Row A
        st.markdown('### Galileo: Sprint Metrics')
        st.markdown("""---""")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.metric("Milestones", len(active_milestones))
        col2.metric("Milestone Stories", len(key_stories_in_sprint))
        ongoing_stories = []
        for milestone in active_milestones:
            ongoing_stories.extend(
                utils.filter_all_but_unneeded_and_completed_and_in_review(
                    r.get_all_stories_for_milestone(milestone['id'], sprint=self._current_iteration)
                )
            )
        col3.metric("Milestone Stories Ongoing", len(ongoing_stories))
        # Key completed stories: are stories that have been marked as completed in this Sprint
        # loop through all active milestones - filter only completed stories for each milestone
        key_addressed_stories = []
        for milestone in active_milestones:
            key_addressed_stories.extend(
                utils.filter_completed_and_in_review(
                    r.get_all_stories_for_milestone(milestone['id'], sprint=self._current_iteration)
                )
            )

        col4.metric("Milestone Stories Addressed", len(key_addressed_stories))
        col5.metric("General Bugs", len(all_gen_bugs_in_sprint))
        col6.metric("General Improvements", len(all_gen_features_in_sprint))
        col7.metric('Total Features/Total Bugs', '{}/{}'.format(len(all_features_in_sprint), len(all_bugs_in_sprint)))

    def draw_feature_bug_distributions(
            self,
            all_gen_bugs_in_sprint,
            all_gen_features_in_sprint,
            total_stories_in_sprint,
    ):
        c1, c2 = st.columns((5, 5))
        with c1:
            st.markdown('#### Features & Bugs: Key Milestones')
            status_map = r.get_status_count(total_stories_in_sprint)
            status_map = {
                'Status': status_map.keys(),
                'Stories': status_map.values()
            }
            status_map_df = pd.DataFrame(status_map)
            plost.donut_chart(
                data=status_map_df,
                theta='Stories',
                color='Status'
            )
        with c2:
            st.markdown('#### General Bugs & Features')
            general_bug_features = {
                'Type': ['Bugs', 'Features'],
                'Count': [len(all_gen_bugs_in_sprint), len(all_gen_features_in_sprint)]
            }
            plost.donut_chart(
                data=pd.DataFrame(general_bug_features),
                theta='Count',
                color='Type'
            )

    def draw_ownership_count_charts(self,
                                    all_gen_bugs_in_sprint,
                                    all_gen_features_in_sprint,
                                    current_iteration_stories,
                                    all_active_milestones):
        c1, c2, c3 = st.columns((4.5, 1, 4.5))
        with c1:
            st.markdown('### Key Milestones Stories')
            owner_map = r.get_owner_count(current_iteration_stories)
            plost.bar_chart(
                data=pd.DataFrame(owner_map),
                bar='Owner',
                value='Stories',
                color='#e28743',
                height=600,
                use_container_width=True,
            )
        with c3:
            # general bugs
            st.markdown('### General Bugs & Features')
            general_bug_owners = r.get_owner_count(all_gen_bugs_in_sprint)
            general_improvements_owners = r.get_owner_count(all_gen_features_in_sprint)

            bug_owners_df = pd.DataFrame(general_bug_owners)
            improvement_owners_df = pd.DataFrame(general_improvements_owners)
            merged_df = pd.merge(bug_owners_df, improvement_owners_df, on='Owner', how='outer').fillna(0)
            merged_df = merged_df.rename(
                columns={'Stories_x': 'Bugs', 'Stories_y': 'Features'}
            )
            plost.bar_chart(
                data=merged_df,
                bar='Owner',
                value=['Bugs', 'Features'],
                height=600,
                use_container_width=True,
            )
        st.markdown("""---""")
        st.markdown('### Hot Sprint Epics')
        c1, c2, c3 = st.columns((2, 6, 2))
        with c2:
            # Grouped Bar of Features & Bugs - by Epics
            all_active_epics = []
            for m in all_active_milestones:
                all_active_epics.extend(r.get_epics_for_milestone(m['id']))
            epic_story_count_map = self.get_epic_story_counts(all_active_epics)
            plost.bar_chart(
                data=pd.DataFrame(epic_story_count_map),
                bar='name',
                value=['bugs', 'features'],
                height=600,
                use_container_width=True,
            )

    def draw_eta_visualization(self, active_milestones):
        for milestone in active_milestones:
            start_date = datetime.fromisoformat(milestone.get('started_at_override', '').replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(milestone.get('completed_at_override', '').replace('Z', '+00:00'))
            duration = end_date - start_date
            progress = datetime.now(timezone.utc) - start_date.replace(tzinfo=timezone.utc)
            progress_percent = int(progress.total_seconds() / duration.total_seconds() * 100)
            x, y = st.columns((6, 4))
            with x:
                col = 'red' if progress_percent > 80 else 'green'
                st.markdown(f"<b>{milestone['name']}</b> (<font color='{col}'><b>{progress_percent}%</b></font> elapsed)", unsafe_allow_html=True)
            with y:
                if progress_percent > 80:
                    st.markdown(f"""
                            <div style='background-color: #DBDBDB; height: 10px; border-radius: 5px;'>
                              <div style='background-color: #f44336; height: 10px; width: {progress_percent}%; border-radius: 5px;'></div>
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                            <div style='background-color: #DBDBDB; height: 10px; border-radius: 5px;'>
                              <div style='background-color: #8fce00; height: 10px; width: {progress_percent}%; border-radius: 5px;'></div>
                            </div>
                        """, unsafe_allow_html=True)

    def milestones_needing_attention(self, active_milestones):
        st.markdown('### Milestones Needing Attention')
        active_ms_set = set()
        for am in active_milestones:
            active_ms_set.add(am['id'])
        # milestones that have passed the dates,
        problematic_milestones = []
        problematic_completion_percent = []
        all_milestones = list(r.get_milestones())
        for m in all_milestones:
            cp = self.get_story_completion_percentage(m)
            if m['id'] not in active_ms_set and self.has_recently_ended(m) and cp <= 95:
                problematic_milestones.append(m)
                problematic_completion_percent.append("{}%".format(str(round(cp, 2))))
        # now we have the list of non active milestones
        pdf = pd.DataFrame(self.get_milestone_data_view(problematic_milestones))
        pdf = pdf.style.format({'Milestone': self.make_clickable})
        pdf.index += 1
        prb_html = pdf.to_html()
        st.write(prb_html, unsafe_allow_html=True)

    def make_clickable(self, val):
        split_val = val.split('###')
        return "<a href={} target='_blank'>{}</a>".format(split_val[1], split_val[0])

    def get_milestone_data_view(self, milestones):
        milestone_names = []
        started_dates = []
        target_completion_dates = []
        num_epics = []
        num_stories = []
        days_elapsed = []
        days_to_target = []
        problematic_completion_percent = []

        for milestone in milestones:
            milestone_names.append(milestone['name'] + "###" + milestone['app_url'])
            epics = r.get_epics_for_milestone(milestone['id'])
            num_epics.append(len(epics))
            total_stories = 0
            for e in epics:
                stories = r.get_stories_for_epic(e['id'])
                total_stories += len(stories)

            num_stories.append(total_stories)

            started_date = None
            completed_date = None
            if milestone['started_at_override'] is not None:
                started_date = datetime.fromisoformat(milestone['started_at_override'].replace('Z', '+00:00'))
                started_dates.append(started_date.strftime('%B %d, %Y'))
            else:
                started_dates.append(None)

            if milestone['completed_at_override'] is not None:
                completed_date = datetime.fromisoformat(milestone['completed_at_override'].replace('Z', '+00:00'))
                target_completion_dates.append(completed_date.strftime('%B %d, %Y'))
                days_to_target.append((completed_date.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days + 1)
                if started_date is not None:
                    period = datetime.now().replace(tzinfo=timezone.utc) - started_date
                    days_elapsed.append(period.days)
            else:
                target_completion_dates.append(None)
                days_to_target.append(None)

            if (started_date is None) or (started_date is None and completed_date is None):
                days_elapsed.append(0)

            cp = self.get_story_completion_percentage(milestone)
            problematic_completion_percent.append("{}%".format(str(round(cp, 2))))

        days_elapsed = [int(d) for d in days_elapsed]
        data = {
            'Milestone': milestone_names,
            'Started At': started_dates,
            'Target Completion': target_completion_dates,
            'Epics': num_epics,
            'Stories': num_stories,
            'Days Elapsed': days_elapsed,
            'Days Remaining': days_to_target,
            'Completion': problematic_completion_percent
        }
        return data

    def show_new_bugs_features_filed_per_day(self, stories):
        stories = utils.filter_stories_by_sprint(stories, 'FFT')
        bugs = {}
        features = {}
        for s in stories:
            creation_day = s.get('created_at', '')
            if creation_day != '':
                date_object = datetime.strptime(creation_day, '%Y-%m-%dT%H:%M:%SZ')
                date_str = date_object.strftime('%Y-%m-%d')
                if utils.is_feature_or_chore(s):
                    features[date_str] = features.setdefault(date_str, 0) + 1
                elif utils.is_bug(s):
                    bugs[date_str] = bugs.setdefault(date_str, 0) + 1
        bugs = dict(sorted(bugs.items(), key=lambda x: x[0]))
        features = dict(sorted(features.items(), key=lambda x: x[0]))
        merged_dict = {"Dates": [], "Features": [], "Bugs": []}
        for key in set(features.keys()) | set(bugs.keys()):
            merged_dict["Dates"].append(key)
            merged_dict["Features"].append(features.get(key, 0))
            merged_dict["Bugs"].append(bugs.get(key, 0))
        return merged_dict


def main():
    sdb = SprintDashboard()
    sprints = r.get_all_sprints()
    recent_sprints = utils.filter_recent_sprints(sprints)
    sprints = [name for name, e_date in sorted(recent_sprints, key=lambda x: x[1], reverse=True)]
    if sprints is None:
        sprints = []
    st.sidebar.header('Sprint Dashboard')
    st.session_state['iteration_name'] = st.sidebar.selectbox('Sprint Name:', tuple(sprints))
    sdb.create_dashboard()


if __name__ == '__main__':
    main()
