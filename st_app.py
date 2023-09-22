import streamlit as st

import requests
import math as mt
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO
import re
from datetime import date, datetime, timedelta
import icalendar as ical

st.set_page_config(page_title="Physics Timetables at Sapienza")

st.title("Timetables - Department of Physics")

st.markdown(
    """
![Sapienza University of Rome logo](https://www.phys.uniroma1.it/fisica/sites/all/themes/sapienza_bootstrap/logo.png)

This app allows you to generate timetables for
Sapienza University of Rome lectures at the Department of
Physics. It is currently updated to [the 21/09 version](https://www.phys.uniroma1.it/fisica/sites/default/files/allegati/_orario_I%20semestre_fs2324-v23_2.html).
The app is maintained by [Shoichi Yip](https://github.com/shoyip).
"""
)


def to_date(date_string):
    return datetime.strptime(date_string, "%d/%m/%Y")


semester_start = to_date("25/09/2023")
semester_end = to_date("23/12/2023")
festivities = list(
    map(
        to_date,
        [
            "01/11/2023",
            "08/12/2023",
            "23/12/2023",
            "24/12/2023",
            "25/12/2023",
            "26/12/2023",
            "27/12/2023",
            "28/12/2023",
            "29/12/2023",
            "30/12/2023",
            "31/12/2023",
            "01/01/2024",
            "02/01/2024",
            "03/01/2024",
            "04/01/2024",
            "05/01/2024",
        ],
    )
)
rooms = [
    "Amaldi",
    "Conversi",
    "Rasetti",
    "Careri",
    "Cabibbo",
    "LabSS-LabAstro",
    "Aula3",
    "Aula4",
    "Aula6",
    "Aula7",
    "Aula8",
    "Aula17",
    "Aula17A",
    "Aula17B",
    "Aula17C",
    "LabCalcA",
    "LabCalcB",
    "LabCalcC",
    "LabTermoA",
    "LabTermoB",
    "LabTermo",
]


def load_data(data_url):
    p = requests.get(data_url)
    s = BeautifulSoup(p.content, "html.parser")

    cohorts = ["T1", "T2", "T3", "M1", "M2"]
    dfs = {}
    for cohort in cohorts:
        r = s.find("a", {"name": cohort})
        ht = str(r.findNext("table"))
        cdf = pd.read_html(StringIO(ht), header=0)[0]
        cdf["Title"] = cdf.Insegnamento + " - " + cdf.Docente + " [" + cohort + "]"
        cdf.drop(columns=["Insegnamento", "Docente"], inplace=True)
        dfs[cohort] = cdf

    df = pd.concat([df for df in dfs.values()], axis=0)

    return df


def clean_str(tt_str):
    l = {" (a)": "A", " (b)": "B", " (c)": "C"}
    pattern = "|".join(sorted(re.escape(k) for k in l))
    clean_str = re.sub(pattern, lambda m: l.get(m.group(0)), tt_str)
    return clean_str


def get_ttrecords(tt_string):
    if type(tt_string) == float:
        return []
    tt_string = clean_str(tt_string)
    records = []
    nxt_start, nxt_end = False, False
    for word in tt_string.split(" "):
        if nxt_start:
            records[-1]["start_date"] = datetime.strptime(word, "%d/%m/%y")
            nxt_start = False
        elif nxt_end:
            records[-1]["end_date"] = datetime.strptime(word, "%d/%m/%y")
            nxt_end = False
        elif word in rooms:
            records.append({"room": word})
        elif word == "dal":
            nxt_start = True
            continue
        elif word == "al":
            nxt_end = True
            continue
        elif bool(re.fullmatch("\d{0,2}-\d{0,2}", word)):
            records[-1]["start_hour"] = int(word.split("-")[0])
            records[-1]["end_hour"] = int(word.split("-")[1])
            # this breaks if hours are not in integer format (i.e. half hours)
    return records


def get_reclist(input_df):
    # transform raw df in list of records
    #input_df.reset_index(drop=False, inplace=True)
    st.write(input_df)
    reclist = list(
        pd.concat(
            [
                input_df["Title"],
                input_df.drop(columns=["Title"]).applymap(get_ttrecords),
            ],
            axis=1,
        )
        .melt("Title")
        .to_records(index=False)
    )
    return reclist


def get_first_day(start_date, day_of_week):
    # given a start_date get the next available date for the specified day of the week
    current_date = start_date
    while current_date.weekday() != day_of_week:
        current_date += timedelta(days=1)
    return current_date


