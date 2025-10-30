# Scenario Guide

This guide provides a complete reference for the `scenario.json` file format, which is used to define the parameters and events of a simulation.

## `scenario.json` Structure

The `scenario.json` file has two main sections: `settings` and `events`.

```json
{
  "settings": {
    "total_peers": 5,
    "watermark_secret_key": "e2e_secret",
    "default_ttl_hours": 1,
    "default_watermark_enabled": true
  },
  "events": [
    {
      "time": 0,
      "type": "CREATE_MESSAGE",
      "originator_idx": 0,
      "recipient_indices": [1],
      "content": "secret info",
      "message_id": "msg1"
    },
    // ... more events
  ]
}
```

### `settings`

The `settings` section contains a variety of options to control the simulation.

*   `total_peers` (required): The number of peers to create in the network.
*   `watermark_secret_key` (optional): The secret key to use for watermarking.
*   `default_ttl_hours` (optional): The default time-to-live for offline messages, in hours.
*   `default_watermark_enabled` (optional): Whether to enable watermarking by default for new peers.
*   `enable_signatures` (optional): Whether to enable cryptographic signature verification.
*   `log_level` (optional): The logging level to use for the simulation.

### `events`

The `events` section contains a list of events to be processed by the simulation engine. Each event is a JSON object with a `time` and a `type`, as well as other event-specific properties.

#### `CREATE_MESSAGE`

Creates a new message.

*   `originator_idx`: The index of the peer that is creating the message.
*   `recipient_indices`: A list of indices of the peers that will receive the message.
*   `content`: The content of the message.
*   `message_id`: A unique ID for the message.

#### `FORWARD_MESSAGE`

Forwards an existing message.

*   `sender_idx`: The index of the peer that is forwarding the message.
*   `recipient_indices`: A list of indices of the peers that will receive the forwarded message.
*   `parent_message_id`: The ID of the message that is being forwarded.
*   `forwarded_message_id`: A new unique ID for the forwarded message.

#### `DELETE_MESSAGE`

Deletes a message.

*   `originator_idx`: The index of the peer that is deleting the message.
*   `message_id`: The ID of the message to delete.

#### `PEER_ONLINE` / `PEER_OFFLINE`

Changes the online status of a peer.

*   `peer_idx`: The index of the peer whose status is changing.

#### `SET_PEER_SETTINGS`

Changes the settings for a peer.

*   `peer_idx`: The index of the peer whose settings are changing.
*   `settings`: A JSON object containing the new settings.
    *   `watermark_enabled`: Whether to enable watermarking for the peer.
    *   `track_forwards`: Whether to track forwards for the peer.

#### `AIRGAP_TRANSFER`

Simulates the transfer of a message to an external storage system.

*   `peer_idx`: The index of the peer that is performing the transfer.
*   `message_id`: The ID of the message to transfer.
*   `encryption_mode`: The encryption mode to use for the transfer. Can be `NONE`, `RECOVERABLE`, or `IRRECOVERABLE`.

#### `VERIFY_WATERMARK`

Verifies the watermark of a message.

*   `peer_idx`: The index of the peer that is verifying the watermark.
*   `message_id`: The ID of the message to verify.
