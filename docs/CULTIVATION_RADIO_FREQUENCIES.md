# Cultivation radio compatibility and frequency evidence

Reviewed September 26, 2026. These are model-specific interface findings, not legal clearance or physical compatibility claims. The final application release and actual hardware proof are separate gates.

## Frequency is only one layer

A receiver must match the frequency, modulation, packet format and authorization requirements. A 915 MHz FSK decoder cannot automatically read a 915 MHz LoRaWAN device. Bluetooth and Wi-Fi both use parts of 2.4 GHz but are not interchangeable. Regional variants and firmware matter. DoobieLogic never turns a detected band into a claim of a connected grow sensor.

| Equipment or interface | Verified public evidence | DoobieLogic scope |
| --- | --- | --- |
| BTHome v2 environmental advertisements | Bluetooth LE service UUID FCD2; public temperature, humidity and CO2 object definitions, encryption and trigger flags. | Unencrypted supported objects only, through a Windows passive Bluetooth receiver. Encrypted, event-only and unknown payloads cannot be linked. |
| Ambient Weather WH31E / WH31B decoder family | rtl_433's primary decoder source describes 915 MHz FSK PCM; CRC plus checksum precede the decoded temperature/humidity fields. | Adapter consumes only the exact WH31E/WH31B JSON models from pinned external decoder 113. Physical receiver and regional-model verification still required. |
| Ecowitt WN31 / WH31 | Manufacturer specifies 915 MHz North America, 868 MHz Europe and 433 MHz other regions, approximately 60-second reporting. | Frequency research. A similar product name does not prove that every firmware emits the supported WH31E/WH31B format. |
| Growlink Wireless Climate Sensor | Current manufacturer page specifies LoRaWAN 863-930 MHz regional coverage and an optional NB-IoT variant; BLE/NFC provisioning features are also advertised. | Not decoded by BTHome or WH31 adapters. Radio mode, customer entitlement, keys and supported integration must be verified. BLE provisioning does not prove public BLE measurements. |
| Redesigned Grodan GroSens | Official current product page identifies LoRa wireless technology. | Exact channel plan, firmware packet schema and authorization are unverified. No inferred frequency or native decoder is advertised. |
| Shelly BLU H&T | Manufacturer specifies Bluetooth 4.2 and 2400-2483.5 MHz; encryption is available. | A BTHome-compatible, unencrypted configuration may match the protocol adapter. No device-specific physical acceptance is claimed and security settings are never changed automatically. |
| AROYA / TrolMaster / other proprietary systems | No sufficiently verified model-specific RF decoder contract is included in this release. | Existing authorized API/export research remains separate. Oscillator clocks and optical wavelength specifications are not RF operating bands. |

Configured sub-GHz center frequencies are 433.920, 868.300 or 915.000 MHz, selected by the host administrator for the owned device variant. Only one tuned center per configured SDR is supported. This is not a spectrum sweep or simultaneous coverage promise. The profile's actual packet decoder remains required.

The first release does not use general Wi-Fi capture, GATT reads, active BLE scan requests, spectrum/IQ files, decryption, key extraction, controller outputs, or broad rtl_433 decoder defaults. It does not prescribe agronomic settings or convert light lux to PPFD or relative soil moisture to calibrated VWC.

## Primary sources and interpretation

- BTHome format and object sizes: https://bthome.io/format/ and https://bthome.io/encryption/
- Bleak Windows passive scanning: https://bleak.readthedocs.io/en/latest/backends/windows.html
- rtl_433 decoder registry: https://github.com/merbanan/rtl_433/blob/master/include/rtl_433_devices.h
- WH31 source/output contract: https://github.com/merbanan/rtl_433/blob/master/src/devices/ambientweather_wh31e.c
- Ecowitt regional frequencies: https://www.ecowitt.com/shop/goodsDetail/361
- Growlink radio variants: https://checkout.growlink.com/products/growlink-wireless-climate-sensor
- Grodan current LoRa product: https://www.grodan.com/global/solutions/grosens-suite/
- Shelly radio specifications: https://us.shelly.com/products/shelly-blu-h-t-mocha

The rtl_433 program is external GPL software. DoobieLogic does not copy its demodulator, redistribute a binary, download or execute arbitrary plugins, or claim those licensing obligations disappear. The host administrator must install and review the intended version and pin its executable hash. Decoder numbering and output must match the reviewed contract before enablement. Packet integrity checks are not cryptographic identity authentication.

## Evidence and limits

The earlier actual Windows receiver capability test started a passive BLE scan for 15 seconds, confirmed the receiver was ready, observed zero supported format candidates, stored no measurements and stopped the child. This is an actual receiver capability result, not a connected physical sensor test. Software acceptance supplies labeled synthetic frames through the same service, database and EdgeStore path. No synthetic device or reading is injected into production discovery.

A supported physical sensor must still be verified against its displayed/controller reading at the intended facility before customer use. Raw radio cannot be recovered when the receiver PC was off. Storage quotas remain finite; bandwidth, receiver range and packet delivery are not guaranteed. The connection UI shows receiver-time timestamps and unauthenticated-broadcast provenance. No new recurring cloud service is required by this path; additional receiver hardware may be needed and was not purchased.
