import streamlit as st
import pandas as pd
from pandas.io.json import json_normalize
from pathlib import Path
import json
import time
import numpy as np
import requests

from distutils import errors
from distutils.log import error
import altair as alt
from itertools import cycle

from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, DataReturnMode, JsCode

siteHeader = st.container()

def poll_job(s, redash_url, job):
    # TODO: add timeout
    while job['status'] not in (3,4):
        response = s.get('{}/api/jobs/{}'.format(redash_url, job['id']))
        job = response.json()['job']
        time.sleep(1)

    if job['status'] == 3:
        return job['query_result_id']
    
    return None


def get_fresh_query_result(redash_url, query_id, api_key):
    s = requests.Session()
    s.headers.update({'Authorization': 'Key {}'.format(api_key)})

    payload = dict(max_age=0)

    response = s.post('{}/api/queries/{}/results'.format(redash_url, query_id), data=json.dumps(payload))

    if response.status_code != 200:
        raise Exception('Refresh failed.')

    result_id = poll_job(s, redash_url, response.json()['job'])

    if result_id:
        response = s.get('{}/api/queries/{}/results/{}.json'.format(redash_url, query_id, result_id))
        if response.status_code != 200:
            raise Exception('Failed getting results.')
    else:
        raise Exception('Query execution failed.')

    return response.json()['query_result']['data']['rows']

apps = pd.DataFrame.from_dict(get_fresh_query_result(st.secrets['redash_url'], st.secrets['clim_app_query_id'], st.secrets['redash_key']))
votes = pd.DataFrame.from_dict(get_fresh_query_result(st.secrets['redash_url'], st.secrets['clim_votes_query_id'], st.secrets['redash_key']))
apps['destination_wallet'] = apps['wallet_address']

complete_dataset =  pd.merge(votes, apps, how="left", on="destination_wallet")
# eth to usd - 1507.09
# dai to usd - 0.998979
# complete_dataset['amount_usd'] = [df['amount'] if x =='ETH' else df['amount']*0.998979 for x in df['token']]

amount_usd = []
for i in range(len(complete_dataset['token'])):
    if complete_dataset['token'][i] == 'ETH':
        amount_usd.append(complete_dataset['amount'][i]*1507.09)
    elif complete_dataset['token'][i] == 'DAI':
        amount_usd.append(complete_dataset['amount'][i]*0.998979)

complete_dataset['amount_usd'] = amount_usd

# complete_dataset['amount_usd'] = np.where(complete_dataset['token']=='Music', complete_dataset['amount']*1507.09,complete_dataset['amount']*0.998979)
main_df = complete_dataset.tail()

print(complete_dataset.sort_values('created_at').groupby(['created_at','project_title', 'token']).sum())

