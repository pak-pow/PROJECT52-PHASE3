"""Tests for WebSocket connection and synchronization handling."""


def test_socket_connection(socket_client):
    """Verify test client can establish WebSocket connection."""
    assert socket_client.is_connected()
    socket_client.disconnect()
    assert not socket_client.is_connected()
