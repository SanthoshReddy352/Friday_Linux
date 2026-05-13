import sys
sys.path.append("/home/tricky/Friday_Linux")
from core.context_store import ContextStore
store = ContextStore()
print("SUMMARY:")
print(repr(store.summarize_session("2a22299c-f7f2-4323-ac8d-c5660d7a3757", limit=20)))
