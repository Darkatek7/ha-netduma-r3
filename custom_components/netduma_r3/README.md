# Netduma R3 Home Assistant Integration

Custom integration to monitor and track devices connected to a Netduma R3 router running DumaOS.

## Features
- Lists all devices from Device Manager  
- Tracks online/offline state through Device Tracker entities  
- Reports per-device upload/download bytes and live rates via SmartQoS  
- Shows router uptime and firmware version  

## Requirements
- Netduma R3 on LAN (firmware 4.0.6xx or newer)  
- Home Assistant 2023.8+  
- Local access to the router’s HTTPS interface  

## Installation
1. Copy `custom_components/netduma_r3` to `/config/custom_components/netduma_r3`.  
2. Restart Home Assistant Core.  
3. Go to *Settings → Devices & Services → Add Integration → Netduma R3*.  
4. Enter the router’s host address (e.g. `192.168.77.1`). Disable SSL verification if the certificate is self-signed.

## Entities
| Type | Description |
|------|--------------|
| `device_tracker.*` | Online state of each known device |
| `sensor.*_rx_bytes` / `_tx_bytes` | Cumulative bytes received/sent |
| `sensor.*_rx_rate` / `_tx_rate` | Instant transfer rate (B/s) |
| `sensor.router_uptime` | Router uptime in seconds |
| `sensor.router_firmware` | Firmware version string |

## Notes
- No official API; uses JSON-RPC endpoints from DumaOS.  
- Endpoints may change with firmware updates.  
- SSL verify can be turned off for self-signed router certificates.

## License
MIT
