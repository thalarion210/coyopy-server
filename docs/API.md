# API

## Base URLs

Default local addresses:

- http://127.0.0.1:8000
- http://localhost:8000

The interactive OpenAPI UI is available at /docs.

## Device endpoints

### POST /api/scan

Scan for nearby Coyote devices.

Request body:

```json
{
  "timeout": 5.0
}
```

Response:

```json
{
  "devices": [
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "name": "47L121000",
      "rssi": -55
    }
  ]
}
```

Notes:

- returns 409 when a device is already connected
- stores the latest scan results in server state for a later connect call without an explicit address

### POST /api/connect

Connect to a device.

Request body with explicit address:

```json
{
  "address": "AA:BB:CC:DD:EE:FF"
}
```

Request body using the first result of the latest scan:

```json
{}
```

Response:

```json
{
  "connected": true,
  "address": "AA:BB:CC:DD:EE:FF",
  "battery": 77
}
```

Notes:

- returns 409 if the server is already connected
- returns 422 if no address is supplied and there is no cached scan result
- returns 500 for transport or BLE errors

### POST /api/disconnect

Disconnect from the current device.

Response:

```json
{
  "disconnected": true
}
```

### GET /api/status

Return current connection and channel state.

Response shape:

```json
{
  "connected": false,
  "address": null,
  "battery": 0,
  "channel_a": {
    "name": "a",
    "power_pct": 0,
    "mode": "none",
    "speed": 1.0,
    "frequency": 15,
    "custom_frames": null
  },
  "channel_b": {
    "name": "b",
    "power_pct": 0,
    "mode": "none",
    "speed": 1.0,
    "frequency": 15,
    "custom_frames": null
  }
}
```

## Channel endpoints

### GET /api/channel/{ch}

Read the current state for channel a or b.

### PUT /api/channel/{ch}/power

Set channel power.

Request body:

```json
{
  "value": 42
}
```

### PUT /api/channel/{ch}/mode

Set a built-in mode, speed and frequency.

Request body:

```json
{
  "mode": "breath",
  "speed": 1.2,
  "frequency": 20
}
```

Notes:

- frequency 0 means dynamic frequency mode
- returns 422 for invalid mode parameters

### PUT /api/channel/{ch}/pattern

Install a custom looping pattern.

Request body:

```json
{
  "frames": [
    {"frequency": 15, "amplitude": 50},
    {"frequency": 25, "amplitude": 65}
  ]
}
```

Notes:

- switches the target channel into custom mode
- returns 422 for invalid frame values or invalid pattern construction

## WebSocket

### GET /ws

The WebSocket is primarily outbound. Unsupported inbound messages are ignored.

Event types:

- connected
- disconnected
- battery
- power
- mode
- frame
- error

Examples:

```json
{"event": "connected", "address": "AA:BB", "battery": 77}
```

```json
{"event": "power", "channel": "a", "value": 42}
```

```json
{"event": "frame", "a": {"frequency": 20, "amplitude": 50}, "b": {"frequency": 15, "amplitude": 30}}
```

## Error model

Errors are returned using FastAPI's standard error envelope:

```json
{
  "detail": "human readable error"
}
```

Typical status codes:

- 409 for invalid state transitions such as connect-while-connected
- 422 for validation errors or invalid request content
- 500 for BLE or transport failures
