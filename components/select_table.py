from typing import Callable
from nicegui import ui


def select_table(
    items: list,
    columns: list,  # Quasar column spec; 'field' is optional ('name' will be used instead)
    row_key: str,
    selected_key: str | None = None,
    on_selection: Callable | None = None,
    body_slot_string: str = "",
):
    """Show items in a table with a single selectable row (click on/off). On change, on_selection is called with selected_key."""

    def refresh_selection(table) -> None:
        """Make the selected row (if any) stand out."""
        nonlocal selected_key
        table.selected.clear()
        if selected_key is not None:
            selected_rows = [row for row in table.rows if row[row_key] == selected_key]
            if selected_rows:
                table.selected.append(selected_rows[0])
        # table.update()  # not required?

    def _on_cell_click(new_key: str) -> None:
        nonlocal selected_key
        if new_key == selected_key:  # deselect
            selected_key = None
        else:
            selected_key = new_key
        refresh_selection(table)
        if on_selection:
            on_selection(selected_key)

    columns = [col if 'field' in col else {**col, 'field': col['name']} for col in columns]

    table = ui.table(
        # columns=[{"name": f, "label": f, "field": f, "sortable": True,
        #   "align": "left", "classes": f"select-table-{f}"} for f in column_names],
        columns=columns,
        column_defaults={"align": "left", "sortable": True},
        rows=items,
        row_key=row_key,
    ).classes("w-full select-table")
    table.add_slot(
        "body-cell",
        r"""
        <q-td :props="props" """ + body_slot_string + r""" @click="$parent.$emit('cell_click', props)">
            {{ props.value }}
        </q-td>
        """,
    )
    table.on("cell_click", lambda msg: _on_cell_click(msg.args['key']))
    refresh_selection(table)
