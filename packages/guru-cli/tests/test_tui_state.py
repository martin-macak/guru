from guru_cli.tui.state import PanelState, WorkbenchMode, WorkbenchState


def test_workbench_state_defaults_to_investigate():
    state = WorkbenchState()
    assert state.mode is WorkbenchMode.INVESTIGATE
    assert state.panels == PanelState(tree_visible=False, detail_visible=False)
    assert state.selected_document_id is None
    assert state.selected_node_id is None


def test_workbench_state_focus_switches_clear_conflicting_focus():
    state = WorkbenchState()
    state = state.with_document("docs/auth.md")
    assert state.selected_document_id == "docs/auth.md"
    state = state.with_node("kb::pkg.services.UserService")
    assert state.selected_document_id is None
    assert state.selected_node_id == "kb::pkg.services.UserService"
