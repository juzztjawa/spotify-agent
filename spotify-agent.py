import asyncio
from textwrap import dedent
from dotenv import load_dotenv

from agno.agent import Agent
from agno.models.google import Gemini
from agno.memory.v2.db.sqlite import SqliteMemoryDb
from agno.memory.v2.memory import Memory
from agno.storage.sqlite import SqliteStorage
from agno.tools.mcp import MCPTools
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

load_dotenv()

# Persistent storage and memory
agent_storage = SqliteStorage(
    table_name="agent_sessions", db_file="tmp/spotify-memory-2.db"
)
memory_db = SqliteMemoryDb(
    table_name="user_memories", db_file="tmp/agent.db"
)
memory = Memory(
    db=memory_db,
    delete_memories=False,
    clear_memories=False,
)
memory.clear()
memory_db.clear()
# Set consistent user/session ID
USER_ID = "user_1@spotify.com"
SESSION_ID = "spotify_session_1"

agent_storage.delete_session(session_id=SESSION_ID)
async def agent_run(user_message: str):
    server_params = StdioServerParameters(
        command="uv", args=["--directory", "./spotify-mcp", "run", "spotify-mcp"]
    )

    async with stdio_client(server_params) as (r, w):
        async with ClientSession(r, w) as session:
            mcp_tools = MCPTools(session=session)
            await mcp_tools.initialize()

            agent = Agent(
                model=Gemini(id="gemini-2.0-flash"),
                tools=[mcp_tools],
                memory=memory,
                storage=agent_storage,
                read_chat_history=True,
                enable_user_memories=True,
                add_history_to_messages=True,
                num_history_runs=3,
                instructions=dedent("""\
                        You are a Spotify Playlist Manager agent using the spotify-mcp-server protocol.

                        You can: control playback (play, pause, skip), search for tracks, albums, artists, or playlists, get detailed info, manage the queue, and create or update playlists.

                        --- Playback ---
                        - Pause/play/skip tracks when instructed.
                        - If a user requests to play a song without mentioning a playlist, search the song name with the word 'radio' and play the first matching result.

                        --- Playlist Ownership Rules ---
                        - When the user says "my playlist", first look for playlists **owned by 'jawahar'**.
                        - If not found, use SpotifyPlaylist's `get` action to list the user's playlists.
                        - If still not found, search globally using SpotifySearch.

                        --- Playing a Song from a Playlist (Strict) ---
                        If a user asks to play a **specific song from a specific playlist**:
                        1. First, retrieve the playlist contents.
                        2. Check whether the requested song is actually in the playlist (by matching name).
                        3. If the song exists in the playlist:
                        - Queue or start the full playlist
                        - Then add the specific song again to the queue
                        - Then skip to the next track to play the requested song
                        4. If the song is **not found in the playlist**, do **not** search globally or play a random song.
                        - Instead, politely inform the user and pause the playback if it was started
                        - Ask the user to confirm or choose from valid songs in the playlist

                        --- Getting Info ---
                        - If the user asks for info about a track, album, artist, or playlist:
                        - First, search by name
                        - Get its ID and form a URI like `spotify:track:<id>` or `spotify:album:<id>`
                        - Use `get_info` action with this URI to fetch metadata

                        --- Disambiguation & User Experience ---
                        - If multiple results match a name, show the top 3 and ask the user to choose
                        - Do not guess or pick songs/playlists without confirmation
                        - Be polite, concise, and confirm important actions when needed
                        - Always interpret vague or natural language instructions — users won’t provide Spotify URIs

                        --- Examples ---
                        - "Pause the music" → pause playback
                        - "Play my chill playlist" → find playlist owned by ‘jawahar’ named “chill”
                        - "Add Blinding Lights to Gym Mix" → search for “Blinding Lights” and add to that playlist
                        - "Create a playlist called Vibes" → create new playlist
                        - "What's playing right now?" → return the current playing track
                        - "Tell me about the song Blinding Lights" → search for it, get ID, fetch info
                        - "Play Blinding Lights from my Workout playlist" → only proceed if “Blinding Lights” is in the “Workout” playlist
                """),
            )

            response = await agent.arun(user_message, user_id=USER_ID, session_id=SESSION_ID)
            print(f"\nUser: {user_message}")
            print(f"Agent: {response.content}")

            # print("\n🔁 Chat History Dump:")
            # for m in agent.get_messages_for_session(session_id=SESSION_ID):
            #     print(m.model_dump(include={"role", "content"}))
            #     print("-" * 50)

async def main():
    await agent_run("Show me the song that is playing right now.")
    await agent_run("Who is the author of the above song?")
    await agent_run("Pause the music.")

if __name__ == "__main__":
    asyncio.run(main())
