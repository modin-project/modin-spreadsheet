from modin_spreadsheet import (
    SpreadsheetWidget,
    set_defaults,
    show_grid,
    on as widget_on,
)
from traitlets import All
import numpy as np

# import pandas as pd
import modin.pandas as pd
import json

# Compares values between two modin dataframes. NaNs in the same positions
# are considered equal, whereas in the equals function they are not.
# pandas.testing.assert_frame_equals doesn't work with modin dataframes.
def assert_modin_frame_equals(df, expected):
    comparison_normal = df == expected
    comparison_NaN = df.isna() == expected.isna()
    assert all(comparison_normal | comparison_NaN)

def create_df():
    return pd.DataFrame(
        {
            "A": [1.0, 2.0, 1.0, 3.0],
            "Date": [pd.Timestamp("20130102"), pd.Timestamp("20140102"), pd.Timestamp("20140202"), pd.Timestamp("20130102")],
            "C": pd.Series([1, 2, 3, 4], index=list(range(4)), dtype="float32"),
            "D": np.array([3, 2, 1, 4], dtype="int32"),
            "E": pd.Categorical(["test", "train", "foo", "bar"]),
            "F": ["foo", "bar", "buzz", "fox"],
            "Mixed": [pd.Timestamp("2017-02-02"), np.nan, 1e10, "hey"],
            1: [5, 4, "hello", 1],
        }
    )


def create_large_df(size=10000):
    large_df = pd.DataFrame(np.random.randn(size, 4), columns=list("ABCD"))
    large_df["B (as str)"] = large_df["B"].map(lambda x: str(x))
    return large_df


def create_multi_index_df():
    arrays = [
        ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
        ["one", "two", "one", "two", "one", "two", "one", "two"],
    ]
    return pd.DataFrame(np.random.randn(8, 4), index=arrays)


def create_interval_index_df():
    td = np.cumsum(np.random.randint(1, 15 * 60, 1000))
    start = pd.Timestamp("2017-04-17")
    df = pd.DataFrame(
        [(start + pd.Timedelta(seconds=d)) for d in td],
        columns=["time"],
        dtype="M8[ns]",
    )

    df["time_bin"] = np.cumsum(np.random.randint(1, 15 * 60, 1000))
    return df


def init_event_history(event_names, widget=None):
    event_history = []

    def on_change(event, spreadsheet_widget):
        event_history.append(event)

    if widget is not None:
        widget.on(event_names, on_change)
    else:
        widget_on(event_names, on_change)

    return event_history


def test_edit_date():
    view = SpreadsheetWidget(df=create_df())
    check_edit_success(
        view,
        "Date",
        3,
        pd.Timestamp("2013-01-02 00:00:00"),
        "2013-01-02T00:00:00.000Z",
        pd.Timestamp("2013-01-16 00:00:00"),
        "2013-01-16T00:00:00.000Z",
    )


# TODO: Fix once get option or display precision getter implemented
# def test_edit_multi_index_df():
#     df_multi = create_multi_index_df()
#     df_multi.index.set_names("first", level=0, inplace=True)
#     view = SpreadsheetWidget(df=df_multi)
#     old_val = df_multi.loc[("bar", "two"), 1]
#
#     check_edit_success(
#         view,
#         1,
#         1,
#         old_val,
#         round(old_val, pd.get_option("display.precision") - 1),
#         3.45678,
#         3.45678,
#     )


def check_edit_success(
    widget,
    col_name,
    row_index,
    old_val_obj,
    old_val_json,
    new_val_obj,
    new_val_json,
):

    event_history = init_event_history("cell_edited", widget)

    grid_data = json.loads(widget._df_json)["data"]
    assert grid_data[row_index][str(col_name)] == old_val_json

    widget._handle_view_msg_helper(
        {
            "column": col_name,
            "row_index": row_index,
            "type": "edit_cell",
            "unfiltered_index": row_index,
            "value": new_val_json,
        }
    )

    expected_index_val = widget._df.index[row_index]
    assert event_history == [
        {
            "name": "cell_edited",
            "index": expected_index_val,
            "column": col_name,
            "old": old_val_obj,
            "new": new_val_obj,
            "source": "gui",
        }
    ]
    assert widget._df[col_name][row_index] == new_val_obj

    # call _update_table so the widget updates _df_json
    widget._update_table(fire_data_change_event=False)
    grid_data = json.loads(widget._df_json)["data"]
    assert grid_data[row_index][str(col_name)] == new_val_json


