import sys
import asyncio
sys.path.append('services/brain')
from graph import story_graph

async def main():
    initial_state = {
        'input': '我今天穿了一件红色的裙子',
        'chat_history': [],
        'session_id': 'test2',
        'config': {
            'model': 'qwen3.5:0.8b',
            'llm_env': 'local'
        }
    }
    
    in_generate = False
    async for event in story_graph.astream_events(initial_state, version='v1'):
        evt_type = event['event']
        name = event.get('name', 'Unknown')
        
        if evt_type == "on_chain_start" and name == "generate":
            in_generate = True
            print("-> ENTERED GENERATE NODE")
        elif evt_type == "on_chain_end" and name == "generate":
            in_generate = False
            print("<- EXITED GENERATE NODE")
            
        if evt_type == "on_chat_model_stream":
            if in_generate:
                print(f"VALID CHUNK (in_generate=True): {event['data']['chunk'].content}")
            else:
                print(f"IGNORED CHUNK (in_generate=False) name={name}: {event['data']['chunk'].content}")

if __name__ == '__main__':
    asyncio.run(main())
