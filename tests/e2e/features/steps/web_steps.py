from behave import given, then, when


@given("a guru server is running")
def step_a_server_running(context):
    """Alias for the smoke feature — server is started in before_feature."""
    sock = context.project_dir / ".guru" / "guru.sock"
    assert sock.exists(), f"Server socket not found at {sock}"


@when("I open the workbench in a browser")
def step_open_workbench(context):
    context.page.goto(f"{context.server_url}/")
    context.page.wait_for_load_state("networkidle")


@then('I see the "{label}" menu item')
def step_menu_item(context, label):
    locator = context.page.get_by_role("link", name=label)
    locator.wait_for(state="visible", timeout=10000)
    assert locator.is_visible()