def test_edit_number():
    df = create_df()
    view = SpreadsheetWidget(df=df)
    old_val = df.loc[2, "D"]
    for idx in range(-10, 10, 1):
        check_edit_success(view, "D", 2, old_val, old_val, idx, idx)
        old_val = idx


def test_add_row_button():
    df = create_df()
    widget = SpreadsheetWidget(df=df)
    event_history = init_event_history("row_added", widget=widget)

    widget._handle_view_msg_helper({"type": "add_row"})

    assert event_history == [{"name": "row_added", "index": 4, "source": "gui"}]

    # make sure the added row in the internal dataframe duplicates the
    # last row and increments the index
    added_index = event_history[0]["index"]
    expected_values = df.iloc[3,:]
    expected_values["modin_spreadsheet_unfiltered_index"] = 4
    sort_idx = widget._df.loc[added_index].index
    assert (widget._df.loc[added_index] == expected_values[sort_idx]).all()


def test_remove_row_button():
    widget = SpreadsheetWidget(df=create_df())
    event_history = init_event_history(
        ["row_removed", "selection_changed"], widget=widget
    )

    selected_rows = [1, 2]
    widget._handle_view_msg_helper({"rows": selected_rows, "type": "change_selection"})

    widget._handle_view_msg_helper({"type": "remove_row"})

    assert event_history == [
        {
            "name": "selection_changed",
            "old": [],
            "new": selected_rows,
            "source": "gui",
        },
        {"name": "row_removed", "indices": selected_rows, "source": "gui"},
    ]


def test_mixed_type_column():
    df = pd.DataFrame({"A": [1.2, "xy", 4], "B": [3, 4, 5]})
    df = df.set_index(pd.Index(["yz", 7, 3.2]))
    view = SpreadsheetWidget(df=df)
    view._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "A", "sort_ascending": True}
    )
    view._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": "A", "search_val": None}
    )


def test_nans():
    df = pd.DataFrame([(pd.Timestamp("2017-02-02"), np.nan), (4, 2), ("foo", "bar")])
    view = SpreadsheetWidget(df=df)
    view._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": 1, "sort_ascending": True}
    )
    view._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": 1, "search_val": None}
    )


def test_row_edit_callback():
    sample_df = create_df()

    def can_edit_row(row):
        return row["E"] == "train" and row["F"] == "bar"

    view = SpreadsheetWidget(df=sample_df, row_edit_callback=can_edit_row)

    view._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "index", "sort_ascending": True}
    )

    expected_dict = {0: False, 1: True, 2: False, 3: False}

    assert expected_dict == view._editable_rows


# TODO: Modify since test fails on pandas too.
# def test_period_object_column():
#     range_index = pd.period_range(start="2000", periods=10, freq="B")
#     df = pd.DataFrame({"a": 5, "b": range_index}, index=range_index)
#     view = SpreadsheetWidget(df=df)
#     view._handle_view_msg_helper(
#         {"type": "change_sort", "sort_field": "index", "sort_ascending": True}
#     )
#     view._handle_view_msg_helper(
#         {"type": "show_filter_dropdown", "field": "index", "search_val": None}
#     )
#     view._handle_view_msg_helper(
#         {"type": "change_sort", "sort_field": "b", "sort_ascending": True}
#     )
#     view._handle_view_msg_helper(
#         {"type": "show_filter_dropdown", "field": "b", "search_val": None}
#     )


def test_get_selected_df():
    sample_df = create_df()
    selected_rows = [1, 3]
    view = SpreadsheetWidget(df=sample_df)
    view._handle_view_msg_helper({"rows": selected_rows, "type": "change_selection"})
    selected_df = view.get_selected_df()
    assert len(selected_df) == 2
    assert_modin_frame_equals(sample_df.iloc[selected_rows], pd.DataFrame(selected_df))


def test_integer_index_filter():
    view = SpreadsheetWidget(df=create_df())
    view._handle_view_msg_helper(
        {
            "field": "index",
            "filter_info": {
                "field": "index",
                "max": None,
                "min": 2,
                "type": "slider",
            },
            "type": "change_filter",
        }
    )
    filtered_df = view.get_changed_df()
    assert len(filtered_df) == 2


