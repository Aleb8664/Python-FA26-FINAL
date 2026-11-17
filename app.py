from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from inventory_data import (
    InventoryDataError,
    active_checkouts,
    add_item,
    add_user,
    authenticate,
    change_user_role,
    find_user,
    is_overdue,
    issue_item,
    load_state,
    outstanding_quantity,
    remove_item,
    renew_checkout,
    return_item,
    save_state,
    setup_owner,
    update_item,
)


INVENTORY_FILE = Path(__file__).with_name("Inventory.json")
MENU_FILE = Path(__file__).with_name("menu.txt")
ITEM_TYPES = {"stock": "Stock / consumable", "reusable": "Reusable equipment"}


def persist_and_rerun(
    state: dict[str, Any], success_message: str | None = None
) -> None:
    try:
        save_state(INVENTORY_FILE, state)
    except InventoryDataError as error:
        st.error(str(error))
        return
    if success_message:
        st.session_state["flash_message"] = success_message
    st.rerun()


def item_label(item: dict[str, Any]) -> str:
    status = "" if item["active"] else " (inactive)"
    return f"{item['name']} — {item['category']}{status}"


def user_label(users: list[dict[str, Any]], employee_id: str) -> str:
    user = next((entry for entry in users if entry["id"] == employee_id), None)
    return f"{user['name']} ({employee_id})" if user else employee_id


def format_date(value: str | None) -> str:
    if not value:
        return "—"
    return datetime.fromisoformat(value).astimezone().strftime("%b %d, %Y %I:%M %p")


st.set_page_config(page_title="Inventory Manager", page_icon=":package:", layout="wide")

try:
    state = load_state(INVENTORY_FILE, MENU_FILE)
except InventoryDataError as error:
    st.error(str(error))
    st.stop()

st.title("Inventory Manager")

if not state["users"]:
    st.info(
        "First-time setup: create the owner password for employee ID 1 (aleb). "
        "The owner account has protected, full administrator access."
    )
    with st.form("initial_owner_setup"):
        owner_password = st.text_input("Create owner password", type="password")
        confirm_password = st.text_input("Confirm owner password", type="password")
        setup_submitted = st.form_submit_button("Create owner account")
    if setup_submitted:
        if len(owner_password) < 8:
            st.error("Use a password with at least 8 characters.")
        elif owner_password != confirm_password:
            st.error("The passwords do not match.")
        else:
            setup_owner(state, owner_password)
            persist_and_rerun(state)
    st.stop()

current_user_id = st.session_state.get("employee_id")
current_user = find_user(state, current_user_id) if current_user_id else None
if current_user is None:
    st.session_state.pop("employee_id", None)
    with st.form("login_form"):
        employee_id = st.text_input("Employee ID")
        password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Sign in")
    if login_submitted:
        authenticated_user = authenticate(state, employee_id.strip(), password)
        if authenticated_user is None:
            st.error("Employee ID or password is incorrect.")
        else:
            st.session_state["employee_id"] = authenticated_user["id"]
            st.rerun()
    st.stop()

flash_message = st.session_state.pop("flash_message", None)
if flash_message:
    st.success(flash_message)

is_admin = current_user["role"] in {"owner", "admin"}
with st.sidebar:
    st.write(f"Signed in as **{current_user['name']}**")
    st.caption(f"Employee ID: {current_user['id']} · Role: {current_user['role'].title()}")
    if st.button("Sign out"):
        st.session_state.pop("employee_id", None)
        st.rerun()
    st.divider()
    st.caption(
        "Local demo storage: account and inventory data is saved in "
        "`Inventory.json` on this computer."
    )

active_users = [user for user in state["users"] if user.get("active", True)]
all_items = state["items"]
active_items = [item for item in all_items if item["active"]]
overdue = [
    transaction
    for transaction in active_checkouts(state)
    if is_overdue(transaction)
]
low_stock_items = [
    item
    for item in active_items
    if item["type"] == "stock" and item["quantity"] <= item["low_stock_threshold"]
]

if overdue:
    overdue_names = ", ".join(
        f"{transaction['item_name']} ({transaction['employee_name']})"
        for transaction in overdue
    )
    st.error(f"OVERDUE: {len(overdue)} checkout(s) need attention — {overdue_names}")
if low_stock_items:
    low_stock_names = ", ".join(
        f"{item['name']} ({item['quantity']} available)"
        for item in low_stock_items
    )
    st.warning(f"Low stock: {low_stock_names}")

