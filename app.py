import json
from pathlib import Path

import streamlit as st


INVENTORY_FILE = Path(__file__).with_name("Inventory.json")
MENU_FILE = Path(__file__).with_name("menu.txt")


def load_menu_inventory() -> list[dict[str, str]]:
    try:
        lines = MENU_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        st.error(f"Could not read {MENU_FILE.name}: {error}")
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


def load_inventory() -> list[dict[str, str]]:
    if not INVENTORY_FILE.exists():
        return load_menu_inventory()

    try:
        inventory = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        st.error(f"Could not load {INVENTORY_FILE.name}: {error}")
        st.stop()

    if not isinstance(inventory, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("Item"), str)
        or not item["Item"].strip()
        or not isinstance(item.get("Category"), str)
        or not item["Category"].strip()
        for item in inventory
    ):
        st.error(f"{INVENTORY_FILE.name} must contain a list of items and categories.")
        st.stop()

    return inventory


def save_inventory(inventory: list[dict[str, str]]) -> bool:
    temporary_file = INVENTORY_FILE.with_suffix(".json.tmp")
    try:
        temporary_file.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary_file.replace(INVENTORY_FILE)
    except OSError as error:
        st.error(f"Could not save changes to {INVENTORY_FILE.name}: {error}")
        return False
    return True


st.set_page_config(page_title="Inventory Explorer", page_icon=":package:", layout="wide")
st.title("Inventory Explorer")
st.caption("Browse, search, and manage the sample items from the project inventory.")

inventory = load_inventory()
categories = sorted({item["Category"] for item in inventory})

with st.expander("Add an item"):
    with st.form("add_item_form"):
        new_item_name = st.text_input("Item name")
        category_options = [*categories, "Add a new category"]
        selected_new_category = st.selectbox("Category", category_options)
        new_category_name = ""
        if selected_new_category == "Add a new category":
            new_category_name = st.text_input("New category name")
        add_item = st.form_submit_button("Add item")

    if add_item:
        item_name = new_item_name.strip()
        category_name = (
            new_category_name.strip()
            if selected_new_category == "Add a new category"
            else selected_new_category
        )
        if not item_name or not category_name:
            st.error("Enter an item name and category.")
        elif any(
            item["Item"].casefold() == item_name.casefold()
            and item["Category"].casefold() == category_name.casefold()
            for item in inventory
        ):
            st.error("That item is already in this category.")
        else:
            updated_inventory = [
                *inventory,
                {"Item": item_name, "Category": category_name},
            ]
            if save_inventory(updated_inventory):
                st.success(f"Added {item_name} to {category_name}.")
                st.rerun()

if inventory:
    item_labels = [
        f"{index}: {item['Item']} — {item['Category']}"
        for index, item in enumerate(inventory)
    ]
    with st.expander("Remove an item"):
        with st.form("remove_item_form"):
            selected_item_label = st.selectbox("Choose an item", item_labels)
            remove_item = st.form_submit_button("Remove item")

        if remove_item:
            item_index = int(selected_item_label.split(":", maxsplit=1)[0])
            removed_item = inventory[item_index]
            updated_inventory = [
                item for index, item in enumerate(inventory) if index != item_index
            ]
            if save_inventory(updated_inventory):
                st.success(f"Removed {removed_item['Item']} from the inventory.")
                st.rerun()

if not inventory:
    st.info("The inventory is empty. Add an item to get started.")

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
