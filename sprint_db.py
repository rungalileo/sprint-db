import plost
import streamlit as st
import pandas as pd
from api_router import ApiRouter
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from utils import Utils

r = ApiRouter()
utils = Utils(r)


class SprintDashboard:
    def __init__(self):
        self._current_iteration = None
        self.general_one_off_improvements_epic = 3079
        self.general_bugs_epic = 3078
        self.N_WEEKS_POST_DEPLOYMENT = 6
        self.N_WEEKS_NEEDS_ATTENTION = 15

        st.set_page_config(layout='wide', initial_sidebar_state='expanded')
        with open('style.css') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

    def has_ended_in_last_N_weeks(self, m: Dict, n_weeks: int) -> bool:
        if m['completed_at_override'] is None:
            return False
        end_date = datetime.fromisoformat(m['completed_at_override'].replace('Z', '+00:00')).date()
        self.weeks = utils.within_last_n_weeks(end_date, n=n_weeks)
        return self.weeks

    def get_story_completion_percentage(self, m: Dict) -> Tuple:
        epics = r.get_epics_for_milestone(m['id'])
        completed_stories = sum(
            [s['completed'] for e in epics for s in r.get_stories_for_epic(e['id']) if not s['archived']])
        in_review_stories = sum(
            [r.get_workflow(s['workflow_state_id']) == 'In Review' for e in epics for s in
             r.get_stories_for_epic(e['id']) if not s['archived']])
        total_stories = sum([not s['archived'] for e in epics for s in r.get_stories_for_epic(e['id'])])
        if total_stories == 0:
            return 0.0, 0.0
        return completed_stories / total_stories * 100, in_review_stories / total_stories * 100

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

    def get_epic_story_counts(self) -> Dict:
        bugs = {}
        features = {}

        # Loop through all epics (for key milestones, and anything under gbai)
        for epic in r.get_all_epics_in_current_sprint():
            epic_name = epic.get('name', '')
            for s in utils.filter_all_but_unneeded_and_completed(
                    r.get_stories_for_epic(epic['id'], sprint=self._current_iteration)):
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
        key_milestones = list(r.get_milestones(active=True))
        # Milestones in the 6-week time window
        post_deployment_milestones = [x for x in r.get_milestones() if
                                      self.has_ended_in_last_N_weeks(x, n_weeks=self.N_WEEKS_POST_DEPLOYMENT)]
        # "extended" means it includes the active milestones and the post deployment milestones
        key_milestones_extended = key_milestones + post_deployment_milestones
        all_milestones = key_milestones + [r.get_special_milestones()[1]]  # GBAI
        gbai_stories = r.get_all_stories_for_milestone(milestone_id=3077, sprint=self._current_iteration)

        key_stories = []
        for milestone in key_milestones_extended:
            key_stories.extend(
                utils.filter_all_but_unneeded(r.get_all_stories_for_milestone(milestone['id'], sprint=self._current_iteration))
            )

        general_bugs = utils.filter_bugs(utils.filter_all_but_unneeded(gbai_stories))
        general_features = utils.filter_features(utils.filter_all_but_unneeded(gbai_stories))

        key_bugs = utils.filter_bugs(utils.filter_all_but_unneeded(key_stories))
        key_features = utils.filter_features(utils.filter_all_but_unneeded(key_stories))

        all_bugs = key_bugs + general_bugs
        all_features = key_features + general_features

        self.populate_top_sprint_metrics(
            key_milestones_extended,
            key_bugs,
            key_features,
            general_bugs,
            general_features,
            key_stories
        )

        st.markdown("""---""")

        tab1, tab2, tab3, tab4 = st.tabs(
            ['Milestone Timelines', 'Milestones Details', 'Engineer Stories', 'Feature/Bug Distributions']
        )

        self.populate_tab_1(key_milestones_extended, tab1)
        self.populate_tab_2(key_milestones, tab2)

        all_stories = key_bugs + key_features + general_bugs + general_features

        # key_milestones: does not include general bugs & improvements
        # all_milestones_in_sprint: includes all active milestones + general bugs & improvements milestone
        # total_stories: includes all stories in "all_milestones_in_sprint"
        self.populate_tab_3(
            key_bugs,
            key_features,
            general_bugs,  # stories
            general_features,  # stories
            all_milestones,  # milestones
            all_stories,  # integer
            tab3
        )
        self.populate_tab_4(all_bugs,
                            all_features,
                            general_bugs,
                            general_features,
                            all_stories,
                            key_bugs,
                            key_features,
                            tab4)

        # Create a container for the footer
        footer_container = st.container()

        # Add your footer content to the container
        with footer_container:
            st.write("---")
            st.write("<center>Built with ❤️ by Atin</center>", unsafe_allow_html=True)

    def populate_tab_4(self,
                       all_bugs,
                       all_features,
                       gen_bugs,
                       gen_features,
                       total_stories,
                       key_bugs,
                       key_features,
                       tab4):
        with tab4:
            st.markdown('## Feature / Bugs Distributions')
            c1, c2, c3, c4, c5 = st.columns(5)
            num_total = len(total_stories)
            num_features = len(all_features)
            num_bugs = len(all_bugs)
            c1.metric("Total Stories", num_total)
            c2.metric("Features %", round(num_features / num_total * 100), 1)
            c3.metric("Bugs %", round(num_bugs / num_total * 100), 1)
            c4.metric("Features Closed", len(utils.filter_completed_and_in_review(all_features)))
            c5.metric("Bugs Squashed", len(utils.filter_completed_and_in_review(all_bugs)))
            st.markdown("""---""")

            # Row D
            st.markdown('### Stories by State')
            # Row E
            col1, col2, col3 = st.columns((4.5, 1, 4.5))
            with col1:
                story_state_distribution = self.get_state_distribution(total_stories)
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
                date_tickets_map = self.new_bugs_features_grouped_by_day(total_stories)
                total_bugs, total_features = sum(date_tickets_map.get('Bugs', [])), sum(
                    date_tickets_map.get('Features', []))
                st.write(f'Total New: {total_features + total_bugs} ({total_bugs} bugs, {total_features} features)')
                plost.bar_chart(
                    data=pd.DataFrame(date_tickets_map),
                    bar='Dates',
                    value=['Features', 'Bugs'],
                    use_container_width=True,
                )
            st.markdown("""---""")
            self.draw_feature_bug_distributions(
                gen_bugs,
                gen_features,
                key_bugs,
                key_features
            )

    def populate_tab_3(self,
                       key_bugs,
                       key_features,
                       general_bugs,
                       general_features,
                       all_milestones,
                       total_stories,
                       tab3):
        # All stories in the current iteration
        all_stories_in_sprint = key_bugs + key_features + general_bugs + general_features
        with tab3:
            # Row C
            self.draw_ownership_count_charts(general_bugs,
                                             general_features,
                                             key_bugs + key_features,
                                             all_milestones)

            st.markdown("""---""")
            all_devs = r.get_all_members()
            col1, col2, col3 = st.columns((4.5, 1, 4.5))
            with col1:
                st.markdown("### Member Stories")
                all_devs = [s.strip() for s in all_devs]
                team_member_name = st.selectbox('Team Member:', all_devs)
                stories_by_member_df = pd.DataFrame(
                    utils.filter_stories_by_member(
                        utils.filter_non_archived(all_stories_in_sprint),
                        team_member_name.strip()
                    )
                )
                st.write(self.get_prettified_story_table(stories_by_member_df), unsafe_allow_html=True)
            with col3:
                stars = self.show_sprint_stars(utils.filter_completed(total_stories))
                st.markdown('### 🌮🌮 Sprint Tacos 🌮🌮')
                for star in stars:
                    st.write(star, unsafe_allow_html=True)
            st.markdown("""---""")
            _, col2, _ = st.columns((2, 6, 2))
            with col2:
                all_epics_in_sprint = utils.filter_all_but_done_epics(r.get_all_epics_in_current_sprint())
                epic_names = set([e['name'] for e in all_epics_in_sprint])
                st.markdown('### Active Epics')
                epic_name = st.selectbox('Shows In Progress & Unstarted Stories:', epic_names)

                stories_by_epic = utils.filter_stories_by_epic(
                    # utils.filter_in_review_and_ready_for_development(total_stories),
                    utils.filter_all_but_unneeded_and_completed(total_stories),
                    epic_name.strip()
                )
                stories_by_epic_df = pd.DataFrame(stories_by_epic)
                st.write(self.get_prettified_story_table(stories_by_epic_df), unsafe_allow_html=True)

    def get_prettified_story_table(self, stories_for_epic_df):
        # TODO: Replace ID column with the Story ID
        stories_for_epic_df = self.sort_by_date(stories_for_epic_df)
        stories_for_epic_df.reset_index(drop=True, inplace=True)
        stories_for_epic_df = stories_for_epic_df.style.format(
            {'Story': self.make_clickable, 'State': self.color_green_completed})
        story_table = stories_for_epic_df.to_html()
        return story_table

    def sort_by_date(self, stories_for_epic_df):
        stories_for_epic_df['Temp_Date'] = pd.to_datetime(stories_for_epic_df['Created'])
        stories_for_epic_df = stories_for_epic_df.sort_values(by='Temp_Date', ascending=False)
        stories_for_epic_df = stories_for_epic_df.drop(columns="Temp_Date", axis=1)
        return stories_for_epic_df

    # Define a function to apply background color to cells
    def color_green_completed(self, val):
        if val == 'Ready for Development':
            color = '#F8860D'
        else:
            color = '#3BB546' if val in {'Completed', 'In Review', 'In Development'} else '#000000'
        return f"<font size='7px' color='{color}'><b>{val}</b></font>" if color != '#000000' else val

    def color_red_negative_completed(self, val):
        color = '#FF0000' if int(val) <= 0 else '#F8860D' if 1 <= int(val) <= 10 else '#3BB546'
        return f"<font size='7px' color='{color}'><b>{val}</b></font>"

    def populate_tab_2(self, key_milestones, tab2):
        with tab2:
            # Row B
            c1, c2, c3 = st.columns((1, 8, 1))
            with c2:
                st.markdown("### Active Milestones")
                st.markdown("The <b>Days Remaining</b> below signifies the days to <b>launch to Sandbox</b>.", unsafe_allow_html=True)
                df = pd.DataFrame(self.get_milestone_data_view(key_milestones))
                df = df.style.format({'Milestone': self.make_clickable,
                                      'Days Remaining': self.color_red_negative_completed})
                table = df.to_html()
                st.write(table, unsafe_allow_html=True)
                st.markdown("""---""")
                self.post_deployment_milestones(key_milestones)
                st.markdown("""---""")
                self.milestones_needing_attention(key_milestones)

    def populate_tab_1(self, key_milestones: List, tab1):
        with tab1:
            st.markdown('### Key Milestone Timelines')
            c1, c2 = st.columns((7, 3))
            with c1:
                self.draw_eta_visualization(key_milestones)

    def populate_top_sprint_metrics(self, key_milestones, key_bugs, key_features,
                                    general_bugs, general_features, key_stories):
        general_stories = general_bugs + general_features
        key_stories = key_bugs + key_features
        triage_key = utils.filter_triage(key_stories)
        addressed_key = utils.filter_completed_and_in_review(key_stories)
        triage_general = utils.filter_triage(general_bugs + general_features)
        addressed_general = utils.filter_completed_and_in_review(general_bugs + general_features)

        st.markdown('### Galileo: Sprint Metrics')
        completion_rate = utils.get_completion_rate(addressed_key + addressed_general, key_stories + general_stories)
        st.write(f'Completion Rate: <b>{completion_rate}%</b>', unsafe_allow_html=True)
        st.markdown("""---""")

        # Row 1
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col2.metric("All Stories", len(key_stories) + len(general_stories))
        col3.metric("Key Stories", len(key_stories))
        col4.metric("General Stories", len(general_stories))
        col5.metric("Features", len(key_features + general_features))
        col6.metric("Bugs", len(key_bugs + general_bugs))

        st.markdown("""---""")

        # Row 2
        col1, col2, col3, col4, col5, col6, col7, col8, col9, col10 = st.columns(10)

        col4.metric("Key Features", len(key_features))
        col5.metric("Key Bugs", len(key_bugs))
        col6.metric("Key Features Done", len(utils.filter_completed_and_in_review(key_features)))
        col7.metric("Key Bugs Done", len(utils.filter_completed_and_in_review(key_bugs)))
        col8.metric("Key Triage", len(triage_key))

        # Row 3
        col1, col2, col3, col4, col5, col6, col7, col8, col9, col10 = st.columns(10)

        col4.metric("Gen Features", len(general_features))
        col5.metric("Gen Bugs", len(general_bugs))
        col6.metric("Gen Features Done", len(utils.filter_completed_and_in_review(general_features)))
        col7.metric("Gen Bugs Done", len(utils.filter_completed_and_in_review(general_bugs)))
        col8.metric("Gen Triage", len(triage_general))

    def draw_feature_bug_distributions(
            self,
            general_bugs,
            general_features,
            key_bugs,
            key_features
    ):
        c1, c2 = st.columns((5, 5))
        with c1:
            st.markdown('#### Key Milestone Stories')
            st.markdown('###### Includes Completed stories')
            status_map = r.get_status_count(key_bugs + key_features)
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
            st.markdown('###### Includes Completed stories')
            general_bug_features = {
                'Type': ['Bugs', 'Features'],
                'Count': [len(general_bugs), len(general_features)]
            }
            plost.donut_chart(
                data=pd.DataFrame(general_bug_features),
                theta='Count',
                color='Type'
            )

    def draw_ownership_count_charts(self,
                                    general_bugs,
                                    general_features,
                                    key_stories,
                                    all_active_milestones):
        c1, c2, c3 = st.columns((4.5, 1, 4.5))
        with c1:
            st.markdown('### Key Milestone Stories')
            st.markdown('###### Includes In-progress, Unstarted & Completed stories')
            owner_map = r.get_owner_count(key_stories)
            plost.bar_chart(
                data=pd.DataFrame(owner_map),
                bar='Owner',
                direction='horizontal',
                value='Stories',
                color='#e28743',
                height=400,
                use_container_width=True,
            )
        with c3:
            # general bugs
            st.markdown('### General Bugs & Features')
            st.markdown('###### Includes In-progress, Unstarted & Completed stories')
            general_bug_owners = r.get_owner_count(general_bugs)
            general_improvements_owners = r.get_owner_count(general_features)

            bug_owners_df = pd.DataFrame(general_bug_owners)
            improvement_owners_df = pd.DataFrame(general_improvements_owners)
            merged_df = pd.merge(bug_owners_df, improvement_owners_df, on='Owner', how='outer').fillna(0)
            merged_df = merged_df.rename(
                columns={'Stories_x': 'Bugs', 'Stories_y': 'Features'}
            )
            plost.bar_chart(
                data=merged_df,
                bar='Owner',
                direction='horizontal',
                value=['Bugs', 'Features'],
                height=400,
                use_container_width=True,
            )
        st.markdown("""---""")
        st.markdown('### Active Sprint Epics')
        st.markdown('###### Shows only In Progress & Unstarted Stories')
        c1, c2, c3 = st.columns((2, 6, 2))
        with c2:
            # Grouped Bar of Features & Bugs - by Epics
            all_active_epics = []
            for m in all_active_milestones:
                all_active_epics.extend(r.get_epics_for_milestone(m['id']))
            epic_story_count_map = self.get_epic_story_counts()
            plost.bar_chart(
                data=pd.DataFrame(epic_story_count_map),
                bar='name',
                direction='horizontal',
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
                col = 'red' if progress_percent > 85 else 'green'
                st.markdown(
                    f"<b>{milestone['name']}</b> (<font color='{col}'><b>{progress_percent}%</b></font> elapsed)",
                    unsafe_allow_html=True)
            with y:
                if progress_percent >= 120:
                    st.markdown(f"""
                            <div style='background-color: #DBDBDB; height: 10px; border-radius: 5px;'>
                                <div style='background-color: #4c0105; height: 10px; width: {progress_percent}%; border-radius: 5px;'></div>
                            </div>
                        """, unsafe_allow_html=True)
                elif progress_percent >= 85:
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

    def post_deployment_milestones(self, active_milestones):
        st.markdown('### Milestones in Post Deployment')
        st.markdown(f'<b>Should be in Sandbox</b>, <b>launched to customers</b>, '
                    f'in the {self.N_WEEKS_POST_DEPLOYMENT}-week phase of fixing bugs arising via customer usage.',
                    unsafe_allow_html=True)
        df = self.get_past_milestones(active_milestones, n_weeks=self.N_WEEKS_POST_DEPLOYMENT)
        df = df.style.format({'Milestone': self.make_clickable, 'Days Remaining': self.color_red_negative_completed})
        df_html = df.to_html()
        st.write(df_html, unsafe_allow_html=True)

    def milestones_needing_attention(self, active_milestones):
        st.markdown('### Milestones Needing Attention')
        st.markdown(f'<b>Concern Zone</b>: Between {self.N_WEEKS_POST_DEPLOYMENT} and {self.N_WEEKS_NEEDS_ATTENTION} weeks '
                    'from Sandbox/Customer Launch', unsafe_allow_html=True)
        df1 = self.get_past_milestones(active_milestones, n_weeks=self.N_WEEKS_NEEDS_ATTENTION)
        df2 = self.get_past_milestones(active_milestones, n_weeks=self.N_WEEKS_POST_DEPLOYMENT)
        # merge the two dataframes on all columns
        merged = df1.merge(df2, how='outer', indicator=True)
        # filter the rows that are only in df1
        filtered = merged[merged['_merge'] == 'left_only'][df1.columns]
        filtered = filtered.style.format({'Milestone': self.make_clickable, 'State': self.color_green_completed})
        filtered_html = filtered.to_html()
        st.write(filtered_html, unsafe_allow_html=True)

    def get_past_milestones(self, active_milestones, n_weeks):
        active_ms_set = set()
        for am in active_milestones:
            active_ms_set.add(am['id'])
        # milestones that have passed the dates,
        problematic_milestones = []
        problematic_completion_percent = []
        problematic_in_review_percent = []
        all_milestones = list(r.get_milestones())
        for m in all_milestones:
            cp_tuple = self.get_story_completion_percentage(m)
            if m['id'] not in active_ms_set and self.has_ended_in_last_N_weeks(m, n_weeks=n_weeks) and cp_tuple[
                0] <= 95:
                problematic_milestones.append(m)
                problematic_completion_percent.append("{}%".format(str(round(cp_tuple[0], 2))))
                problematic_in_review_percent.append("{}%".format(str(round(cp_tuple[1], 2))))
        # list of non active milestones
        pdf = pd.DataFrame(self.get_milestone_data_view(problematic_milestones))
        return pdf

    def make_clickable(self, val):
        split_val = val.split('###')
        return "<a href={} target='_blank'>{}</a>".format(split_val[1], split_val[0])

    def get_milestone_data_view(self, milestones):
        milestone_names = []
        started_dates = []
        dev_complete_dates = []
        sandbox_deployment_dates = []
        post_deployment_fix_dates = []
        num_epics = []
        num_stories = []
        days_elapsed = []
        days_to_target = []
        problematic_completion_percent = []
        problematic_in_review_percent = []

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
            sandbox_date = None
            if milestone['started_at_override'] is not None:
                started_date = datetime.fromisoformat(milestone['started_at_override'].replace('Z', '+00:00'))
                started_dates.append(started_date.strftime('%b %-d'))
            else:
                started_dates.append(None)

            if milestone['completed_at_override'] is not None:
                sandbox_date = datetime.fromisoformat(milestone['completed_at_override'].replace('Z', '+00:00'))
                sandbox_deployment_dates.append(sandbox_date.strftime('%b %-d'))
                dev_complete_dates.append((utils.get_dev_complete_date(sandbox_date)).strftime('%b %-d'))
                post_deployment_fix_dates.append((utils.get_post_deployment_date(sandbox_date)).strftime('%b %-d'))
                days_to_target.append(
                    (sandbox_date.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days + 1)
                if started_date is not None:
                    period = datetime.now().replace(tzinfo=timezone.utc) - started_date
                    days_elapsed.append(period.days)
            else:
                sandbox_deployment_dates.append(None)
                days_to_target.append(None)

            if (started_date is None) or (started_date is None and sandbox_date is None):
                days_elapsed.append(0)

            cp_tuple = self.get_story_completion_percentage(milestone)
            problematic_completion_percent.append("{}%".format(str(round(cp_tuple[0], 2))))
            problematic_in_review_percent.append("{}%".format(str(round(cp_tuple[1], 2))))

        days_elapsed = [int(d) for d in days_elapsed]
        data = {
            'Milestone': milestone_names,
            'Started At': started_dates,
            'Dev Complete': dev_complete_dates,
            'Sandbox Deploy': sandbox_deployment_dates,
            'Post Deploy Fixes': post_deployment_fix_dates,
            'Epics': num_epics,
            'Stories': num_stories,
            'Days Elapsed': days_elapsed,
            'Days Remaining': days_to_target,
            'Completed': problematic_completion_percent,
            'In Review': problematic_in_review_percent,
        }
        return data

    def new_bugs_features_grouped_by_day(self, stories):
        stories = utils.filter_stories_by_sprint(stories, self._current_iteration)
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
    st.sidebar.header('Sprint Dashboard')
    st.session_state['iteration_name'] = st.sidebar.selectbox('Sprint Name:', tuple(sprints))
    sdb.create_dashboard()


if __name__ == '__main__':
    main()