tab_names = ["Dashboard", "Inventory", "Issue / check out", "Returns / renewals", "History"]
if is_admin:
    tab_names.append("User administration")
tabs = st.tabs(tab_names)
dashboard_tab, inventory_tab, issue_tab, returns_tab, history_tab = tabs[:5]

with dashboard_tab:
    st.subheader("Inventory at a glance")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Active items", len(active_items))
    metric_columns[1].metric(
        "Available units", sum(item["quantity"] for item in active_items)
    )
    metric_columns[2].metric("Low-stock items", len(low_stock_items))
    metric_columns[3].metric("Overdue checkouts", len(overdue))

    if overdue:
        st.subheader("Overdue equipment")
        overdue_rows = [
            {
                "Item": transaction["item_name"],
                "Borrower": transaction["employee_name"],
                "Quantity out": transaction["quantity_outstanding"],
                "Due": format_date(transaction["due_at"]),
                "Reason": transaction["reason"],
            }
            for transaction in overdue
        ]
        st.dataframe(overdue_rows, hide_index=True, width="stretch")
    if low_stock_items:
        st.subheader("Items at or below their reorder threshold")
        st.dataframe(
            [
                {
                    "Item": item["name"],
                    "Category": item["category"],
                    "Available": item["quantity"],
                    "Alert at": item["low_stock_threshold"],
                }
                for item in low_stock_items
            ],
            hide_index=True,
            width="stretch",
        )