with siteHeader:
    st.title('Web3 Open Source Software Analysis')
    st.text('In this project we are going to breakdown analysis of the round contributions and identify possible sybil behaviour')

    votes_dai = votes[votes['token'] == 'DAI']
    votes_eth = votes[votes['token'] == 'ETH']

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Grant applications", f"{apps['project_id'].nunique()}")
    col2.metric("Unique contributors", f"{votes['source_wallet'].nunique()}")
    col3.metric("No. of contributions", f"{votes['id'].count()}")
    col4.metric("Lastest contribution", f"{votes['created_at'].max()}")

    col1_1, col2_1, col3_1, col4_1 = st.columns(4)
    col1_1.metric("Avg contribution (ETH)", str(votes_eth['amount'].mean().round(5)))
    col2_1.metric("Avg contribution (DAI)", str(votes_dai['amount'].mean().round(5)))
    col3_1.metric("Sum of contribution in ETH", str(votes_eth['amount'].sum().round(2)))
    col4_1.metric("Sum of contributions in DAI", str(votes_dai['amount'].sum().round(2)))

    
    gb = GridOptionsBuilder.from_dataframe(main_df)
   
    gb.configure_column("amount", type=["numericColumn","numberColumnFilter","customNumericFormat"], precision=5, aggFunc='sum')
    gb.configure_column("amount_usd", type=["numericColumn","numberColumnFilter","customNumericFormat"], precision=2, aggFunc='sum')
    gb.configure_column("created_at", type=["dateColumnFilter","customDateTimeFormat"], custom_format_string='yyyy-MM-dd HH:mm zzz', pivot=True)

    #configures last row to use custom styles based on cell's value, injecting JsCode on components front end
    cellsytle_jscode = JsCode("""
    function(params) {
        if ((params.value !== undefined) && (params.value !== null)) {
            return {
                'color': 'black',
                'backgroundColor': 'white'
            }
        } else {
            return {
                'color': 'white',
                'backgroundColor': 'darkred'
            }
        }
    };
    """)

    gb.configure_column("previous_funding", cellStyle=cellsytle_jscode)

    gb.configure_selection('multiple')
    gb.configure_selection('multiple', use_checkbox=True, groupSelectsChildren=True, groupSelectsFiltered=True)

    gb.configure_grid_options(domLayout='normal')
    gridOptions = gb.build()


    grid_height = 300
    return_mode_value = 'FILTERED'
    update_mode_value = 'GRID_CHANGED'

    grid_response = AgGrid(
        complete_dataset.head(200), 
        gridOptions=gridOptions,
        height=grid_height, 
        width='100%',
        data_return_mode=return_mode_value, 
        update_mode=update_mode_value,
        allow_unsafe_jscode=True #Set it to True to allow jsfunction to be injected
        )

    df = grid_response['data']
    # print(df)
    selected = grid_response['selected_rows']
    # print(selected)
    # selected_df = pd.DataFrame(selected)
    # selected_df.index = selected_df.index.astype(int)
    selected_df = pd.DataFrame(selected).apply(pd.to_numeric)

    with st.spinner("Displaying results..."):
        #displays the chart
        df['created_at'] = pd.to_datetime(df['created_at'])
        chart_data = df.loc[:,['created_at','amount_usd']].assign(source='total')

        if not selected_df.empty :
            selected_df['amount'].apply(pd.to_numeric, errors='coerce')
            selected_df['amount_usd'].apply(pd.to_numeric, errors='coerce')
            selected_df['created_at'].apply(pd.to_datetime, errors='coerce')
            print(selected_df)

            # selected_data['created_at'] = pd.to_datetime(selected['created_at'])
            selected_data = selected_df.loc[:,['created_at','amount_usd']].assign(source='selection')
            print(selected_data)
            chart_data = pd.concat([chart_data, selected_data])
            print(chart_data)

        # chart_data = pd.melt(chart_data, id_vars=['source'], var_name="date", value_name="quantity")
        #st.dataframe(chart_data)
        chart = alt.Chart(data=chart_data).mark_bar().encode(
            x=alt.X("monthdate(created_at):O", title='Date'),
            y=alt.Y("sum(amount_usd):Q"),
            color=alt.Color('source:N', scale=alt.Scale(domain=['total', 'selection'])),
        )

        st.header("Amount donated over time ")
        st.markdown("""
        This chart is built with data returned from the grid. The rows that are selected are identified as shown in the legend.
        """)

        st.altair_chart(chart, use_container_width=True)


    title_list = df.project_title.unique()
    titles = [x for x in title_list if not pd.isnull(x)]

    with st.spinner("Displaying results..."):
        
        #displays the chart
        df['created_at'] = pd.to_datetime(df['created_at'])
        chart_data = df.loc[:,['project_title', 'created_at','amount_usd']]

        # chart_data = pd.melt(chart_data, id_vars=['source'], var_name="date", value_name="quantity")
        #st.dataframe(chart_data)

        cd = chart_data.groupby(['project_title'], as_index=False)['amount_usd'].sum()

        top_10_projects = cd['project_title'].head(10)
        chart_data = chart_data[chart_data['project_title'].isin(top_10_projects)]

        titles = chart_data.project_title.unique()

        chart = alt.Chart(data=chart_data).mark_bar().encode(
            x=alt.X("monthdate(created_at):O", title='Date'),
            y=alt.Y("sum(amount_usd):Q"),
            color=alt.Color('project_title:N', scale=alt.Scale(domain=titles)),
        )

        st.header("Amount donated over time by project")
        st.markdown("""
        This chart is built with data returned from the grid. The rows that are selected are identified as shown in the legend.
        """)

        st.altair_chart(chart, use_container_width=True)




