"""Guard the isolated window stack; browser tests also click the real Close button."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_contextual_windows_start_above_header_and_search_layers():
    component = (ROOT / 'frontend/src/components/WorkspaceWindow.tsx').read_text(encoding='utf-8')
    css = (ROOT / 'frontend/src/streamlit-exact.css').read_text(encoding='utf-8')
    base = re.search(r'const WORKSPACE_WINDOW_BASE_Z_INDEX = (\d+);', component)
    assert base, 'An explicit baseline prevents a fresh session from starting behind the header.'
    for selector in ('.topbar', '.global-search-results'):
        rules = re.findall(re.escape(selector) + r'\{([^}]+)\}', css)
        layers = [int(value) for rule in rules for value in re.findall(r'z-index:\s*(\d+)', rule)]
        assert layers, f'Missing layer contract for {selector}'
        assert int(base.group(1)) > max(layers), f'Contextual dialogs must remain above {selector}'
    assert 'let workspaceWindowZIndex = WORKSPACE_WINDOW_BASE_Z_INDEX;' in component
    assert 'workspaceWindowZIndex += 1;' in component
    assert 'topWorkspaceWindowKey() === windowKey' in component