with inventory_tab:
    if is_admin:
        browse_tab, add_tab, edit_tab, remove_tab = st.tabs(
            ["Browse items", "Add item", "Edit item", "Remove item"]
        )
    else:
        browse_tab = st.container()
        add_tab = edit_tab = remove_tab = None

    with browse_tab:
        st.subheader("Inventory")
        include_inactive = (
            st.checkbox("Show inactive items") if is_admin else False
        )
        visible_items = (
            all_items if include_inactive else [item for item in active_items]
        )
        search_column, category_column = st.columns([2, 1])
        with search_column:
            item_search = st.text_input("Search inventory", key="inventory_search")
        with category_column:
            visible_categories = sorted({item["category"] for item in visible_items})
            selected_category = st.selectbox(
                "Category", ["All categories", *visible_categories]
            )
        item_search = item_search.strip().casefold()
        filtered_items = [
            item
            for item in visible_items
            if (
                selected_category == "All categories"
                or item["category"] == selected_category
            )
            and item_search in item["name"].casefold()
        ]
        if filtered_items:
            outstanding_by_item = {
                item["id"]: outstanding_quantity(state, item["id"])
                for item in filtered_items
            }
            st.dataframe(
                [
                    {
                        "Item": item["name"],
                        "Category": item["category"],
                        "Type": ITEM_TYPES[item["type"]],
                        "Available": item["quantity"],
                        "Checked out": outstanding_by_item[item["id"]],
                        "Low-stock alert": (
                            str(item["low_stock_threshold"])
                            if item["type"] == "stock"
                            else "—"
                        ),
                        "Checkout limit (days)": (
                            str(item["max_checkout_days"])
                            if item["type"] == "reusable"
                            else "—"
                        ),
                        "Status": "Active" if item["active"] else "Inactive",
                    }
                    for item in filtered_items
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No inventory items match these filters.")

    if is_admin and add_tab is not None:
        with add_tab:
            st.subheader("Add an inventory item")
            new_type = st.selectbox(
                "Item type",
                list(ITEM_TYPES),
                format_func=lambda value: ITEM_TYPES[value],
                key="new_item_type",
            )
            categories = sorted({item["category"] for item in all_items})
            category_options = [*categories, "Add a new category"]
            selected_new_category = st.selectbox(
                "Category",
                category_options,
                key="new_item_category",
            )
            if selected_new_category == "Add a new category":
                new_category = st.text_input("New category name")
            else:
                new_category = ""
            with st.form("add_inventory_item"):
                new_name = st.text_input("Item name")
                new_quantity = st.number_input(
                    "Available quantity", min_value=0, value=5, step=1
                )
                new_threshold = st.number_input(
                    "Low-stock alert threshold", min_value=0, value=3, step=1
                )
                new_max_days = 7
                new_max_renewals = 2
                if new_type == "reusable":
                    new_max_days = st.number_input(
                        "Maximum checkout days", min_value=1, value=7, step=1
                    )
                    new_max_renewals = st.number_input(
                        "Maximum renewals", min_value=0, value=2, step=1
                    )
                authorized_users = st.multiselect(
                    "Employees allowed to use this item (leave blank for all active employees)",
                    [user["id"] for user in active_users if user["role"] != "owner"],
                    format_func=lambda employee_id: user_label(
                        active_users, employee_id
                    ),
                )
                add_submitted = st.form_submit_button("Add item")
            if add_submitted:
                category = (
                    new_category.strip()
                    if selected_new_category == "Add a new category"
                    else selected_new_category
                )
                try:
                    add_item(
                        state,
                        name=new_name,
                        category=category,
                        item_type=new_type,
                        quantity=int(new_quantity),
                        low_stock_threshold=int(new_threshold),
                        max_checkout_days=int(new_max_days),
                        max_renewals=int(new_max_renewals),
                        authorized_user_ids=authorized_users,
                    )
                except InventoryDataError as error:
                    st.error(str(error))
                else:
                    persist_and_rerun(state, f"Added {new_name.strip()}.")

    if is_admin and edit_tab is not None:
        with edit_tab:
            st.subheader("Edit item settings and available quantity")
            if not all_items:
                st.info("There are no items to edit.")
            else:
                item_ids = [item["id"] for item in all_items]
                selected_edit_id = st.selectbox(
                    "Choose an item to edit",
                    item_ids,
                    format_func=lambda item_id: item_label(
                        next(item for item in all_items if item["id"] == item_id)
                    ),
                )
                edit_item_data = next(
                    item for item in all_items if item["id"] == selected_edit_id
                )
                with st.form("edit_inventory_item"):
                    edited_name = st.text_input(
                        "Item name", value=edit_item_data["name"]
                    )
                    edited_category = st.text_input(
                        "Category", value=edit_item_data["category"]
                    )
                    edited_type = st.selectbox(
                        "Item type",
                        list(ITEM_TYPES),
                        index=list(ITEM_TYPES).index(edit_item_data["type"]),
                        format_func=lambda value: ITEM_TYPES[value],
                    )
                    edited_quantity = st.number_input(
                        "Available quantity",
                        min_value=0,
                        value=edit_item_data["quantity"],
                        step=1,
                    )
                    edited_threshold = st.number_input(
                        "Low-stock alert threshold",
                        min_value=0,
                        value=edit_item_data["low_stock_threshold"],
                        step=1,
                    )
                    edited_max_days = st.number_input(
                        "Maximum checkout days",
                        min_value=1,
                        value=edit_item_data["max_checkout_days"],
                        step=1,
                    )
                    edited_max_renewals = st.number_input(
                        "Maximum renewals",
                        min_value=0,
                        value=edit_item_data["max_renewals"],
                        step=1,
                    )
                    edited_authorized_users = st.multiselect(
                        "Employees allowed to use this item (leave blank for all active employees)",
                        [
                            user["id"]
                            for user in active_users
                            if user["role"] != "owner"
                        ],
                        default=[
                            employee_id
                            for employee_id in edit_item_data["authorized_user_ids"]
                            if any(
                                employee["id"] == employee_id
                                for employee in active_users
                            )
                        ],
                        format_func=lambda employee_id: user_label(
                            active_users, employee_id
                        ),
                    )
                    edit_submitted = st.form_submit_button("Save item changes")
                if edit_submitted:
                    try:
                        update_item(
                            state,
                            selected_edit_id,
                            name=edited_name,
                            category=edited_category,
                            item_type=edited_type,
                            quantity=int(edited_quantity),
                            low_stock_threshold=int(edited_threshold),
                            max_checkout_days=int(edited_max_days),
                            max_renewals=int(edited_max_renewals),
                            authorized_user_ids=edited_authorized_users,
                        )
                    except InventoryDataError as error:
                        st.error(str(error))
                    else:
                        persist_and_rerun(
                            state, f"Saved changes to {edited_name.strip()}."
                        )

    if is_admin and remove_tab is not None:
        with remove_tab:
            st.subheader("Remove an inventory item")
            if not all_items:
                st.info("There are no items to remove.")
            else:
                remove_item_id = st.selectbox(
                    "Choose an item",
                    [item["id"] for item in all_items],
                    format_func=lambda item_id: item_label(
                        next(item for item in all_items if item["id"] == item_id)
                    ),
                    key="remove_item_select",
                )
                remove_item_data = next(
                    item for item in all_items if item["id"] == remove_item_id
                )
                has_items_out = outstanding_quantity(state, remove_item_id) > 0
                if has_items_out:
                    st.warning(
                        "This item has units checked out. You can mark it inactive, "
                        "but must record all returns before permanently deleting it."
                    )
                with st.form("remove_inventory_item"):
                    remove_mode = st.radio(
                        "Action",
                        ["Mark inactive (keep history)", "Permanently delete"],
                    )
                    remove_submitted = st.form_submit_button("Confirm removal")
                if remove_submitted:
                    permanent = remove_mode == "Permanently delete"
                    try:
                        remove_item(state, remove_item_id, permanent=permanent)
                    except InventoryDataError as error:
                        st.error(str(error))
                    else:
                        persist_and_rerun(
                            state,
                            f"{remove_item_data['name']} was "
                            f"{'permanently deleted' if permanent else 'marked inactive'}."
                        )

with issue_tab:
    st.subheader("Issue stock or check out reusable equipment")
    available_items = [
        item for item in active_items if item["quantity"] > 0
    ]
    if not available_items:
        st.info("There are no available inventory items to issue or check out.")
    else:
        checkout_item_id = st.selectbox(
            "Choose an item",
            [item["id"] for item in available_items],
            format_func=lambda item_id: item_label(
                next(item for item in available_items if item["id"] == item_id)
            ),
        )
        checkout_item = next(
            item for item in available_items if item["id"] == checkout_item_id
        )
        if (
            checkout_item["authorized_user_ids"]
            and current_user["id"] not in checkout_item["authorized_user_ids"]
            and not is_admin
        ):
            st.error("You are not authorized to use this item.")
        else:
            st.caption(f"Available now: {checkout_item['quantity']}")
            with st.form("issue_inventory_item"):
                checkout_quantity = st.number_input(
                    "Quantity",
                    min_value=1,
                    max_value=checkout_item["quantity"],
                    value=1,
                    step=1,
                )
                reason = st.text_area("Reason (required)")
                issue_submitted = st.form_submit_button(
                    "Issue stock"
                    if checkout_item["type"] == "stock"
                    else "Check out equipment"
                )
            if issue_submitted:
                try:
                    issue_item(
                        state,
                        employee_id=current_user["id"],
                        item_id=checkout_item_id,
                        quantity=int(checkout_quantity),
                        reason=reason,
                    )
                except InventoryDataError as error:
                    st.error(str(error))
                else:
                    persist_and_rerun(
                        state,
                        "Stock issued."
                        if checkout_item["type"] == "stock"
                        else "Equipment checked out.",
                    )

with returns_tab:
    st.subheader("Return or renew equipment")
    user_checkouts = [
        transaction
        for transaction in active_checkouts(state)
        if is_admin or transaction["employee_id"] == current_user["id"]
    ]
    return_tab, renew_tab = st.tabs(["Return equipment", "Renew checkout"])
    if not user_checkouts:
        st.info("There are no active equipment checkouts available to manage.")
    else:
        transaction_ids = [transaction["id"] for transaction in user_checkouts]

        def checkout_label(transaction_id: str) -> str:
            transaction = next(
                entry for entry in user_checkouts if entry["id"] == transaction_id
            )
            return (
                f"{transaction['item_name']} — {transaction['employee_name']} — "
                f"{transaction['quantity_outstanding']} out — due "
                f"{format_date(transaction['due_at'])}"
            )

        with return_tab:
            return_transaction_id = st.selectbox(
                "Choose a checkout to return",
                transaction_ids,
                format_func=checkout_label,
                key="return_checkout_select",
            )
            return_transaction = next(
                transaction
                for transaction in user_checkouts
                if transaction["id"] == return_transaction_id
            )
            with st.form("return_equipment"):
                return_quantity = st.number_input(
                    "Quantity to return",
                    min_value=1,
                    max_value=return_transaction["quantity_outstanding"],
                    value=return_transaction["quantity_outstanding"],
                    step=1,
                )
                return_submitted = st.form_submit_button("Record return")
            if return_submitted:
                try:
                    return_item(
                        state,
                        transaction_id=return_transaction_id,
                        employee_id=current_user["id"],
                        quantity=int(return_quantity),
                    )
                except InventoryDataError as error:
                    st.error(str(error))
                else:
                    persist_and_rerun(state, "Return recorded.")

        with renew_tab:
            renew_transaction_id = st.selectbox(
                "Choose a checkout to renew",
                transaction_ids,
                format_func=checkout_label,
                key="renew_checkout_select",
            )
            renew_transaction = next(
                transaction
                for transaction in user_checkouts
                if transaction["id"] == renew_transaction_id
            )
            renewal_item = next(
                (
                    item
                    for item in all_items
                    if item["id"] == renew_transaction["item_id"]
                ),
                None,
            )
            renewals_left = (
                renewal_item["max_renewals"] - renew_transaction["renewals"]
                if renewal_item
                else 0
            )
            if renewals_left <= 0:
                st.warning("The maximum number of renewals has been reached.")
            else:
                st.caption(f"Renewals remaining: {renewals_left}")
                with st.form("renew_equipment"):
                    renew_submitted = st.form_submit_button("Renew checkout")
                if renew_submitted:
                    try:
                        renew_checkout(
                            state,
                            transaction_id=renew_transaction_id,
                            employee_id=current_user["id"],
                        )
                    except InventoryDataError as error:
                        st.error(str(error))
                    else:
                        persist_and_rerun(state, "Checkout renewed.")

with history_tab:
    st.subheader("Issue and checkout history")
    visible_transactions = [
        transaction
        for transaction in state["transactions"]
        if is_admin or transaction["employee_id"] == current_user["id"]
    ]
    if visible_transactions:
        st.dataframe(
            [
                {
                    "Item": transaction["item_name"],
                    "Type": (
                        "Equipment checkout"
                        if transaction["kind"] == "checkout"
                        else "Stock issued"
                    ),
                    "Employee": transaction["employee_name"],
                    "Quantity": transaction["quantity"],
                    "Still out": transaction["quantity_outstanding"],
                    "Reason": transaction["reason"],
                    "Checked out / issued": format_date(transaction["checked_out_at"]),
                    "Due": format_date(transaction["due_at"]),
                    "Returned": format_date(transaction["returned_at"]),
                    "Renewals": transaction["renewals"],
                }
                for transaction in reversed(visible_transactions)
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("There is no issue or checkout history yet.")

if is_admin:
    user_admin_tab = tabs[5]
    with user_admin_tab:
        st.subheader("Create employee accounts and assign access")
        with st.form("create_employee_account"):
            new_employee_id = st.text_input("New employee ID")
            new_employee_name = st.text_input("Employee name")
            new_employee_password = st.text_input(
                "Initial password (at least 8 characters)", type="password"
            )
            new_employee_role = st.selectbox(
                "Access level",
                ["employee", "admin"],
                format_func=lambda role: "Administrator" if role == "admin" else "Employee",
            )
            create_user_submitted = st.form_submit_button("Create account")
        if create_user_submitted:
            try:
                add_user(
                    state,
                    new_employee_id,
                    new_employee_name,
                    new_employee_password,
                    new_employee_role,
                )
            except InventoryDataError as error:
                st.error(str(error))
            else:
                persist_and_rerun(state, f"Created account for {new_employee_name.strip()}.")

        st.subheader("Change an employee's access")
        manageable_users = [
            user for user in active_users if user["role"] != "owner"
        ]
        if manageable_users:
            role_user_id = st.selectbox(
                "Employee account",
                [user["id"] for user in manageable_users],
                format_func=lambda employee_id: user_label(
                    manageable_users, employee_id
                ),
            )
            role_user = find_user(state, role_user_id)
            with st.form("change_employee_role"):
                new_role = st.selectbox(
                    "Access level",
                    ["employee", "admin"],
                    index=0 if role_user["role"] == "employee" else 1,
                    format_func=lambda role: "Administrator"
                    if role == "admin"
                    else "Employee",
                )
                role_submitted = st.form_submit_button("Save access level")
            if role_submitted:
                try:
                    change_user_role(state, role_user_id, new_role)
                except InventoryDataError as error:
                    st.error(str(error))
                else:
                    persist_and_rerun(
                        state,
                        f"Updated {role_user['name']}'s access to {new_role}.",
                    )
        else:
            st.info("Create an employee account before changing access.")

        st.subheader("Accounts")
        st.dataframe(
            [
                {
                    "Employee ID": user["id"],
                    "Name": user["name"],
                    "Access": (
                        "Owner (protected)"
                        if user["role"] == "owner"
                        else user["role"].title()
                    ),
                }
                for user in active_users
            ],
            hide_index=True,
            width="stretch",
        )
