import re

def get_farewell(summary):
    topic = None
    if summary:
        for line in reversed(summary.split('\n')):
            if line.startswith("user: "):
                msg = line[6:].strip()
                msg_clean = re.sub(r'^(search for|search|google|open|play|tell me about|what is|who is|how to|why are|explain|can you explain)\s+', '', msg, flags=re.IGNORECASE).strip(' .!?')
                if len(msg_clean) > 2 and not re.search(r'^(bye|goodbye|exit|quit|stop|shut down|shutdown|close)$', msg_clean, re.IGNORECASE):
                    topic = msg_clean
                    break
    
    if topic:
        return f"Bye sir. We recently discussed {topic}, looking forward to having more conversation about it later. See you soon!"
    return "Bye sir, see you soon."

print(get_farewell("user: Google capital of france\nassistant: Paris"))
print(get_farewell("user: what is programming languages and why are they important ?\nassistant: abc\nuser: Goodbye"))
print(get_farewell("user: play never gonna give you up\nassistant: playing"))
