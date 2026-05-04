from core.app import FridayApp
from core.planning.turn_orchestrator import TurnRequest
import sys

app = FridayApp()
app.initialize()

print("--- TESTING CALENDAR QUERY ---")
req = TurnRequest(text="What's on my calendar today", source="gui")
res = app.turn_orchestrator.handle(req)
print(f"GUI: source={res.source}, plan_mode={res.plan_mode}, resp={res.response[:60]}")

req2 = TurnRequest(text="What's on my calendar today", source="voice")
res2 = app.turn_orchestrator.handle(req2)
print(f"VOICE: source={res2.source}, plan_mode={res2.plan_mode}, resp={res2.response[:60]}")

sys.exit(0)
