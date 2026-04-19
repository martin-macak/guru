from behave import then, when


@when("I open the workbench in a browser")
def step_open_workbench(context):
    context.page.goto(f"{context.server_url}/")
    context.page.wait_for_load_state("networkidle")


@then('I see the "{label}" menu item')
def step_menu_item(context, label):
    assert context.page.get_by_role("link", name=label).is_visible()
