from dash import html, dcc, callback
import dash
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import logging
from dateutil.relativedelta import *  # type: ignore
import plotly.express as px
from pages.utils.graph_utils import color_seq
from queries.company_query import company_query as cq
import io
from cache_manager.cache_manager import CacheManager as cm
from pages.utils.job_utils import nodata_graph
import time
import datetime as dt

PAGE = "company"
VIZ_ID = "company-associated-activity"

paramter_1 = "company-contributions-required"
paramter_2 = "checks"


gc_compay_associated_activity = dbc.Card(
    [
        dbc.CardBody(
            [
                html.H3(
                    "Company Associated Activity",
                    className="card-title",
                    style={"textAlign": "center"},
                ),
                dbc.Popover(
                    [
                        dbc.PopoverHeader("Graph Info:"),
                        dbc.PopoverBody(
                            "This graph counts the number of contributions that COULD be linked to each company.\n\
                            The methodology behind this is to take each associated email to someones github account\n\
                            and link the contributions to each as it is unknown which initity the actvity was done for."
                        ),
                    ],
                    id=f"{PAGE}-popover-{VIZ_ID}",
                    target=f"{PAGE}-popover-target-{VIZ_ID}",  # needs to be the same as dbc.Button id
                    placement="top",
                    is_open=False,
                ),
                dcc.Loading(
                    dcc.Graph(id=VIZ_ID),
                ),
                dbc.Form(
                    [
                        dbc.Row(
                            [
                                dbc.Label(
                                    "Contributions Required:",
                                    html_for=f"{PAGE}-{paramter_1}-{VIZ_ID}",
                                    width={"size": "auto"},
                                ),
                                dbc.Col(
                                    dbc.Input(
                                        id=f"{PAGE}-{paramter_1}-{VIZ_ID}",
                                        type="number",
                                        min=1,
                                        max=100,
                                        step=1,
                                        value=10,
                                        size="sm",
                                    ),
                                    className="me-2",
                                    width=2,
                                ),
                                dbc.Col(
                                    [
                                        dbc.Checklist(
                                            id=f"{PAGE}-{paramter_2}-{VIZ_ID}",
                                            options=[
                                                {"label": "Exclude gmail", "value": "gmail"},
                                                {"label": "Exclude Other", "value": "other"},
                                            ],
                                            value=[""],
                                            inline=True,
                                        ),
                                    ]
                                ),
                                dbc.Col(
                                    dbc.Button(
                                        "About Graph",
                                        id=f"{PAGE}-popover-target-{VIZ_ID}",
                                        color="secondary",
                                        size="sm",
                                    ),
                                    width="auto",
                                    style={"paddingTop": ".5em"},
                                ),
                            ],
                            align="center",
                        ),
                        dbc.Row(
                            [
                                html.Div(id=f"{PAGE}-SliderContainer-{VIZ_ID}"),
                            ],
                            align="center",
                        ),
                    ]
                ),
            ]
        )
    ],
)

# callback for graph info popover
@callback(
    Output(f"{PAGE}-popover-{VIZ_ID}", "is_open"),
    [Input(f"{PAGE}-popover-target-{VIZ_ID}", "n_clicks")],
    [State(f"{PAGE}-popover-{VIZ_ID}", "is_open")],
)
def toggle_popover(n, is_open):
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE}-SliderContainer-{VIZ_ID}", "children"),
    [
        Input("repo-choices", "data"),
    ],
    # background=True,
)
def create_slider(repolist):
    # wait for data to asynchronously download and become available.
    cache = cm()
    df = cache.grabm(func=cq, repos=repolist)
    while df is None:
        time.sleep(1.0)
        df = cache.grabm(func=cq, repos=repolist)

    # get date value for first contribution
    df["created"] = pd.to_datetime(df["created"], utc=True)
    df = df.sort_values(by="created", axis=0, ascending=True)
    base = df.iloc[0]["created"]

    date_picker = (
        dcc.DatePickerRange(
            id=f"{PAGE}-date-picker-range-{VIZ_ID}",
            min_date_allowed=base,
            max_date_allowed=dt.date.today(),
            clearable=True,
        ),
    )
    return date_picker


# callback for Company Affiliation by Github Account Info graph
@callback(
    Output(VIZ_ID, "figure"),
    [
        Input("repo-choices", "data"),
        Input(f"{PAGE}-{paramter_2}-{VIZ_ID}", "value"),
        Input(f"{PAGE}-{paramter_1}-{VIZ_ID}", "value"),
        Input(f"{PAGE}-date-picker-range-{VIZ_ID}", "start_date"),
        Input(f"{PAGE}-date-picker-range-{VIZ_ID}", "end_date"),
    ],
    background=True,
    prevent_initial_call=True,
)
def compay_associated_activity_graph(repolist, checks, num, start_date, end_date):

    # wait for data to asynchronously download and become available.
    cache = cm()
    df = cache.grabm(func=cq, repos=repolist)
    while df is None:
        time.sleep(1.0)
        df = cache.grabm(func=cq, repos=repolist)

    start = time.perf_counter()
    logging.debug(f"{VIZ_ID}- START")

    # test if there is data
    if df.empty:
        logging.debug(f"{VIZ_ID} - NO DATA AVAILABLE")
        return nodata_graph

    # function for all data pre processing, COULD HAVE ADDITIONAL INPUTS AND OUTPUTS
    df = process_data(df, checks, num, start_date, end_date)

    fig = create_figure(df)

    logging.debug(f"{VIZ_ID} - END - {time.perf_counter() - start}")
    return fig


def process_data(df: pd.DataFrame, checks, num, start_date, end_date):
    """Implement your custom data-processing logic in this function.
    The output of this function is the data you intend to create a visualization with,
    requiring no further processing."""

    # convert to datetime objects rather than strings
    df["created"] = pd.to_datetime(df["created"], utc=True)

    # order values chronologically by COLUMN_TO_SORT_BY date
    df = df.sort_values(by="created", axis=0, ascending=True)

    # filter values based on date picker
    if start_date is not None:
        df = df[df.created >= start_date]
    if end_date is not None:
        df = df[df.created <= end_date]

    # creates list of emails for each contribution and flattens list result
    emails = df.email_list.str.split(" , ").explode("email_list").tolist()

    # remove any entries not in email format
    emails = [x for x in emails if "@" in x]

    # creates list of email domains from the emails list
    email_domains = [x[x.rindex("@") + 1 :] for x in emails]

    # creates df of domains and counts
    df = pd.DataFrame(email_domains, columns=["domains"]).value_counts().to_frame().reset_index()

    df = df.rename(columns={0: "occurances"})

    # changes the name of the company if under a certain threshold
    df.loc[df.occurances <= num, "domains"] = "Other"

    # groups others together for final counts
    df = (
        df.groupby(by="domains")["occurances"]
        .sum()
        .reset_index()
        .sort_values(by=["occurances"], ascending=False)
        .reset_index(drop=True)
    )

    # removes entries with gmail or other if checked
    if "gmail" in checks:
        df = df[df.domains != "gmail.com"]
    if "other" in checks:
        df = df[df.domains != "Other"]

    return df


def create_figure(df: pd.DataFrame):

    # graph generation
    fig = px.pie(df, names="domains", values="occurances", color_discrete_sequence=color_seq)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label} <br>Contribution: %{value}<br><extra></extra>",
    )

    return fig
