def read_menu():
    menus = {}
    try:
        with open("Final Project\\menu.txt", "r") as file:
            for line in file:
                parts_of_line = line.strip().split(":")
                category = parts_of_line[0].strip()
                detail = parts_of_line[1].strip()
                menus[category] = detail
        return menus
    except Exception as e:
        print(e)


def split_into_variables(menu_items):
    coffee = menu_items.get("LARGE_ITEMS")
    prices = menu_items.get("MEDIUM_ITEMS")
    milks = menu_items.get("SMALL_ITEMS")
    flavors = menu_items.get("OTHER ITEMS")
    return (
        coffee,
        prices,
        milks,
        flavors,
    )


def print_menu(coffee, prices, milks, flavors):
    """This section deliberately incomplete"""
    print("Coffee\n")
    coffee_item = coffee.split(",")
    for item in coffee_item:
        print(f"\t{item.strip()}")


def main():
    menu_items = read_menu()
    (
        coffee,
        prices,
        milks,
        flavors,
    ) = split_into_variables(menu_items)
    print_menu(coffee, prices, milks, flavors)


main()
