import sys
import asyncio
sys.path.append('services/brain')
from graph import story_graph

async def main():
    initial_state = {
        'input': '我讨厌大灰狼',
        'chat_history': [],
        'session_id': 'test-local-log',
        'config': {
            'model': 'qwen3.5:0.8b',
            'llm_env': 'local'
        }
    }
    
    found_any = False
    print("STARTING ASTREAM EVENTS")
    async for event in story_graph.astream_events(initial_state, version='v1'):
        found_any = True
        evt_type = event['event']
        name = event.get('name', 'Unknown')
        tags = event.get('tags', [])
        
        if evt_type == "on_chat_model_stream":
            print(f"STREAM -> name={name}, tags={tags}")
        elif evt_type in ("on_chain_start", "on_chain_end"):
            print(f"{evt_type} -> name={name}, tags={tags}")
            
    if not found_any:
        print("NO EVENTS RETURNED!")

if __name__ == '__main__':
    asyncio.run(main())