def test_series_of_text_filters():
    view = SpreadsheetWidget(df=create_df())
    view._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": "E", "search_val": None}
    )
    view._handle_view_msg_helper(
        {
            "field": "E",
            "filter_info": {
                "field": "E",
                "selected": [0, 1],
                "type": "text",
                "excluded": [],
            },
            "type": "change_filter",
        }
    )
    filtered_df = view.get_changed_df()
    assert len(filtered_df) == 2

    # reset the filter...
    view._handle_view_msg_helper(
        {
            "field": "E",
            "filter_info": {
                "field": "E",
                "selected": None,
                "type": "text",
                "excluded": [],
            },
            "type": "change_filter",
        }
    )

    # ...and apply a text filter on a different column
    view._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": "F", "search_val": None}
    )
    view._handle_view_msg_helper(
        {
            "field": "F",
            "filter_info": {
                "field": "F",
                "selected": [0, 1],
                "type": "text",
                "excluded": [],
            },
            "type": "change_filter",
        }
    )
    filtered_df = view.get_changed_df()
    assert len(filtered_df) == 2


def test_date_index():
    df = create_df()
    df.set_index("Date", inplace=True)
    view = SpreadsheetWidget(df=df)
    view._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": "A",
            "filter_info": {
                "field": "A",
                "type": "slider",
                "min": 2,
                "max": 3,
            },
        }
    )


def test_multi_index():
    widget = SpreadsheetWidget(df=create_multi_index_df())
    event_history = init_event_history(
        ["filter_dropdown_shown", "filter_changed", "sort_changed"],
        widget=widget,
    )

    widget._handle_view_msg_helper(
        {
            "type": "show_filter_dropdown",
            "field": "level_0",
            "search_val": None,
        }
    )

    widget._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": 3, "search_val": None}
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": 3,
            "filter_info": {
                "field": 3,
                "type": "slider",
                "min": -0.111,
                "max": None,
            },
        }
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": 3,
            "filter_info": {
                "field": 3,
                "type": "slider",
                "min": None,
                "max": None,
            },
        }
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": "level_1",
            "filter_info": {
                "field": "level_1",
                "type": "text",
                "selected": [0],
                "excluded": [],
            },
        }
    )

    widget._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": 3, "sort_ascending": True}
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_sort",
            "sort_field": "level_0",
            "sort_ascending": True,
        }
    )

    assert event_history == [
        {"name": "filter_dropdown_shown", "column": "level_0"},
        {"name": "filter_dropdown_shown", "column": 3},
        {"name": "filter_changed", "column": 3},
        {"name": "filter_changed", "column": 3},
        {"name": "filter_changed", "column": "level_1"},
        {
            "name": "sort_changed",
            "old": {"column": None, "ascending": True},
            "new": {"column": 3, "ascending": True},
        },
        {
            "name": "sort_changed",
            "old": {"column": 3, "ascending": True},
            "new": {"column": "level_0", "ascending": True},
        },
    ]


def test_interval_index():
    df = create_interval_index_df()
    df.set_index("time_bin", inplace=True)
    show_grid(df)


def test_multi_interval_index():
    df = create_interval_index_df()
    df["A"] = np.array([3] * 1000, dtype="int32")
    df.set_index(["time", "time_bin"], inplace=True)
    show_grid(df)


def test_set_defaults():
    fake_grid_options_a = {"foo": "bar"}
    set_defaults(show_toolbar=False, precision=4, grid_options=fake_grid_options_a)

    def assert_widget_vals_a(widget):
        assert not widget.show_toolbar
        assert widget.precision == 4
        assert widget.grid_options == fake_grid_options_a

    df = create_df()
    view = show_grid(df)
    assert_widget_vals_a(view)

    view = SpreadsheetWidget(df=df)
    assert_widget_vals_a(view)

    fake_grid_options_b = {"foo": "buzz"}
    set_defaults(show_toolbar=True, precision=2, grid_options=fake_grid_options_b)

    def assert_widget_vals_b(widget):
        assert widget.show_toolbar
        assert widget.precision == 2
        assert widget.grid_options == fake_grid_options_b

    df = create_df()
    view = show_grid(df)
    assert_widget_vals_b(view)

    view = SpreadsheetWidget(df=df)
    assert_widget_vals_b(view)


class MyObject(object):
    def __init__(self, obj):
        self.obj = obj


my_object_vals = [MyObject(MyObject(None)), MyObject(None)]


