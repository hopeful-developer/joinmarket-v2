import json
from unittest.mock import AsyncMock

import pytest
from jmcore.protocol import MessageType

from orderbook_watcher.directory_client import DirectoryClient


@pytest.mark.asyncio
async def test_get_peerlist_skips_unexpected_response() -> None:
    # This test verifies that get_peerlist skips unexpected messages (like PUBMSG)
    # and successfully processes the eventual PEERLIST message.
    mock_connection = AsyncMock()

    pub_msg = {"type": MessageType.PUBMSG.value, "line": "some public message"}
    # Correct format: nick;location
    peerlist_msg = {"type": MessageType.PEERLIST.value, "line": "nick1;peer1:5222,nick2;peer2:5222"}

    mock_connection.receive.side_effect = [
        json.dumps(pub_msg).encode("utf-8"),
        json.dumps(peerlist_msg).encode("utf-8"),
    ]

    client = DirectoryClient("test.onion", 5222, "testnet")
    client.connection = mock_connection
    client.timeout = 5.0  # fast timeout

    peers = await client.get_peerlist()
    assert len(peers) == 2
    assert "nick1" in peers
    assert "nick2" in peers
