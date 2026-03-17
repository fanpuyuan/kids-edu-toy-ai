import httpx

with httpx.stream('POST', 'http://localhost:8004/chat_stream', json={'input': '你好，穿红裙子不要吃青椒', 'session_id': 'test2', 'config': {}}) as r:
    print("Status:", r.status_code)
    for line in r.iter_lines():
        if line:
            print(line)