def test_object_dtype():
    df = pd.DataFrame({"a": my_object_vals}, index=my_object_vals)
    widget = SpreadsheetWidget(df=df)
    grid_data = json.loads(widget._df_json)["data"]

    widget._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": "a", "search_val": None}
    )
    widget._handle_view_msg_helper(
        {
            "field": "a",
            "filter_info": {
                "field": "a",
                "selected": [0, 1],
                "type": "text",
                "excluded": [],
            },
            "type": "change_filter",
        }
    )

    filter_table = widget._filter_tables["a"]
    assert not isinstance(filter_table[0], dict)
    assert not isinstance(filter_table[1], dict)

    assert not isinstance(grid_data[0]["a"], dict)
    assert not isinstance(grid_data[1]["a"], dict)

    assert not isinstance(grid_data[0]["index"], dict)
    assert not isinstance(grid_data[1]["index"], dict)


def test_index_categorical():
    df = pd.DataFrame({"foo": np.random.randn(3), "future_index": [22, 13, 87]})
    df["future_index"] = df["future_index"].astype("category")
    df = df.set_index("future_index")
    widget = SpreadsheetWidget(df=df)
    grid_data = json.loads(widget._df_json)["data"]

    assert not isinstance(grid_data[0]["future_index"], dict)
    assert not isinstance(grid_data[1]["future_index"], dict)


def test_object_dtype_categorical():
    cat_series = pd.Series(pd.Categorical(my_object_vals, categories=my_object_vals))
    widget = show_grid(cat_series)
    constraints_enum = widget._columns[0]["constraints"]["enum"]
    assert not isinstance(constraints_enum[0], dict)
    assert not isinstance(constraints_enum[1], dict)

    widget._handle_view_msg_helper(
        {"type": "show_filter_dropdown", "field": 0, "search_val": None}
    )
    widget._handle_view_msg_helper(
        {
            "field": 0,
            "filter_info": {
                "field": 0,
                "selected": [0],
                "type": "text",
                "excluded": [],
            },
            "type": "change_filter",
        }
    )
    assert len(widget._df) == 1
    assert widget._df[0][0] == cat_series[0]


def test_change_viewport():
    widget = SpreadsheetWidget(df=create_large_df())
    event_history = init_event_history(All)

    widget._handle_view_msg_helper(
        {"type": "change_viewport", "top": 7124, "bottom": 7136}
    )

    assert event_history == [
        {
            "name": "json_updated",
            "triggered_by": "change_viewport",
            "range": (7024, 7224),
        },
        {"name": "viewport_changed", "old": (0, 100), "new": (7124, 7136)},
    ]


def test_change_filter_viewport():
    widget = SpreadsheetWidget(df=create_large_df())
    event_history = init_event_history(All)

    widget._handle_view_msg_helper(
        {
            "type": "show_filter_dropdown",
            "field": "B (as str)",
            "search_val": None,
        }
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_filter_viewport",
            "field": "B (as str)",
            "top": 556,
            "bottom": 568,
        }
    )

    widget._handle_view_msg_helper(
        {
            "type": "change_filter_viewport",
            "field": "B (as str)",
            "top": 302,
            "bottom": 314,
        }
    )

    assert event_history == [
        {"name": "filter_dropdown_shown", "column": "B (as str)"},
        {
            "name": "text_filter_viewport_changed",
            "column": "B (as str)",
            "old": (0, 200),
            "new": (556, 568),
        },
        {
            "name": "text_filter_viewport_changed",
            "column": "B (as str)",
            "old": (556, 568),
            "new": (302, 314),
        },
    ]


def test_change_selection():
    widget = SpreadsheetWidget(df=create_large_df(size=10))
    event_history = init_event_history("selection_changed", widget=widget)

    widget._handle_view_msg_helper({"type": "change_selection", "rows": [5]})
    assert widget._selected_rows == [5]

    widget._handle_view_msg_helper({"type": "change_selection", "rows": [7, 8]})
    assert widget._selected_rows == [7, 8]

    widget.change_selection([3, 5, 6])
    assert widget._selected_rows == [3, 5, 6]

    widget.change_selection()
    assert widget._selected_rows == []

    assert event_history == [
        {"name": "selection_changed", "old": [], "new": [5], "source": "gui"},
        {
            "name": "selection_changed",
            "old": [5],
            "new": [7, 8],
            "source": "gui",
        },
        {
            "name": "selection_changed",
            "old": [7, 8],
            "new": [3, 5, 6],
            "source": "api",
        },
        {
            "name": "selection_changed",
            "old": [3, 5, 6],
            "new": [],
            "source": "api",
        },
    ]


