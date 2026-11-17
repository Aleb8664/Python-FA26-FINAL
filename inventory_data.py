import hashlib
import hmac
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PASSWORD_ITERATIONS = 260_000
SAMPLE_CATEGORIES = {"tools", "equipment"}


class InventoryDataError(Exception):
    """Raised when inventory data cannot be read or safely updated."""


def new_id() -> str:
    return uuid.uuid4().hex


def make_password_record(password: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return {"salt": salt.hex(), "password_hash": password_hash.hex()}


def verify_password(password: str, user: dict[str, Any]) -> bool:
    try:
        salt = bytes.fromhex(user["salt"])
        expected_hash = bytes.fromhex(user["password_hash"])
    except (KeyError, TypeError, ValueError):
        return False

    actual_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(actual_hash, expected_hash)


def _read_sample_items(menu_path: Path) -> list[dict[str, Any]]:
    try:
        lines = menu_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InventoryDataError(f"Could not read {menu_path.name}: {error}") from error

    items = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        category, separator, names = line.partition(":")
        if not separator or not category.strip():
            raise InventoryDataError(
                f"Invalid sample inventory on line {line_number}; "
                "expected a category followed by a colon."
            )

        category = category.strip()
        item_type = "reusable" if category.casefold() in SAMPLE_CATEGORIES else "stock"
        for name in names.split(","):
            item_name = name.strip()
            if not item_name:
                continue
            items.append(
                {
                    "id": new_id(),
                    "name": item_name,
                    "category": category,
                    "type": item_type,
                    "quantity": random.randint(2, 8)
                    if item_type == "reusable"
                    else random.randint(5, 30),
                    "low_stock_threshold": 3,
                    "max_checkout_days": 7,
                    "max_renewals": 2,
                    "authorized_user_ids": [],
                    "active": True,
                }
            )
    return items


def _migrate_legacy_inventory(old_inventory: list[Any]) -> dict[str, Any]:
    migrated_items = []
    for index, old_item in enumerate(old_inventory):
        if not isinstance(old_item, dict):
            raise InventoryDataError(
                f"Legacy inventory entry {index + 1} must be an object."
            )
        name = old_item.get("Item")
        category = old_item.get("Category")
        if not isinstance(name, str) or not name.strip():
            raise InventoryDataError(
                f"Legacy inventory entry {index + 1} has no valid item name."
            )
        if not isinstance(category, str) or not category.strip():
            raise InventoryDataError(
                f"Legacy inventory entry {index + 1} has no valid category."
            )
        migrated_items.append(
            {
                "id": new_id(),
                "name": name.strip(),
                "category": category.strip(),
                "type": "stock",
                "quantity": random.randint(5, 30),
                "low_stock_threshold": 3,
                "max_checkout_days": 7,
                "max_renewals": 2,
                "authorized_user_ids": [],
                "active": True,
            }
        )
    return {"version": 1, "users": [], "items": migrated_items, "transactions": []}


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise InventoryDataError("Inventory data must be a JSON object.")
    for key in ("users", "items", "transactions"):
        if not isinstance(state.get(key), list):
            raise InventoryDataError(f"Inventory data field '{key}' must be a list.")
    user_ids = set()
    for index, user in enumerate(state["users"]):
        if not isinstance(user, dict):
            raise InventoryDataError(f"Employee account {index + 1} is not valid.")
        if (
            not isinstance(user.get("id"), str)
            or not user["id"].strip()
            or not isinstance(user.get("name"), str)
            or not user["name"].strip()
            or user.get("role") not in {"owner", "admin", "employee"}
            or not isinstance(user.get("active"), bool)
            or not isinstance(user.get("salt"), str)
            or not isinstance(user.get("password_hash"), str)
        ):
            raise InventoryDataError(
                f"Employee account {index + 1} has invalid fields."
            )
        if user["id"] in user_ids:
            raise InventoryDataError("Employee IDs must be unique.")
        user_ids.add(user["id"])
        if not verify_password_record_format(user):
            raise InventoryDataError(
                f"Employee account {index + 1} has an invalid password record."
            )
    if state["users"] and not any(
        user["id"] == "1" and user["role"] == "owner"
        for user in state["users"]
    ):
        raise InventoryDataError("The protected owner account (ID 1) is missing.")

    item_ids = set()
    for index, item in enumerate(state["items"]):
        if not isinstance(item, dict):
            raise InventoryDataError(f"Inventory item {index + 1} is not valid.")
        if (
            not isinstance(item.get("id"), str)
            or not item["id"]
            or not isinstance(item.get("name"), str)
            or not item["name"].strip()
            or not isinstance(item.get("category"), str)
            or not item["category"].strip()
            or item.get("type") not in {"stock", "reusable"}
            or not _is_integer(item.get("quantity"))
            or item["quantity"] < 0
            or not _is_integer(item.get("low_stock_threshold"))
            or item["low_stock_threshold"] < 0
            or not _is_integer(item.get("max_checkout_days"))
            or item["max_checkout_days"] < 1
            or not _is_integer(item.get("max_renewals"))
            or item["max_renewals"] < 0
            or not isinstance(item.get("authorized_user_ids"), list)
            or any(
                not isinstance(employee_id, str)
                for employee_id in item["authorized_user_ids"]
            )
            or not isinstance(item.get("active"), bool)
        ):
            raise InventoryDataError(f"Inventory item {index + 1} has invalid fields.")
        if item["id"] in item_ids:
            raise InventoryDataError("Inventory item IDs must be unique.")
        item_ids.add(item["id"])

    for index, transaction in enumerate(state["transactions"]):
        if not isinstance(transaction, dict):
            raise InventoryDataError(f"Transaction {index + 1} is not valid.")
        if (
            transaction.get("kind") not in {"checkout", "stock_issue"}
            or not isinstance(transaction.get("item_id"), str)
            or not isinstance(transaction.get("item_name"), str)
            or not isinstance(transaction.get("employee_id"), str)
            or not isinstance(transaction.get("employee_name"), str)
            or not _is_integer(transaction.get("quantity"))
            or transaction["quantity"] < 1
            or not _is_integer(transaction.get("quantity_outstanding"))
            or not 0 <= transaction["quantity_outstanding"] <= transaction["quantity"]
            or not isinstance(transaction.get("reason"), str)
            or not transaction["reason"].strip()
            or not _is_integer(transaction.get("renewals"))
            or transaction["renewals"] < 0
            or not isinstance(transaction.get("checked_out_at"), str)
            or (
                transaction.get("due_at") is not None
                and not isinstance(transaction.get("due_at"), str)
            )
            or (
                transaction.get("returned_at") is not None
                and not isinstance(transaction.get("returned_at"), str)
            )
        ):
            raise InventoryDataError(f"Transaction {index + 1} has invalid fields.")
        try:
            datetime.fromisoformat(transaction["checked_out_at"])
            if transaction.get("due_at"):
                datetime.fromisoformat(transaction["due_at"])
            if transaction.get("returned_at"):
                datetime.fromisoformat(transaction["returned_at"])
        except ValueError as error:
            raise InventoryDataError(
                f"Transaction {index + 1} has an invalid date."
            ) from error
    return state


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def verify_password_record_format(user: dict[str, Any]) -> bool:
    try:
        salt = bytes.fromhex(user["salt"])
        password_hash = bytes.fromhex(user["password_hash"])
    except ValueError:
        return False
    return len(salt) == 16 and len(password_hash) == hashlib.sha256().digest_size


def save_state(path: Path, state: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except OSError as error:
        raise InventoryDataError(f"Could not save {path.name}: {error}") from error


def load_state(path: Path, menu_path: Path) -> dict[str, Any]:
    if not path.exists():
        state = {
            "version": 1,
            "users": [],
            "items": _read_sample_items(menu_path),
            "transactions": [],
        }
        save_state(path, state)
        return state

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InventoryDataError(f"Could not load {path.name}: {error}") from error

    if isinstance(state, list):
        state = _migrate_legacy_inventory(state)
        save_state(path, state)
    return validate_state(state)


def make_user(
    employee_id: str, name: str, password: str, role: str
) -> dict[str, Any]:
    password_record = make_password_record(password)
    return {
        "id": employee_id,
        "name": name,
        "role": role,
        "active": True,
        **password_record,
    }


def find_user(state: dict[str, Any], employee_id: str) -> dict[str, Any] | None:
    return next(
        (
            user
            for user in state["users"]
            if user["id"] == employee_id and user.get("active", True)
        ),
        None,
    )


def authenticate(
    state: dict[str, Any], employee_id: str, password: str
) -> dict[str, Any] | None:
    user = find_user(state, employee_id)
    if user is not None and verify_password(password, user):
        return user
    return None


def setup_owner(state: dict[str, Any], password: str) -> None:
    if state["users"]:
        raise InventoryDataError("The initial owner has already been created.")
    if len(password) < 8:
        raise InventoryDataError("Passwords must be at least 8 characters.")
    state["users"].append(make_user("1", "aleb", password, "owner"))


def add_user(
    state: dict[str, Any], employee_id: str, name: str, password: str, role: str
) -> None:
    employee_id = employee_id.strip()
    name = name.strip()
    if not employee_id or not name:
        raise InventoryDataError("Enter both an employee ID and a name.")
    if employee_id == "1":
        raise InventoryDataError("Employee ID 1 is reserved for the protected owner.")
    if any(user["id"] == employee_id for user in state["users"]):
        raise InventoryDataError("That employee ID is already in use.")
    if role not in {"employee", "admin"}:
        raise InventoryDataError("Choose either employee or admin access.")
    if len(password) < 8:
        raise InventoryDataError("Passwords must be at least 8 characters.")
    state["users"].append(make_user(employee_id, name, password, role))


def change_user_role(
    state: dict[str, Any], employee_id: str, role: str
) -> None:
    user = find_user(state, employee_id)
    if user is None:
        raise InventoryDataError("That employee account was not found.")
    if employee_id == "1" or user["role"] == "owner":
        raise InventoryDataError("The owner account cannot be changed.")
    if role not in {"employee", "admin"}:
        raise InventoryDataError("Choose either employee or admin access.")
    user["role"] = role


def add_item(
    state: dict[str, Any],
    *,
    name: str,
    category: str,
    item_type: str,
    quantity: int,
    low_stock_threshold: int,
    max_checkout_days: int,
    max_renewals: int,
    authorized_user_ids: list[str],
) -> dict[str, Any]:
    name = name.strip()
    category = category.strip()
    if not name or not category:
        raise InventoryDataError("Enter an item name and category.")
    if item_type not in {"stock", "reusable"}:
        raise InventoryDataError("Choose stock or reusable equipment.")
    if quantity < 0 or low_stock_threshold < 0:
        raise InventoryDataError("Quantity and low-stock threshold cannot be negative.")
    if max_checkout_days < 1 or max_renewals < 0:
        raise InventoryDataError("Checkout days must be positive and renewals nonnegative.")
    if any(
        item["name"].casefold() == name.casefold()
        and item["category"].casefold() == category.casefold()
        for item in state["items"]
    ):
        raise InventoryDataError("That item already exists in this category.")

    item = {
        "id": new_id(),
        "name": name,
        "category": category,
        "type": item_type,
        "quantity": quantity,
        "low_stock_threshold": low_stock_threshold,
        "max_checkout_days": max_checkout_days,
        "max_renewals": max_renewals,
        "authorized_user_ids": list(authorized_user_ids),
        "active": True,
    }
    state["items"].append(item)
    return item


def update_item(
    state: dict[str, Any],
    item_id: str,
    *,
    name: str,
    category: str,
    item_type: str,
    quantity: int,
    low_stock_threshold: int,
    max_checkout_days: int,
    max_renewals: int,
    authorized_user_ids: list[str],
) -> None:
    item = next((entry for entry in state["items"] if entry["id"] == item_id), None)
    if item is None:
        raise InventoryDataError("That inventory item was not found.")
    name = name.strip()
    category = category.strip()
    if not name or not category:
        raise InventoryDataError("Enter an item name and category.")
    if item_type not in {"stock", "reusable"}:
        raise InventoryDataError("Choose stock or reusable equipment.")
    if quantity < 0 or low_stock_threshold < 0:
        raise InventoryDataError("Quantity and low-stock threshold cannot be negative.")
    if max_checkout_days < 1 or max_renewals < 0:
        raise InventoryDataError("Checkout days must be positive and renewals nonnegative.")
    if any(
        other["id"] != item_id
        and other["name"].casefold() == name.casefold()
        and other["category"].casefold() == category.casefold()
        for other in state["items"]
    ):
        raise InventoryDataError("That item already exists in this category.")
    if item_type != item["type"] and outstanding_quantity(state, item_id):
        raise InventoryDataError(
            "Return all checked-out units before changing the item type."
        )

    item.update(
        {
            "name": name,
            "category": category,
            "type": item_type,
            "quantity": quantity,
            "low_stock_threshold": low_stock_threshold,
            "max_checkout_days": max_checkout_days,
            "max_renewals": max_renewals,
            "authorized_user_ids": list(authorized_user_ids),
        }
    )


def outstanding_quantity(state: dict[str, Any], item_id: str) -> int:
    return sum(
        transaction.get("quantity_outstanding", 0)
        for transaction in state["transactions"]
        if transaction["item_id"] == item_id
        and transaction["kind"] == "checkout"
        and transaction.get("quantity_outstanding", 0) > 0
    )


def remove_item(state: dict[str, Any], item_id: str, *, permanent: bool) -> None:
    item = next((entry for entry in state["items"] if entry["id"] == item_id), None)
    if item is None:
        raise InventoryDataError("That inventory item was not found.")
    if permanent:
        if outstanding_quantity(state, item_id):
            raise InventoryDataError(
                "Return all checked-out units before permanently deleting this item."
            )
        state["items"].remove(item)
    else:
        item["active"] = False


def _can_use_item(
    item: dict[str, Any], user: dict[str, Any]
) -> bool:
    allowed_user_ids = item.get("authorized_user_ids", [])
    return (
        user["role"] in {"admin", "owner"}
        or not allowed_user_ids
        or user["id"] in allowed_user_ids
    )


def issue_item(
    state: dict[str, Any],
    *,
    employee_id: str,
    item_id: str,
    quantity: int,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    user = find_user(state, employee_id)
    item = next((entry for entry in state["items"] if entry["id"] == item_id), None)
    if user is None:
        raise InventoryDataError("Your employee account is inactive or missing.")
    if item is None or not item["active"]:
        raise InventoryDataError("That inventory item is unavailable.")
    if not _can_use_item(item, user):
        raise InventoryDataError("You are not authorized to use this item.")
    if quantity < 1 or quantity > item["quantity"]:
        raise InventoryDataError("Choose a quantity available in stock.")
    reason = reason.strip()
    if not reason:
        raise InventoryDataError("Enter a reason for issuing or checking out the item.")

    now = now or datetime.now(timezone.utc)
    due_at = (
        now + timedelta(days=item["max_checkout_days"])
        if item["type"] == "reusable"
        else None
    )
    item["quantity"] -= quantity
    transaction = {
        "id": new_id(),
        "kind": "checkout" if item["type"] == "reusable" else "stock_issue",
        "item_id": item["id"],
        "item_name": item["name"],
        "category": item["category"],
        "employee_id": user["id"],
        "employee_name": user["name"],
        "quantity": quantity,
        "quantity_outstanding": quantity if item["type"] == "reusable" else 0,
        "reason": reason,
        "checked_out_at": now.isoformat(),
        "due_at": due_at.isoformat() if due_at else None,
        "renewals": 0,
        "returned_at": None,
    }
    state["transactions"].append(transaction)
    return transaction


def return_item(
    state: dict[str, Any],
    *,
    transaction_id: str,
    employee_id: str,
    quantity: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    user = find_user(state, employee_id)
    transaction = next(
        (
            entry
            for entry in state["transactions"]
            if entry["id"] == transaction_id
            and entry["kind"] == "checkout"
            and entry.get("quantity_outstanding", 0) > 0
        ),
        None,
    )
    if user is None or transaction is None:
        raise InventoryDataError("The active checkout was not found.")
    if user["role"] not in {"admin", "owner"} and user["id"] != transaction["employee_id"]:
        raise InventoryDataError("Only the borrower or an admin can record this return.")
    if quantity < 1 or quantity > transaction["quantity_outstanding"]:
        raise InventoryDataError("Choose a quantity currently checked out.")

    item = next(
        (entry for entry in state["items"] if entry["id"] == transaction["item_id"]),
        None,
    )
    if item is not None:
        item["quantity"] += quantity
    transaction["quantity_outstanding"] -= quantity
    if transaction["quantity_outstanding"] == 0:
        now = now or datetime.now(timezone.utc)
        transaction["returned_at"] = now.isoformat()
    return transaction


def renew_checkout(
    state: dict[str, Any],
    *,
    transaction_id: str,
    employee_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    user = find_user(state, employee_id)
    transaction = next(
        (
            entry
            for entry in state["transactions"]
            if entry["id"] == transaction_id
            and entry["kind"] == "checkout"
            and entry.get("quantity_outstanding", 0) > 0
        ),
        None,
    )
    if user is None or transaction is None:
        raise InventoryDataError("The active checkout was not found.")
    if user["role"] not in {"admin", "owner"} and user["id"] != transaction["employee_id"]:
        raise InventoryDataError("Only the borrower or an admin can renew this checkout.")

    item = next(
        (entry for entry in state["items"] if entry["id"] == transaction["item_id"]),
        None,
    )
    if item is None:
        raise InventoryDataError("The inventory item for this checkout no longer exists.")
    if transaction["renewals"] >= item["max_renewals"]:
        raise InventoryDataError("The maximum number of renewals has been reached.")

    now = now or datetime.now(timezone.utc)
    due_at = datetime.fromisoformat(transaction["due_at"])
    transaction["due_at"] = (
        max(due_at, now) + timedelta(days=item["max_checkout_days"])
    ).isoformat()
    transaction["renewals"] += 1
    return transaction


def active_checkouts(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        transaction
        for transaction in state["transactions"]
        if transaction["kind"] == "checkout"
        and transaction.get("quantity_outstanding", 0) > 0
    ]


def is_overdue(transaction: dict[str, Any], now: datetime | None = None) -> bool:
    if not transaction.get("due_at"):
        return False
    now = now or datetime.now(timezone.utc)
    return datetime.fromisoformat(transaction["due_at"]) < now
