# JoinMarket Messaging Protocol

## Message Format

All messages are JSON envelopes with two fields:
```json
{"type": <message_type>, "line": "<payload>"}
```

Messages are terminated with `\r\n`.

## Message Types

- **685**: PRIVMSG - Private message between two peers
- **687**: PUBMSG - Public broadcast message to all peers
- **789**: PEERLIST - Directory sends list of connected peers (after routing a PRIVMSG, directory sends this to inform recipient of sender's location)
- **791**: GETPEERLIST - Request peer list from directory
- **793**: HANDSHAKE - Client handshake request
- **795**: DN_HANDSHAKE - Directory handshake response
- **797**: PING - Keep-alive ping (sent by clients to maintain connection)
- **799**: PONG - Ping response (sent by directory in response to PING)
- **801**: DISCONNECT - Graceful disconnect

## JoinMarket Message Format (inside "line" field)

Format: `{from_nick}!{to_nick}!{command} {arguments}`

- `from_nick`: Sender's nickname (e.g., `J5AiXEVUkwBBZs8A`)
- `to_nick`: Recipient nickname or `PUBLIC` for broadcasts
- `command`: Command with `!` prefix (e.g., `!orderbook`, `!sw0reloffer`)
- `arguments`: Space-separated command arguments

### Examples

**Public orderbook request:**
```
J54JdT1AFotjmpmH!PUBLIC!!orderbook
```

**Maker offer announcement (PRIVMSG to taker):**
```
J5AiXEVUkwBBZs8A!J54JdT1AFotjmpmH!sw0reloffer 0 224207 40603304 0 0.000014!tbond <fidelity_bond_proof>
```

## Nick Format

JoinMarket nicks follow this format:
- Prefix: `J` (JoinMarket identifier)
- Version: `5` (protocol version)
- Hash: 10-character base58-encoded SHA256(pubkey) hash
- Padding: Right-padded with `O` to 14 characters total

Example: `J54JdT1AFotjmpmHOOOO` (16 chars total including `J5`)

## Orderbook Watcher Flow

1. **Connect to directory**
   - Send HANDSHAKE (type 793)
   - Receive DN_HANDSHAKE (type 795)

2. **Request peer list**
   - Send GETPEERLIST (type 791)
   - Receive PEERLIST (type 789): `nick1;location1,nick2;location2,...`

3. **Request orderbooks**
   - Send PUBMSG (type 687): `{watcher_nick}!PUBLIC!!orderbook`
   - Directory broadcasts to all connected makers
   - Makers respond with PRIVMSG (type 685) containing their offers

4. **Receive offers**
   - Each maker sends one PRIVMSG per offer type they support
   - Format: `{maker_nick}!{watcher_nick}!{offer_type} {oid} {minsize} {maxsize} {txfee} {cjfee}!tbond {fidelity_bond_proof}`

## Offer Types

- **sw0absoffer**: Segregated Witness absolute fee offer
- **sw0reloffer**: Segregated Witness relative fee offer
- **swabsoffer**: Legacy Segregated Witness absolute fee (deprecated)
- **swreloffer**: Legacy Segregated Witness relative fee (deprecated)

### Offer Fields

1. **oid**: Order ID (integer)
2. **minsize**: Minimum coinjoin size in satoshis (integer)
3. **maxsize**: Maximum coinjoin size in satoshis (integer)
4. **txfee**: Transaction fee contribution in satoshis (integer)
5. **cjfee**: Coinjoin fee
   - Absolute offers: integer (satoshis)
   - Relative offers: decimal (e.g., `0.000014` = 14 ppm)

### Fidelity Bond Proof

After the offer fields, separated by `!tbond `, makers can include a fidelity bond proof (base64-encoded).

Format: `!tbond {base64_proof}`

The proof contains:
- Timelocked UTXO information
- Public key
- Signature proving ownership
- Certificate expiry block height

## Example Session

```
// Watcher connects and handshakes
-> {"type": 793, "line": "{\"app-name\": \"joinmarket\", \"directory\": false, ...}"}
<- {"type": 795, "line": "{\"app-name\": \"joinmarket\", \"directory\": true, \"accepted\": true, ...}"}

// Watcher requests peer list
-> {"type": 791, "line": ""}
<- {"type": 789, "line": "J5Maker1;onion1.onion:5222,J5Maker2;onion2.onion:5222"}

// Watcher broadcasts orderbook request
-> {"type": 687, "line": "J5Watcher!PUBLIC!!orderbook"}

// Makers respond with offers (via directory forwarding)
<- {"type": 685, "line": "J5Maker1!J5Watcher!sw0reloffer 0 100000 1000000 500 0.000020"}
<- {"type": 685, "line": "J5Maker2!J5Watcher!sw0absoffer 1 50000 500000 1000 5000"}

// Watcher disconnects
-> {"type": 801, "line": ""}
```

## Implementation Notes

1. **Directory behavior**:
   - When a PUBMSG to `PUBLIC` is received, the directory broadcasts it to all connected peers
   - When a PRIVMSG is received, the directory routes it to the specific recipient
   - After routing a PRIVMSG, the directory sends a PEERLIST message (type 789) to the recipient with the sender's location
   - The PEERLIST format after PRIVMSG routing: `{sender_nick};{sender_location}`

2. **Orderbook requests**:
   - Watcher sends ONE `!orderbook` broadcast to `PUBLIC`
   - Makers respond individually with PRIVMSG containing their offers
   - Watcher must listen for PRIVMSG (type 685) responses, not PUBMSG

3. **Multiple offers per maker**:
   - A maker can send multiple PRIVMSG messages, one per offer type
   - Each message contains one offer and optional fidelity bond proof
   - Format: `{offer_type} {params}!tbond {base64_proof}`

4. **Keep-alive**:
   - Clients should send PING (type 797) periodically to maintain connection
   - Directory responds with PONG (type 799)
   - Recommended interval: 60 seconds

5. **Timeouts**:
   - Wait 10+ seconds after sending `!orderbook` to collect all responses
   - Not all makers will respond (some may be offline or not accepting new participants)