def test_instance_created():
    event_history = init_event_history(All)
    spreadsheet_widget = show_grid(create_df())

    assert event_history == [{"name": "instance_created"}]
    assert spreadsheet_widget.id


def test_add_row():
    event_history = init_event_history(All)
    df = pd.DataFrame({"foo": ["hello"], "bar": ["world"], "baz": [42], "boo": [57]})
    df.set_index("baz", inplace=True, drop=True)

    q = SpreadsheetWidget(df=df)

    new_row = [
        ("baz", 43),
        ("bar", "new bar"),
        ("boo", 58),
        ("foo", "new foo"),
    ]

    q.add_row(new_row)

    assert q._df.loc[43, "foo"] == "new foo"
    assert q._df.loc[42, "foo"] == "hello"

    assert event_history == [
        {"name": "instance_created"},
        {"name": "json_updated", "range": (0, 100), "triggered_by": "add_row"},
        {"name": "row_added", "index": 43, "source": "api"},
    ]


def test_remove_row():
    event_history = init_event_history(All)
    df = create_df()

    widget = SpreadsheetWidget(df=df)
    widget.remove_row(rows=[2])

    assert 2 not in widget._df.index
    assert len(widget._df) == 3

    assert event_history == [
        {"name": "instance_created"},
        {
            "name": "json_updated",
            "range": (0, 100),
            "triggered_by": "remove_row",
        },
        {"name": "row_removed", "indices": [2], "source": "api"},
    ]


def test_edit_cell():
    df = pd.DataFrame({"foo": ["hello"], "bar": ["world"], "baz": [42], "boo": [57]})
    df.set_index("baz", inplace=True, drop=True)

    q = SpreadsheetWidget(df=df)
    event_history = init_event_history(All)

    q.edit_cell(42, "foo", "hola")

    assert q._df.loc[42, "foo"] == "hola"

    assert event_history == [
        {
            "name": "json_updated",
            "range": (0, 100),
            "triggered_by": "edit_cell",
        },
        {
            "name": "cell_edited",
            "index": 42,
            "column": "foo",
            "old": "hello",
            "new": "hola",
            "source": "api",
        },
    ]


