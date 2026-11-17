from pathlib import Path

import streamlit as st


def load_inventory() -> list[dict[str, str]]:
    menu_path = Path(__file__).with_name("menu.txt")
    try:
        lines = menu_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        st.error(f"Could not read {menu_path.name}: {error}")
        st.stop()

    inventory = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        category, separator, item_list = line.partition(":")
        if not separator or not category.strip():
            st.error(
                f"Invalid inventory data on line {line_number}. "
                "Expected a category followed by a colon and comma-separated items."
            )
            st.stop()

        category_name = category.strip().replace("_", " ").title()
        for item in item_list.split(","):
            item_name = item.strip()
            if item_name:
                inventory.append({"Item": item_name, "Category": category_name})

    return inventory


st.set_page_config(page_title="Inventory Explorer", page_icon=":package:", layout="wide")
st.title("Inventory Explorer")
st.caption("Search and browse the sample items from the project inventory.")

inventory = load_inventory()
if not inventory:
    st.warning("No inventory items were found in menu.txt.")
    st.stop()

categories = sorted({item["Category"] for item in inventory})

search_column, category_column = st.columns([2, 1])
with search_column:
    search_term = st.text_input("Search items", placeholder="For example, generator")
with category_column:
    selected_category = st.selectbox("Filter by category", ["All categories", *categories])

search_term = search_term.strip().casefold()
filtered_inventory = [
    item
    for item in inventory
    if (selected_category == "All categories" or item["Category"] == selected_category)
    and search_term in item["Item"].casefold()
]

metric_column, category_metric_column, result_column = st.columns(3)
metric_column.metric("Inventory items", len(inventory))
category_metric_column.metric("Categories", len(categories))
result_column.metric("Matching items", len(filtered_inventory))

st.subheader("Items")
if filtered_inventory:
    st.dataframe(filtered_inventory, hide_index=True, width="stretch")
else:
    st.info("No items match the current search and category filter.")
