# Sources

- `wire_protocol.py`, `wire_schema.json`: originally copied from the user's local `/home/lubancat/lzd/lite-panel`, commit `005b566b6661b77541093b7d7c2940114273c580`. The protocol is LP Binary v1. Source repository: https://gitee.com/laingzd/lite-panel .
- `motors.py`: GPIO numbers and direction levels follow `Demo/DeskBot_demo/common/gpio_manager/gpio_manager.h` and `gui_app/pages/ui_ChatBotPage/app_ChatBotPage.c` in this repository.
- `camera_capture.c`: uses the same VI/VENC/ISP interfaces as the local Rockchip SDK examples; SDK interfaces remain under their original licenses.
- `vendor/paho`: paho-mqtt 2.1.0, original wheel `paho_mqtt-2.1.0-py3-none-any.whl`. Preserve the source copyright headers and `vendor/licenses/LICENSE.txt`; dual EPL-2.0 / EDL-1.0. License URLs are included in source headers.
- `vendor/ca-bundle.crt`: public root certificates concatenated from Ubuntu `ca-certificates_20260816ubuntu0.22.04.2_all.deb`, `usr/share/ca-certificates`. No local custom trust certificates or private keys are included. For a private Broker CA, provide `ca_file` in the device's cloud configuration.

- Echo-Mate performance changes (2026-11-20): LP Binary CRC uses `binascii.crc_hqx` with the same polynomial and initial value; encoded frames are checked against the original host codec. The vendored paho client masks outgoing RFC 6455 frames using native integer XOR instead of a Python byte loop; frame boundary and masking compatibility tests cover small and extended-length payloads. Original license headers are retained.