def test_get_history():
    spreadsheet = SpreadsheetWidget(df=create_df())

    # Initial history
    last_history = spreadsheet.get_history()[-1]
    expected_history = "unfiltered_df = df.copy()"
    assert last_history == expected_history

    # Edit cell
    spreadsheet._handle_view_msg_helper(
        {
            "column": "A",
            "row_index": 0,
            "type": "edit_cell",
            "unfiltered_index": 0,
            "value": "hello world",
        }
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Edit cell\ndf.loc[(0, 'A')]='hello world'\nunfiltered_df.loc[(0, 'A')]='hello world'"
    assert last_history == expected_history

    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 0,
            "column": "Date",
            "unfiltered_index": 0,
            "value": "2013-01-10T00:00:00.000+00:00",
            "type": "edit_cell",
        },
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Edit cell\ndf.loc[(0, 'Date')]=Timestamp('2013-01-10 00:00:00')\nunfiltered_df.loc[(0, 'Date')]=Timestamp('2013-01-10 00:00:00')"
    assert last_history == expected_history

    # Remove row
    spreadsheet._handle_view_msg_helper(
        {"type": "remove_row"},
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = (
        "# Remove rows\ndf.drop([], inplace=True)\nunfiltered_df.drop([], inplace=True)"
    )
    assert last_history == expected_history

    # Change selection
    spreadsheet._handle_view_msg_helper(
        {"rows": [], "type": "change_selection"},
    )
    spreadsheet._handle_view_msg_helper(
        {"rows": [1], "type": "change_selection"},
    )
    spreadsheet._handle_view_msg_helper(
        {"rows": [1, 2, 3], "type": "change_selection"},
    )
    # History should not be changed
    last_history = spreadsheet.get_history()[-1]
    assert last_history == expected_history

    # Change viewport
    spreadsheet._handle_view_msg_helper(
        {"type": "change_viewport", "top": 7124, "bottom": 7136}
    )
    # History should not be changed
    last_history = spreadsheet.get_history()[-1]
    assert last_history == expected_history

    # Add row
    spreadsheet._handle_view_msg_helper({"type": "add_row"})
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Add row\nlast = df.loc[max(df.index)].copy()\ndf.loc[last.name+1] = last.values\nunfiltered_df.loc[last.name+1] = last.values"
    assert last_history == expected_history

    # Change filter
    spreadsheet._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": "Date",
            "filter_info": {
                "field": "Date",
                "type": "date",
                "min": 1351900800000,
                "max": 1357862399999,
            },
        },
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Filter columns\ndf = unfiltered_df[(unfiltered_df['Date'] >= pd.to_datetime(1351900800000, unit='ms'))&(unfiltered_df['Date'] <= pd.to_datetime(1357862399999, unit='ms'))].copy()"
    assert last_history == expected_history

    # Change sort
    spreadsheet._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "A", "sort_ascending": True}
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Sort mixed type column\ndf['A_modin_spreadsheet_sort_column'] = df['A'].map(str)\ndf.sort_values('A_modin_spreadsheet_sort_column', ascending=True, inplace=True)\ndf.drop(columns='A_modin_spreadsheet_sort_column', inplace=True)"
    assert last_history == expected_history

    # Reset filters
    spreadsheet._handle_view_msg_helper({"type": "reset_filters_end"})
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Sort mixed type column\ndf['A_modin_spreadsheet_sort_column'] = df['A'].map(str)\ndf.sort_values('A_modin_spreadsheet_sort_column', ascending=True, inplace=True)\ndf.drop(columns='A_modin_spreadsheet_sort_column', inplace=True)"
    assert last_history == expected_history

    # Reset sort
    spreadsheet._handle_view_msg_helper({"type": "reset_sort"})
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Reset sort\ndf.sort_index(ascending=True, inplace=True)"
    assert last_history == expected_history

    # Reorder columns
    # Should also check that no helper columns are recorded
    spreadsheet._handle_view_msg_helper(
        {"column_names": ['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1], "type": "reorder_columns"}
    )
    last_history = spreadsheet.get_history()[-1]
    expected_history = "# Reorder column\ndf = df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])\nunfiltered_df = unfiltered_df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])"
    assert last_history == expected_history

    # Clear history
    spreadsheet._handle_view_msg_helper({"type": "clear_history"})
    history = spreadsheet.get_history()
    expected_history = ["unfiltered_df = df.copy()"]
    assert history == expected_history


def test_apply_history():
    df = create_df()
    df_copy = df.copy()
    spreadsheet = SpreadsheetWidget(df=df)

    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 1,
            "column": "A",
            "unfiltered_index": 1,
            "value": 5,
            "type": "edit_cell",
        }
    )
    spreadsheet._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": "A",
            "filter_info": {"field": "A", "type": "slider", "min": None, "max": 4.14},
        },
    )
    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 2,
            "column": "F",
            "unfiltered_index": 3,
            "value": "foo",
            "type": "edit_cell",
        }
    )
    spreadsheet._handle_view_msg_helper(
        {
            "type": "change_filter",
            "field": "Date",
            "filter_info": {
                "field": "Date",
                "type": "date",
                "min": 1356998400000,
                "max": 1400000000000,
            },
        }
    )
    spreadsheet._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "Date", "sort_ascending": True}
    )
    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 1,
            "column": "A",
            "unfiltered_index": 2,
            "value": 2,
            "type": "edit_cell",
        }
    )
    spreadsheet._handle_view_msg_helper(
        {"column_names": ['Date', 1, 'A', 'C', 'F', 'Mixed', 'E', 'D'], "type": "reorder_columns"}
    )
    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 2,
            "column": "A",
            "unfiltered_index": 3,
            "value": 3,
            "type": "edit_cell",
        }
    )

    changed_df = spreadsheet.get_changed_df()

    # Checks that spreadsheet df is not modified in place
    assert_modin_frame_equals(changed_df, df)

    applied_df = spreadsheet.apply_history(df_copy)

    # Checks that apply_history does not modify in place
    assert_modin_frame_equals(df, df_copy)

    # Checks that the history is applied properly
    assert_modin_frame_equals(changed_df, applied_df)


