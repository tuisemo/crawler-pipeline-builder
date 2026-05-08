import pathlib

p1 = pathlib.Path('tests/test_workflow_executor.py')
text1 = p1.read_text(encoding='utf-8')
text1 = text1.replace('backend.workflow.executor.page_session_mgr', 'backend.workflow.executor_helpers.ext_session_mgr')
# Since ext_session_mgr.create takes an agent_id, we need to adjust the lambda:
text1 = text1.replace('lambda: session', 'lambda agent_id: session')
p1.write_text(text1, encoding='utf-8')

p2 = pathlib.Path('tests/test_assist_services.py')
text2 = p2.read_text(encoding='utf-8')
text2 = text2.replace('backend.assist.services.page_session_mgr', 'backend.assist.services.ext_session_mgr')
# ext_session_mgr.create takes (agent_id, url), so if any lambda creates it:
text2 = text2.replace('lambda: FakeSession()', 'lambda agent_id, url=None: FakeSession()')
# Also remove `get_active_session` patches:
# Actually test_assist_services might have `FakeManager()` which might need a `get` method.
p2.write_text(text2, encoding='utf-8')