def get_cal(input_df, semester_start, semester_end):
    reclist = get_reclist(input_df)
    days_of_week = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
    dow_str_num = {dow_str: idx for idx, dow_str in enumerate(days_of_week)}
    cal = ical.Calendar()
    cal.add(
        "prodid",
        "-//Calendario Didattico Sapienza Dipartimento di Fisica//www.uniroma1.it",
    )
    cal.add("version", "1.0")

    for rec in reclist:
        if len(rec[2]) > 0:
            title = rec[0]
            day_of_week = dow_str_num[rec[1]]
            entry = rec[2]
            # propagate start date of second entry option as end date of first entry option
            if len(entry) == 2:
                entry[0]["end_date"] = entry[1]["start_date"]
            # now let us create the events
            for entry_option in entry:
                if "start_date" in entry_option:
                    start_date = entry_option["start_date"]
                    event_date = get_first_day(start_date, day_of_week)
                else:
                    event_date = get_first_day(semester_start, day_of_week)

                start_hour = entry_option["start_hour"]
                end_hour = entry_option["end_hour"]

                start_dt = event_date + timedelta(hours=start_hour)
                end_dt = event_date + timedelta(hours=end_hour)

                if ("end_date" in entry_option):
                    if (entry_option["end_date"] < semester_end):
                        end_recurrence = entry_option["end_date"]
                else:
                    end_recurrence = semester_end

                ev = ical.Event()
                ev.add("name", title)
                ev.add("summary", title)
                ev.add("description", title)
                ev.add("location", entry_option["room"])
                ev.add("dtstart", start_dt)
                ev.add("dtend", end_dt)
                ev.add("rrule", {"freq": "weekly", "until": end_recurrence})
                # exdates should have the SAME format of dtstart and same HOUR as well (doesn't work)
                # for festivity in festivities:
                # ev.add('exdate', festivity + timedelta(hours=start_hour))
                cal.add_component(ev)
    return cal


def get_timetable(input_df):
    list_of_recs = get_reclist(input_df)

    # intialize timetable with blank strings
    lovs = ["" for i in range(24)]
    days_of_week = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
    timetable = pd.DataFrame({day_of_week: lovs for day_of_week in days_of_week})

    # now fill the timetable with correct lecture records
    for rec in list_of_recs:
        # if record is not nan
        if rec[2] != []:
            # extract variables of interest
            title = rec[0]
            day_of_week = rec[1]
            # for every option of hour
            for entry_option in rec[2]:
                start_hour = entry_option["start_hour"]
                end_hour = entry_option["end_hour"]
                room = entry_option["room"]
                # now for each hour of the lecture assign the string to the corresponding cell
                # the string contains title, room and informations about when the timetable is effective
                for hour in range(start_hour, end_hour):
                    timetable.loc[hour, day_of_week] += title + " in " + room + " "
                    if "start_date" in entry_option:
                        timetable.loc[hour, day_of_week] += (
                            "dal "
                            + entry_option["start_date"].strftime("%d/%m/%Y")
                            + " al "
                            + entry_option["end_date"].strftime("%d/%m/%Y")
                        )
                    timetable.loc[hour, day_of_week] += "\n"

    return timetable.loc[
        8:20, days_of_week[0:5]
    ]  # return only meaningful days and hours


raw_df = load_data(
    # "https://www.phys.uniroma1.it/fisica/sites/default/files/allegati/Orario_I_semestre_23_24.html"
    "https://www.phys.uniroma1.it/fisica/sites/default/files/allegati/_orario_I%20semestre_fs2324-v23_2.html"
)
raw_df.set_index("Title", inplace=True)

# st.subheader("Data")
# st.write(raw_df)

# st.subheader("Multiselect")
course_list = [title for title in raw_df.index]

# st.subheader("Tabella Orari")

# st.write(df_cal)

# cal_md = df_cal.to_markdown(index=False)
# st.markdown(cal_md)


def set_state(i):
    st.session_state.stage = i


def generate_ttxls(df_cal, tt_filename):
    df_cal.to_excel(tt_filename, sheet_name="Timetable", header=True, index=True)

def generate_ical(input_df, ical_filename, semester_start, semester_end):
    cal = get_cal(input_df, semester_start, semester_end)
    with open(ical_filename, 'wb') as f:
        f.write(cal.to_ical())

if "stage" not in st.session_state:
    st.session_state.stage = 'initial'

options = st.multiselect(
    "Choose the courses you would like to include in your timetable.", course_list
)

my_df = raw_df.loc[options]

tab1, tab2 = st.tabs(["Excel", "iCal"])

with tab1:
    st.header("Generate Excel Table")
    df_cal = get_timetable(my_df.reset_index(drop=False))

    st.button(":boom: Generate table", on_click=set_state, args=['excel1'])

    if st.session_state.stage == 'excel1':
        st.table(df_cal)
        st.button(":bar_chart: Generate Timetable Excel", on_click=set_state, args=['excel2'])

    if st.session_state.stage == 'excel2':
        generate_ttxls(df_cal, "timetable.xlsx")
        with open("timetable.xlsx", "rb") as f:
            st.download_button(":arrow_down: Download Timetable Excel", f, "timetable.xlsx")

with tab2:
    st.header("Generate iCal file")
    st.button(":boom: Generate iCal file", on_click=set_state, args=['ical1'])

    if st.session_state.stage == 'ical1':
        generate_ical(my_df.reset_index(drop=False), 'semester_calendar.ics', semester_start, semester_end)
        with open("semester_calendar.ics", "rb") as f:
            st.download_button(":calendar: Download iCal file", f, "semester_calendar.ics")