def test_filter_relevant_history():
    spreadsheet = SpreadsheetWidget(df=create_df())

    # Initial history
    filtered_history = spreadsheet.filter_relevant_history()
    expected_history = ["unfiltered_df = df.copy()"]
    assert filtered_history == expected_history

    # Empty history
    spreadsheet._history = []
    expected_history = []
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # Multiple filters
    spreadsheet._history = [
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] <= 48802)].copy()",
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] >= 5495)&(unfiltered_df['trip_id'] <= 48802)].copy()",
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] >= 5495)&(unfiltered_df['trip_id'] <= 48802)&(unfiltered_df['vendor_id'] >= 2)].copy()",
    ]
    expected_history = [
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] >= 5495)&(unfiltered_df['trip_id'] <= 48802)&(unfiltered_df['vendor_id'] >= 2)].copy()",
    ]
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # Multiple sorts
    spreadsheet._history = [
        "# Sort column\ndf.sort_values('trip_id', ascending=True, inplace=True)",
        "# Sort column\ndf.sort_values('vendor_id', ascending=True, inplace=True)",
        "# Sort column\ndf.sort_values('vendor_id', ascending=False, inplace=True)",
    ]
    expected_history = [
        "# Sort column\ndf.sort_values('vendor_id', ascending=False, inplace=True)",
    ]
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # Filter after reset
    spreadsheet._history = [
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] >= 6485)].copy()",
        "# Reset filter\ndf = unfiltered_df.copy()",
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] <= 41873)].copy()",
    ]
    expected_history = [
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] <= 41873)].copy()"
    ]
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # Sort after reset
    spreadsheet._history = [
        "# Sort column\ndf.sort_values('trip_id', ascending=True, inplace=True)",
        "# Reset sort\ndf.sort_index(ascending=True, inplace=True)",
        "# Sort column\ndf.sort_values('vendor_id', ascending=True, inplace=True)",
    ]
    expected_history = [
        "# Sort column\ndf.sort_values('vendor_id', ascending=True, inplace=True)"
    ]
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # None after reset
    spreadsheet._history = [
        "# Sort column\ndf.sort_values('vendor_id', ascending=True, inplace=True)",
        "# Reset sort\ndf.sort_index(ascending=True, inplace=True)",
        "# Filter columns\ndf = unfiltered_df[(unfiltered_df['trip_id'] >= 6980)].copy()",
        "# Reset all filters\ndf = unfiltered_df.copy()",
    ]
    expected_history = []
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_history

    # Mixed transformation
    mixed_history = [
        "# Edit cell\ndf.loc[(4, 'trip_id')]=10\nunfiltered_df.loc[(4, 'trip_id')]=10",
        "# Sort column\ndf.sort_values('trip_id', ascending=True, inplace=True)",
        "# Sort column\ndf.sort_values('rate_code_id', ascending=True, inplace=True)",
        "# Reset sort\ndf.sort_index(ascending=True, inplace=True)",
        "# Sort index\ndf.sort_index(ascending=True, inplace=True)",
        "# Remove rows\ndf.drop([6], inplace=True)\nunfiltered_df.drop([6], inplace=True)",
        "# Add row\nlast = df.loc[max(df.index)].copy()\ndf.loc[last.name+1] = last.values\nunfiltered_df.loc[last.name+1] = last.values",
        "# Reset all filters\ndf = unfiltered_df.copy()",
        "# Sort index\ndf.sort_index(ascending=True, inplace=True)",
        "# Reorder column\ndf = df.reindex(columns=['A', 'Date', 'C', 'E', 'D', 'F', 'Mixed', 1])\nunfiltered_df = unfiltered_df.reindex(columns=['A', 'Date', 'C', 'E', 'D', 'F', 'Mixed', 1])",
        "# Reorder column\ndf = df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])\nunfiltered_df = unfiltered_df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])"
    ]
    expected_filtered_history = [
        "# Edit cell\ndf.loc[(4, 'trip_id')]=10\nunfiltered_df.loc[(4, 'trip_id')]=10",
        "# Remove rows\ndf.drop([6], inplace=True)\nunfiltered_df.drop([6], inplace=True)",
        "# Add row\nlast = df.loc[max(df.index)].copy()\ndf.loc[last.name+1] = last.values\nunfiltered_df.loc[last.name+1] = last.values",
        "# Sort index\ndf.sort_index(ascending=True, inplace=True)",
        "# Reorder column\ndf = df.reindex(columns=['A', 'Date', 'C', 'E', 'D', 'F', 'Mixed', 1])\nunfiltered_df = unfiltered_df.reindex(columns=['A', 'Date', 'C', 'E', 'D', 'F', 'Mixed', 1])",
        "# Reorder column\ndf = df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])\nunfiltered_df = unfiltered_df.reindex(columns=['A', 'Date', 'C', 'F', 'E', 'D', 'Mixed', 1])"
    ]
    spreadsheet._history = mixed_history
    filtered_history = spreadsheet.filter_relevant_history()
    assert filtered_history == expected_filtered_history

    # Persist filter history
    spreadsheet._history = mixed_history
    spreadsheet.filter_relevant_history(persist=True)
    assert spreadsheet.get_history() == expected_filtered_history

    # Don't persist filter history
    spreadsheet._history = mixed_history
    filtered_history = spreadsheet.filter_relevant_history(persist=False)
    assert filtered_history == expected_filtered_history
    assert spreadsheet.get_history() == mixed_history


