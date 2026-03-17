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
    
    # We want to see all events
    async for event in story_graph.astream_events(initial_state, version='v1'):
        if event['event'] == 'on_chat_model_stream':
            tags = event.get('tags', [])
            name = event.get('name', '')
            print(f"STREAM - name: {name}, tags: {tags}, chunk: {event['data']['chunk'].content}")
        else:
            print(f"EVENT: {event['event']} | NAME: {event.get('name')} | TAGS: {event.get('tags', [])}")

if __name__ == '__main__':
    asyncio.run(main())