def test_mixed_type_sort():
    df = pd.DataFrame(
        {
            "Mixed": [pd.Timestamp("2017-02-02"), np.nan, 1e10, 5, "hey"],
            1: [5, 4, "hello", 2, 1],
        }
    )

    spreadsheet = SpreadsheetWidget(df=df)

    spreadsheet._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "Mixed", "sort_ascending": True}
    )

    expected_order_mixed = [1e10, pd.Timestamp("2017-02-02"), 5, "hey", np.nan]
    sorted_order_mixed = list(spreadsheet.get_changed_df()["Mixed"])
    assert expected_order_mixed[:4] == sorted_order_mixed[:4]
    # np.nan != np.nan by definition, so check if value at index 4 are both np.nan
    assert np.isnan(expected_order_mixed[4]) and np.isnan(sorted_order_mixed[4])

    # check sorting on number column names works
    spreadsheet._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": 1, "sort_ascending": True}
    )
    expected_order_1 = [1, 2, 4, 5, "hello"]
    sorted_order_1 = list(spreadsheet.get_changed_df()[1])
    assert expected_order_1 == sorted_order_1


def test_column_reorder():
    spreadsheet = SpreadsheetWidget(df=create_df())

    # Check basic column reorder (move column A behind C)
    spreadsheet._handle_view_msg_helper(
        {"column_names": ['Date', 'C', 'A', 'D', 'E', 'F', 'Mixed', 1], "type": "reorder_columns"}
    )

    expected_columns = ['Date', 'C', 'A', 'D', 'E', 'F', 'Mixed', 1]
    actual_columns = list(spreadsheet.get_changed_df().columns)
    assert expected_columns == actual_columns

    # Check non-string column name reorder (move column 1 behind F)
    spreadsheet._handle_view_msg_helper(
        {"column_names": ['Date', 'C', 'A', 'D', 'E', 'F', 'Mixed', 1], "type": "reorder_columns"}
    )

    expected_columns = ['Date', 'C', 'A', 'D', 'E', 'F', 'Mixed', 1]
    actual_columns = list(spreadsheet.get_changed_df().columns)
    assert expected_columns == actual_columns

    # Check sort on column A is correct
    spreadsheet._handle_view_msg_helper(
        {"type": "change_sort", "sort_field": "A", "sort_ascending": False}
    )

    expected_order = [3, 2, 1, 1]
    sorted_order = list(spreadsheet.get_changed_df()["A"])
    assert expected_order == sorted_order

    # Check editing cell in column A is correct
    spreadsheet._handle_view_msg_helper(
        {
            "row_index": 0,
            "column": "A",
            "unfiltered_index": 3,
            "value": 5,
            "type": "edit_cell",
        }
    )

    assert spreadsheet.get_changed_df().loc[3, "A"] == 5

    # Reorder columns with helper column
    spreadsheet._handle_view_msg_helper(
        {'type': 'change_sort', 'sort_field': 1, 'sort_ascending': True}
    )
    spreadsheet._handle_view_msg_helper(
        {"column_names": ['Date', 1, 'A', 'C', 'F', 'Mixed', 'E', 'D'], "type": "reorder_columns"}
    )
    expected_columns = ['Date', 1, 'A', 'C', 'F', 'Mixed', 'E', 'D']
    actual_columns = list(spreadsheet.get_changed_df().columns)
    assert expected_columns == actual_columns
